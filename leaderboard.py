import pandas as pd
from player_in_match import PlayerInMatch
from match_class import Match
from rapidfuzz import process
from rapidfuzz import fuzz
import difflib

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


    def create_empty_leaderboard(self):
        columns = [
            'Rank',
            'Player Name', 
            'Player Discord', 
            'MMR', 
            'Crewmate MMR', 
            'Impostor MMR',
            'Voting Accuracy (Crewmate games)',
            'Total Number Of Games Played',
            'Number Of Impostor Games Played',
            'Number Of Crewmate Games Played',
            'Number Of Impostor Games Won', 
            'Number Of Crewmate Games Won',
            'Number Of Games Won',
            'Number Of Games Died First',
            'Threw on Crit', 
            'Voted Right on Crit but Lost'
            # , 
            # 'Previous Games Voting Accuracy', 'Change In Crewmate MMR', 'Change In Impostor MMR',
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
            'Player Discord': "",
            'MMR': 1000,
            'Crewmate MMR': 1000,
            'Impostor MMR': 1000,
            'Voting Accuracy (Crewmate games)': 1,
            'Total Number Of Games Played': 0,
            'Number Of Impostor Games Played': 0,
            'Number Of Crewmate Games Played': 0,
            'Number Of Impostor Games Won': 0,
            'Number Of Crewmate Games Won': 0,
            'Number Of Games Won': 0,
            'Number Of Games Died First': 0,
            'Threw on Crit': 0, 
            'Voted Right on Crit but Lost': 0
            #,
            # 'Best Crewmate Win Streak': 0,
            # 'Impostor Win Streak': 0,
            # 'Best Impostor Win Streak': 0,
            # 'Previous Games Voting Accuracy': pd.DataFrame([], columns=['Accuracy List']),
            # 'Change In Crewmate MMR': pd.DataFrame([], columns=['Change In Crewmate MMR']),
            # 'Change In Impostor MMR': pd.DataFrame([], columns=['Change In Impostor MMR'])
        }
        self.leaderboard = pd.concat([self.leaderboard, pd.DataFrame([new_player_data])], ignore_index=True)
        self.rank_players()
        self.save_leaderboard()


    def update_player(self, player: PlayerInMatch):
        player_row = self.get_player_row(player.name)
        index = player_row['Rank']
        if player.canceled:
            self.leaderboard.at[index, 'MMR'] -= player.mmr_gain
            self.leaderboard.at[index, 'MMR'] = round(self.leaderboard.at[index, 'MMR'],3)
            self.leaderboard.at[index, 'Crewmate MMR'] -= player.crewmate_mmr_gain
            self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
            self.leaderboard.at[index, 'Impostor MMR'] -= player.impostor_mmr_gain
            self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
            self.leaderboard.at[index, 'Total Number Of Games Played'] -= 1
            if player.won: self.leaderboard.at[index, 'Number Of Games Won'] -= 1

        else:
            self.leaderboard.at[index, 'MMR'] += player.mmr_gain
            self.leaderboard.at[index, 'MMR'] = round(self.leaderboard.at[index, 'MMR'],3)
            self.leaderboard.at[index, 'Crewmate MMR'] += player.crewmate_mmr_gain
            self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
            self.leaderboard.at[index, 'Impostor MMR'] += player.impostor_mmr_gain
            self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
            self.leaderboard.at[index, 'Total Number Of Games Played'] += 1
            if player.won: self.leaderboard.at[index, 'Number Of Games Won'] += 1
            
        if player.team == "crewmate":
            self.update_crewmate_stats(index, player)
        else:
            self.update_impostor_stats(index, player)

        self.rank_players()
        self.save_leaderboard()
        

    def rank_players(self):
        self.leaderboard = self.leaderboard.sort_values(by='MMR', ascending=False)
        self.leaderboard.reset_index(drop=True, inplace=True)
        self.leaderboard.index.name = 'Rank'


    def update_crewmate_stats(self, index, player : PlayerInMatch):
        if player.canceled:
            self.leaderboard.at[index, 'Number Of Crewmate Games Played'] -= 1
        else:
            self.leaderboard.at[index, 'Number Of Crewmate Games Played'] += 1

        if player.won:
            if player.canceled:
                self.leaderboard.at[index, 'Number Of Crewmate Games Won'] -= 1
            else:
                self.leaderboard.at[index, 'Number Of Crewmate Games Won'] += 1

        if player.died_first_round:
            if player.canceled:
                self.leaderboard.at[index, 'Number Of Games Died First'] -= 1
            else:
                self.leaderboard.at[index, 'Number Of Games Died First'] += 1
        else:
            voting_acc = self.leaderboard.at[index, 'Voting Accuracy (Crewmate games)'] 
            games_died_first = self.leaderboard.at[index, 'Number Of Games Died First']
            total_crew_games = self.leaderboard.at[index, 'Number Of Crewmate Games Played']
            new_voting_acc = ((voting_acc * (total_crew_games - games_died_first - 1)) + player.get_voting_accuracy()) / (total_crew_games - games_died_first)
            self.leaderboard.at[index, 'Voting Accuracy (Crewmate games)'] = round(new_voting_acc,4)
            if player.voted_wrong_on_crit:
                if player.canceled:
                    self.leaderboard.at[index, 'Threw on Crit'] -= 1
                else:
                    self.leaderboard.at[index, 'Threw on Crit'] += 1
            if player.right_vote_on_crit_but_loss:
                if player.canceled:
                    self.leaderboard.at[index, 'Voted Right on Crit but Lost'] -= 1
                else:
                    self.leaderboard.at[index, 'Voted Right on Crit but Lost'] += 1
            

    def update_impostor_stats(self, index, player):
        if player.canceled:
            self.leaderboard.at[index, 'Number Of Impostor Games Played'] -= 1
        else:
            self.leaderboard.at[index, 'Number Of Impostor Games Played'] += 1

        if player.won:
            if player.canceled:
                self.leaderboard.at[index, 'Number Of Impostor Games Won'] -= 1
            else:
                self.leaderboard.at[index, 'Number Of Impostor Games Won'] += 1


    def get_player_row(self, player_name):
        lowercase_name = str(player_name).lower().replace(" ","")
        row = self.leaderboard[self.leaderboard['Player Name'].str.lower().str.replace(" ","") == lowercase_name]
        if not row.empty:
            row.reset_index(inplace=True, drop=False)
            return row.iloc[0]
        else:
            return None
        

    def get_player_row_lookslike(self, player_name):
        row = self.leaderboard[self.leaderboard['Player Name'] == player_name]

        if row.empty: 
            self.leaderboard['player_name_normalized'] = self.leaderboard['Player Name'].apply(lambda x: x.strip().lower().replace(" ",""))
            best_match = process.extractOne(player_name.strip().lower().replace(" ",""), self.leaderboard['player_name_normalized'], score_cutoff=85)
            if best_match is not None:
                best_player_name_match, score, any = best_match
                if score >= 85:  # Adjust the threshold as needed
                    row = self.leaderboard[self.leaderboard['player_name_normalized'] == best_player_name_match]

            # Check if the column exists before attempting to drop it
            if 'player_name_normalized' in self.leaderboard.columns:
                self.leaderboard.drop(columns=['player_name_normalized'], inplace=True)

        if not row.empty:
            row.reset_index(inplace=True, drop=False)
            return row.iloc[0]
        else:
            return None

        
    def get_player_ranking(self, player_row):
        if not player_row.empty:
            ranking = player_row['Rank'] + 1
            return ranking
        else:
            return None
    

    def get_player_mmr(self, player_row):
        if player_row is not None and not player_row.empty:
            return player_row['MMR']
        else:
            return None


    def get_player_crew_mmr(self, player_row):
        if player_row is not None and not player_row.empty:
            return player_row['Crewmate MMR']
        else:
            return None


    def get_player_imp_mmr(self, player_row):
        if player_row is not None and not player_row.empty:
            return player_row['Impostor MMR']
        else:
            return None


    def get_player_voting_accuracy(self, player_row):
        if player_row is not None and not player_row.empty:
            return player_row['Voting Accuracy (Crewmate games)']
        else:
            return None


    def is_player_in_leaderboard(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            return not player_row.empty
        else:
            return False
    

    def get_player_crew_win_rate(self, player_row):
        if player_row is not None and not player_row.empty:
            crew_games_won = player_row['Number Of Crewmate Games Won']
            crew_games_played = player_row['Number Of Crewmate Games Played']
            if crew_games_played > 0:
                return (crew_games_won / crew_games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None
        

    def get_player_imp_win_rate(self, player_row):
        if player_row is not None and not player_row.empty:
            impostor_games_won = player_row['Number Of Impostor Games Won']
            impostor_games_played = player_row['Number Of Impostor Games Played']
            if impostor_games_played > 0:
                return (impostor_games_won / impostor_games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None
        

    def get_player_win_rate(self, player_row):
        if player_row is not None and not player_row.empty:
            games_won = player_row['Number Of Games Won']
            games_played = player_row['Total Number Of Games Played']
            if games_played > 0:
                return (games_won / games_played) * 100
            else:
                return 0  # Prevent division by zero
        else:
            return None
        

    def get_player_discord(self, player_row):
        if player_row is not None and not player_row.empty:
            discord_id = player_row['Player Discord']
            if discord_id:  # Check if the Discord ID is not empty
                return discord_id
        return None
    

    def get_player_by_discord(self, discord_id):
        row = self.leaderboard[self.leaderboard['Player Discord'] == str(discord_id)]
        if not row.empty:
            row.reset_index(inplace=True, drop=False)
            return row.iloc[0]
        else:
            return None


    def add_player_discord(self, player_name, discord_id):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            index = player_row['Rank']
            self.leaderboard.at[index, 'Player Discord'] = str(discord_id)
            self.save_leaderboard()
            return True
        else:
            return False


    def delete_player_discord(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            index = player_row['Rank'] 
            self.leaderboard.at[index, 'Player Discord'] = ""
            self.save_leaderboard()
            return True
        else:
            return False
    

    def players_with_empty_discord(self):
        players_with_empty_discord = self.leaderboard[self.leaderboard['Player Discord'].isnull()]
        if not players_with_empty_discord.empty:
            return players_with_empty_discord
        else:
            return None


    def top_players_by_mmr(self, top=10):
        if top == "": top = 10
        top_players = self.leaderboard.nlargest(top, 'MMR')[['Player Name', 'MMR']]
        return top_players


    def top_players_by_impostor_mmr(self, top=10):
        if top == "": top = 10
        top_impostors = self.leaderboard.nlargest(top, 'Impostor MMR')[['Player Name', 'Impostor MMR']]
        top_impostors.columns = ['Player Name', 'Impostor MMR']
        top_impostors.reset_index(drop=True, inplace=True)
        top_impostors.index.name = 'Rank'
        return top_impostors


    def top_players_by_crewmate_mmr(self, top=10):
        if top == "":
            top = 10
        top_crewmates = self.leaderboard.nlargest(top, 'Crewmate MMR')[['Player Name', 'Crewmate MMR']]
        top_crewmates.columns = ['Player Name', 'Crewmate MMR']
        top_crewmates.reset_index(drop=True, inplace=True)
        top_crewmates.index.name = 'Rank'
        return top_crewmates
    

    def is_player_sherlock(self, player_name):
        best_crewmate = self.leaderboard[['Player Name', 'Crewmate MMR']].sort_values(by='Crewmate MMR', ascending=False).head(1)
        crewmate_name = best_crewmate.iloc[0]['Player Name']
        if fuzz.ratio(player_name.lower().strip(), crewmate_name.lower().strip()) >= 85:
            return True
        else:
            return False
    

    def is_player_jack_the_ripper(self, player_name):
        best_impostor = self.leaderboard[['Player Name', 'Impostor MMR']].sort_values(by='Impostor MMR', ascending=False).head(1)
        impostor_name = best_impostor.iloc[0]['Player Name']
        if fuzz.ratio(player_name.lower().strip(), impostor_name.lower().strip()) >= 85:
            return True
        else:
            return False
        

    def is_player_ace(self, player_name):
        best_overall = self.leaderboard[['Player Name', 'MMR']].head(1)
        player = best_overall.iloc[0]['Player Name']
        if fuzz.ratio(player_name.lower().strip(), player.lower().strip()) >= 85:
            return True
        else:
            return False
    
    
    def mmr_change(self, player_row, value):
        value = int(value)
        index = player_row['Rank']
        self.leaderboard.at[index, 'MMR'] += value
        self.leaderboard.at[index, 'MMR'] = round(self.leaderboard.at[index, 'MMR'],3)
        self.leaderboard.at[index, 'Crewmate MMR'] += value
        self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
        self.leaderboard.at[index, 'Impostor MMR'] += value
        self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
        self.save_leaderboard()


    
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
# print(leaderboard.get_player_mmr('aiden'))

# print(df)
# df.to_csv("csv.csv")