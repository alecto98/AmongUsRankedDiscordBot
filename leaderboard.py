import pandas as pd
from player_in_match import PlayerInMatch
from match_class import Match

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
            'Player Name', 'Player Discord', 'ELO', 'Crewmate ELO', 'Impostor ELO',
            'Voting Accuracy (Crewmate games)', 'Total Number Of Games Played',
            'Number Of Impostor Games Played', 'Number Of Crewmate Games Played',
            'Number Of Impostor Games Won', 'Number Of Crewmate Games Won',
            'Number Of Games Won', 'Crewmate Win Streak', 'Best Crewmate Win Streak',
            'Impostor Win Streak', 'Best Impostor Win Streak',
            'Previous Games Voting Accuracy',
            'Change In Crewmate ELO', 'Change In Impostor ELO'
        ]
        self.leaderboard = pd.DataFrame(columns=columns)

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
            'Number Of Games Died First': 0 #,
            # 'Best Crewmate Win Streak': 0,
            # 'Impostor Win Streak': 0,
            # 'Best Impostor Win Streak': 0,
            # 'Previous Games Voting Accuracy': pd.DataFrame([], columns=['Accuracy List']),
            # 'Change In Crewmate ELO': pd.DataFrame([], columns=['Change In Crewmate ELO']),
            # 'Change In Impostor ELO': pd.DataFrame([], columns=['Change In Impostor ELO'])
        }
        self.leaderboard = pd.concat([self.leaderboard, pd.DataFrame([new_player_data])], ignore_index=True)
        self.save_leaderboard()

    def update_player(self, player: PlayerInMatch):
        player_row = self.leaderboard[self.leaderboard['Player Name'] == player.name]
        if player_row.empty:
            self.new_player(player.name)
            player_row = self.leaderboard[self.leaderboard['Player Name'] == player.name]
        index = player_row.index[0]

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
        
    def rank_players(self):
        self.leaderboard = self.leaderboard.sort_values(by='ELO', ascending=False)
        self.leaderboard.reset_index(drop=True, inplace=True)
        self.leaderboard.index.name = 'Rank'

    def get_player_row(self, player_name):
        player_name_short = player_name[:4].lower()
        self.leaderboard['Player Name Short'] = self.leaderboard['Player Name'].str[:4].str.lower()
        player_row = self.leaderboard[self.leaderboard['Player Name Short'] == player_name_short]
        self.leaderboard.drop(columns=['Player Name Short'], inplace=True)
        return player_row
    
    def get_player_ranking(self, player_name):
        player_row = self.get_player_row(player_name)
        if not player_row.empty:
            ranking = player_row.index[0] + 1
            return ranking
        else:
            return None
    
    def get_player_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        return player_row['ELO'].values[0] if not player_row.empty else None

    def get_player_crew_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        return player_row['Crewmate ELO'].values[0] if not player_row.empty else None

    def get_player_imp_elo(self, player_name):
        player_row = self.get_player_row(player_name)
        return player_row['Impostor ELO'].values[0] if not player_row.empty else None

    def is_player_in_leaderboard(self, player_name):
        return not self.get_player_row(player_name).empty

    def add_player_discord(self, player_name, discord_id):
        player_row = self.get_player_row(player_name)
        if not player_row.empty:
            index = player_row.index[0]
            self.leaderboard.at[index, 'Player Discord'] = discord_id
            self.save_leaderboard()



    # Add other methods as needed

# Example usage:
# leaderboard = Leaderboard('leaderboard.csv')

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