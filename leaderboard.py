import pandas as pd
from player_in_match import PlayerInMatch
from match_class import Match
from rapidfuzz import process
from rapidfuzz import fuzz

class Leaderboard:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.load_leaderboard()

    def load_leaderboard(self):
        try:
            self.leaderboard = pd.read_csv(self.csv_file)
            self.leaderboard.set_index('Rank', inplace=True)
        except FileNotFoundError:
            self.create_empty_leaderboard()
            # self.leaderboard = pd.DataFrame()
            # self.leaderboard.set_index('Rank', inplace=True)

    def create_empty_leaderboard(self):
        columns = [
            'Rank',
            'Player Name', 
            'Player Discord', 
            'ELO', 
            'Crewmate ELO', 
            'Impostor ELO',
            'Voting Accuracy (Crewmate games)',
            'Total Number Of Games Played',
            'Number Of Impostor Games Played',
            'Number Of Crewmate Games Played',
            'Number Of Impostor Games Won', 
            'Number Of Crewmate Games Won',
            'Number Of Games Won',
            'Number Of Games Died First'
            # , 
            # 'Previous Games Voting Accuracy', 'Change In Crewmate ELO', 'Change In Impostor ELO',
            # 'Crewmate Win Streak', 'Best Crewmate Win Streak',
            # 'Impostor Win Streak', 'Best Impostor Win Streak'
        ]
        self.leaderboard = pd.DataFrame(columns=columns)
        self.leaderboard.set_index('Rank', inplace=True)

    def save_leaderboard(self):
        self.leaderboard.to_csv(self.csv_file)

    def new_player(self, player_name):
        new_player_data = {
            'Player Name': player_name,
            'Player Discord': None,
            'ELO': 1000,
            'Crewmate ELO': 1100,
            'Impostor ELO': 900,
            'Voting Accuracy (Crewmate games)': 1,
            'Total Number Of Games Played': 0,
            'Number Of Impostor Games Played': 0,
            'Number Of Crewmate Games Played': 0,
            'Number Of Impostor Games Won': 0,
            'Number Of Crewmate Games Won': 0,
            'Number Of Games Won': 0,
            'Number Of Games Died First': 0 
            #,
            # 'Best Crewmate Win Streak': 0,
            # 'Impostor Win Streak': 0,
            # 'Best Impostor Win Streak': 0,
            # 'Previous Games Voting Accuracy': pd.DataFrame([], columns=['Accuracy List']),
            # 'Change In Crewmate ELO': pd.DataFrame([], columns=['Change In Crewmate ELO']),
            # 'Change In Impostor ELO': pd.DataFrame([], columns=['Change In Impostor ELO'])
        }
        self.leaderboard = pd.concat([self.leaderboard, pd.DataFrame([new_player_data])], ignore_index=True)
        self.rank_players()
        self.save_leaderboard()

    def update_player(self, player: PlayerInMatch):
        player_row = self.get_player_row(player.name)
        index = player_row['Rank']

        self.leaderboard.at[index, 'ELO'] = round(player.current_elo, 3)
        self.leaderboard.at[index, 'Crewmate ELO'] = round(player.crewmate_current_elo, 3)
        self.leaderboard.at[index, 'Impostor ELO'] = round(player.impostor_current_elo, 3)
        self.leaderboard.at[index, 'Total Number Of Games Played'] += 1

        if player.won:
            self.leaderboard.at[index, 'Number Of Games Won'] += 1

        if player.team == "crewmate":
            self.update_crewmate_stats(index, player)
        else:
            self.update_impostor_stats(index, player)

        self.rank_players()
        self.save_leaderboard()
        
    def rank_players(self):
        self.leaderboard = self.leaderboard.sort_values(by='ELO', ascending=False)
        self.leaderboard.reset_index(drop=True, inplace=True)
        self.leaderboard.index.name = 'Rank'

    def update_crewmate_stats(self, index, player):
        self.leaderboard.at[index, 'Number Of Crewmate Games Played'] += 1
        if player.won:
            self.leaderboard.at[index, 'Number Of Crewmate Games Won'] += 1

        if player.died_first_round:
            self.leaderboard.at[index, 'Number Of Games Died First'] += 1
        else:
            voting_acc = self.leaderboard.at[index, 'Voting Accuracy (Crewmate games)'] 
            games_died_first = self.leaderboard.at[index, 'Number Of Games Died First']
            total_crew_games = self.leaderboard.at[index, 'Number Of Crewmate Games Played']
            new_voting_acc = (voting_acc * (total_crew_games - games_died_first - 1) + player.get_voting_accuracy()) / total_crew_games
            self.leaderboard.at[index, 'Voting Accuracy (Crewmate games)'] = new_voting_acc

    def update_impostor_stats(self, index, player):
        self.leaderboard.at[index, 'Number Of Impostor Games Played'] += 1
        if player.won:
            self.leaderboard.at[index, 'Number Of Impostor Games Won'] += 1

    def get_player_row(self, player_name):
        row = self.leaderboard[self.leaderboard['Player Name'] == player_name]
        if row.empty: 
            self.leaderboard['player_name_normalized'] = self.leaderboard['Player Name'].apply(lambda x: x.strip().lower())
            best_match = process.extractOne(player_name.strip().lower(), self.leaderboard['player_name_normalized'], score_cutoff=85)
            if best_match is not None:
                best_player_name_match = best_match[0]
                row = self.leaderboard[self.leaderboard['player_name_normalized'] == best_player_name_match]
            self.leaderboard.drop(columns=['player_name_normalized'], inplace=True)
        if not row.empty:
            row.reset_index(inplace=True, drop=False)
            return row.iloc[0]
        else:
            return None

    def get_player_ranking(self, player_name):
        player_row = self.get_player_row(player_name)
        if not player_row.empty:
            ranking = player_row['Rank'] + 1
            return ranking
        else:
            return None
    
    def get_player_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            return player_row['ELO']
        else:
            return None

    def get_player_crew_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            return player_row['Crewmate ELO']
        else:
            return None
        
    def get_player_imp_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            return player_row['Impostor ELO']
        else:
            return None

    def is_player_in_leaderboard(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            return not player_row.empty
        else:
            return False
    
    def get_player_crew_win_rate(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            crew_games_won = player_row['Number Of Crewmate Games Won']
            crew_games_played = player_row['Number Of Crewmate Games Played']
            if crew_games_played > 0:
                return (crew_games_won / crew_games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None
        
    def get_player_imp_win_rate(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            impostor_games_won = player_row['Number Of Impostor Games Won']
            impostor_games_played = player_row['Number Of Impostor Games Played']
            if impostor_games_played > 0:
                return (impostor_games_won / impostor_games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None
        
    def get_player_win_rate(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            games_won = player_row['Number Of Games Won']
            games_played = player_row['Total Number Of Games Played']
            if games_played > 0:
                return (games_won / games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None    

    def add_player_discord(self, player_name, discord_id):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            index = player_row['Rank']
            self.leaderboard.at[index, 'Player Discord'] = discord_id
            self.save_leaderboard()

    def top_players_by_mmr(self, top=10):
        if top == "": top == 10
        top_players = self.leaderboard[['Player Name', 'ELO']].head(top)
        return top_players

    def top_players_by_impostor_mmr(self, top=10):
        if top == "":
            top = 10
        top_impostors = self.leaderboard[['Player Name', 'Impostor ELO']].sort_values(by='Impostor ELO', ascending=False).head(top)
        top_impostors.columns = ['Player Name', 'Impostor MMR']
        top_impostors.reset_index(drop=True, inplace=True)
        top_impostors.index.name = 'Rank'
        return top_impostors

    def top_players_by_crewmate_mmr(self, top=10):
        if top == "":
            top = 10
        top_crewmates = self.leaderboard[['Player Name', 'Crewmate ELO']].sort_values(by='Crewmate ELO', ascending=False).head(top)
        top_crewmates.columns = ['Player Name', 'Crewmate MMR']
        top_crewmates.reset_index(drop=True, inplace=True)
        top_crewmates.index.name = 'Rank'
        return top_crewmates
    

    def is_player_sherlock(self, player_name):
        best_crewmate = self.leaderboard[['Player Name', 'Crewmate ELO']].sort_values(by='Crewmate ELO', ascending=False).head(1)
        crewmate_name = best_crewmate.iloc[0]['Player Name']
        if fuzz.ratio(player_name.lower().strip(), crewmate_name.lower().strip()) >= 85:
            return True
        else:
            return False
    
    def is_player_jack_the_ripper(self, player_name):
        best_impostor = self.leaderboard[['Player Name', 'Impostor ELO']].sort_values(by='Impostor ELO', ascending=False).head(1)
        impostor_name = best_impostor.iloc[0]['Player Name']
        if fuzz.ratio(player_name.lower().strip(), impostor_name.lower().strip()) >= 85:
            return True
        else:
            return False

    
    # Add other methods as needed


# print(match_z.players.__dict__)
# print(match_z.__dict__)
# for player in match_z.players.players:
#     print(player.__dict__)
# print(match_z.players.players[0].__dict__)
# Example usage:
# leaderboard = Leaderboard('leaderboard_full.csv')
# print(leaderboard.get_player_row("A"))
# print(leaderboard.get_player_crew_win_rate("Aiden"))
# # print(leaderboard.get_player_ranking("no one"))
# print(leaderboard.get_player_row("A"))


# f = FileHandler()
# path = "Matches/"
# file_name =  "TgNtl8gi1LgUOLGo_match.json"
# match = f.match_from_file(path,file_name)
# print(match.__dict__)
# player1 = PlayerInMatch(name="aiden")
# leaderboard.new_player(player1)
# print(leaderboard.leaderboard)
# print(leaderboard.get_player_elo('aiden'))

# print(df)
# df.to_csv("csv.csv")