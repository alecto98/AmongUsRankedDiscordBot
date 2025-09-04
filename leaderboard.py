import pandas as pd
from player_in_match import PlayerInMatch
from match_class import Match
from rapidfuzz import process
from rapidfuzz import fuzz
import os
import yaml

# Load config from YAML
with open(os.path.join('config', 'config.yaml'), 'r', encoding='utf-8') as f:
    all_configs = yaml.safe_load(f)
use_config = all_configs['use'] if 'use' in all_configs else 'main'
config = all_configs[use_config]

class Leaderboard:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.dtype_dict = {
            'Rank': 'Int64', 'Player Name': 'object',
            'Player Discord': 'Int64', 'MMR': 'float64', 'Crewmate MMR': 'float64', 'Impostor MMR': 'float64',
            'Voting Accuracy (Crewmate games)': 'float64', 'Total Number Of Games Played': 'Int64',
            'Number Of Impostor Games Played': 'Int64', 'Number Of Crewmate Games Played': 'Int64',
            'Number Of Impostor Games Won': 'Int64', 'Number Of Crewmate Games Won': 'Int64',
            'Number Of Games Won': 'Int64', 'Number Of Games Died First': 'Int64',
            'Voted Wrong on Crit': 'Int64', 
            'Voted Right on Crit but Lost': 'Int64',
            'Crewmate Win Streak': 'Int64', 'Best Crewmate Win Streak': 'Int64',
            'Impostor Win Streak': 'Int64', 'Best Impostor Win Streak': 'Int64',
            'Survivability (Crewmate)': 'float64', 'Survivability (Impostor)': 'float64'
        }
        self.load_leaderboard()

    def load_leaderboard(self):
        if not os.path.exists(self.csv_file):
            # Create empty leaderboard if file doesn't exist
            self.create_empty_leaderboard()
            self.save()
            return

        try:
            self.leaderboard = pd.read_csv(self.csv_file, dtype=self.dtype_dict)
            self.leaderboard.set_index('Rank', inplace=True)
            self.leaderboard.fillna(0, inplace=True)
        except ValueError as e:
            print(f"Error loading CSV: {e}")
            print("Attempting to load with more flexible dtypes...")
            self.leaderboard = pd.read_csv(self.csv_file)
            for col, dtype in self.dtype_dict.items():
                if col in self.leaderboard.columns:
                    try:
                        self.leaderboard[col] = self.leaderboard[col].astype(dtype)
                    except ValueError:
                        print(f"Could not convert column {col} to {dtype}. Keeping original dtype.")
            self.leaderboard.set_index('Rank', inplace=True)
            self.leaderboard.fillna(0, inplace=True)

    def create_empty_leaderboard(self):
        self.leaderboard = pd.DataFrame(columns=self.dtype_dict.keys()).astype(self.dtype_dict)
        self.leaderboard.set_index('Rank', inplace=True)

    def save(self):
        self.leaderboard.to_csv(self.csv_file, float_format='%.2f')

    def new_player(self, player_name:str):
        new_player_data = {
            'Player Name': player_name.strip(),
            'Player Discord': 0,
            'MMR': float(config['current_mmr']),
            'Crewmate MMR': float(config['crewmate_current_mmr']),
            'Impostor MMR': float(config['impostor_current_mmr'])
        }
        self.leaderboard = pd.concat([self.leaderboard, pd.DataFrame([new_player_data])], ignore_index=True)
        self.rank_players()

    def canceled_new_player_row(self, player_name:str):
        new_player_data = {
            'Player Name': player_name.strip(),
            'Player Discord': 0,
            'MMR': float(config['current_mmr']),
            'Crewmate MMR': float(config['crewmate_current_mmr']),
            'Impostor MMR': float(config['impostor_current_mmr'])
        }
        return pd.Series(new_player_data)

    def update_player(self, player: PlayerInMatch):
        player_row = self.get_player_row(player.name)
        index = player_row['Rank']
        self.leaderboard.at[index, 'MMR'] += player.mmr_gain
        self.leaderboard.at[index, 'MMR'] = round(self.leaderboard.at[index, 'MMR'],3)
        self.leaderboard.at[index, 'Crewmate MMR'] += player.crewmate_mmr_gain
        self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
        self.leaderboard.at[index, 'Impostor MMR'] += player.impostor_mmr_gain
        self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
        self.rank_players()
        
    def rank_players(self):
        if len(self.leaderboard) > 1:
            self.leaderboard.sort_values(by='MMR', ascending=False, inplace=True, kind='mergesort')
            self.leaderboard.reset_index(drop=True, inplace=True)
        self.leaderboard.index.name = 'Rank'

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
            if discord_id != 0 and discord_id is not None:  # Check if the Discord ID is not empty
                return discord_id
        return 0

    def get_player_by_discord(self, discord_id):
        row = self.leaderboard[self.leaderboard['Player Discord'] == int(discord_id)]
        if not row.empty:
            row.reset_index(inplace=True, drop=False)
            return row.iloc[0]
        else:
            return None

    def add_player_discord(self, player_name, discord_id):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            discord_id = int(discord_id) 
            index = player_row['Rank']  
            self.leaderboard.at[index, 'Player Discord'] = discord_id  
            self.save()  
            return True
        else:
            return False

    def delete_player_discord(self, player_name):
        player_row = self.get_player_row(player_name)
        if player_row is not None and not player_row.empty:
            index = player_row['Rank'] 
            self.leaderboard.at[index, 'Player Discord'] = 0
            self.save()
            return True
        else:
            return False

    def players_with_empty_discord(self):
        players_with_empty_discord = self.leaderboard[self.leaderboard['Player Discord'] == 0]
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
        value = float(value)
        index = player_row['Rank']
        self.leaderboard.at[index, 'Crewmate MMR'] += value
        self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
        self.leaderboard.at[index, 'Impostor MMR'] += value
        self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
        self.leaderboard.at[index, 'MMR'] = round((self.leaderboard.at[index, 'Crewmate MMR']+self.leaderboard.at[index, 'Impostor MMR'])/2,3)
        self.save()

    def mmr_change_crew(self, player_row, value):
        value = float(value)
        index = player_row['Rank']
        self.leaderboard.at[index, 'Crewmate MMR'] += value
        self.leaderboard.at[index, 'Crewmate MMR'] = round(self.leaderboard.at[index, 'Crewmate MMR'], 3)
        self.leaderboard.at[index, 'MMR'] = round((self.leaderboard.at[index, 'Crewmate MMR']+self.leaderboard.at[index, 'Impostor MMR'])/2,3)
        self.save()

    def mmr_change_imp(self, player_row, value):
        value = float(value)
        index = player_row['Rank']
        self.leaderboard.at[index, 'Impostor MMR'] += value
        self.leaderboard.at[index, 'Impostor MMR'] = round(self.leaderboard.at[index, 'Impostor MMR'], 3)
        self.leaderboard.at[index, 'MMR'] = round((self.leaderboard.at[index, 'Crewmate MMR']+self.leaderboard.at[index, 'Impostor MMR'])/2,3)
        self.save()

    # Add other methods as needed


# print(match_z.players.__dict__)
# print(match_z.__dict__)
# for player in match_z.players.players:
#     print(player.__dict__)
# print(match_z.players.players[0].__dict__)
# Example usage:
# leaderboard = Leaderboard('leaderboard_fullz.json')
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