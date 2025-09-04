import os
import json
from datetime import datetime

class JsonFileManager:
    def __init__(self, directory):
        self.directory = directory
    
    def read_json_file(self, filename):
        with open(os.path.join(self.directory, filename), 'r') as file:
            return json.load(file)
    
    def write_json_file(self, filename, data):
        with open(os.path.join(self.directory, filename), 'w') as file:
            json.dump(data, file, indent=4)
    
    def sort_and_assign_match_ids(self):
        def read_json_files(directory):
            json_files = []
            for filename in os.listdir(directory):
                if filename.endswith('_match.json'):
                    with open(os.path.join(directory, filename), 'r') as file:
                        json_data = json.load(file)
                        game_started = json_data.get('gameStarted')
                        if game_started:
                            json_files.append((filename, game_started))
            return json_files

        def sort_json_files_by_game_started(json_files):
            return sorted(json_files, key=lambda x: datetime.strptime(x[1], '%m/%d/%Y %H:%M:%S'))

        def assign_match_ids(sorted_json_files):
            for idx, (filename, _) in enumerate(sorted_json_files):
                match_id = str(idx)
                json_data = {'MatchID': idx}
                # Extract events file name from match_data
                events_file_name = None
                # Get events file name from match_data
                with open(os.path.join(self.directory, filename), 'r') as file:
                    match_data = json.load(file)
                    events_file_name = match_data.get('eventsLogFile')
                if events_file_name is None:
                    print(f"Warning: Events file name not found in '{filename}'. Skipping renaming.")
                    continue
                # Construct file paths
                old_events_file = os.path.join(self.directory, events_file_name)
                new_events_file = os.path.join(self.directory, f"{match_id}_events.json")
                # Check if the old events file exists before renaming
                if os.path.exists(old_events_file):
                    os.rename(old_events_file, new_events_file)
                else:
                    print(f"Warning: Old events file '{old_events_file}' not found. Skipping renaming.")
                    continue
                # Rename _match file
                old_match_file = os.path.join(self.directory, filename)
                new_match_file = os.path.join(self.directory, f"{match_id}_match.json")
                os.rename(old_match_file, new_match_file)
                # Update MatchID in the new _match file
                with open(new_match_file, 'r+') as file:
                    match_data['MatchID'] = idx
                    match_data['eventsLogFile'] = f"{match_id}_events.json"
                    # Store the events file name in match_data
                    match_data['eventsFileName'] = new_events_file
                    file.seek(0)
                    json.dump(match_data, file, indent=4)

        json_files = read_json_files(self.directory)
        sorted_json_files = sort_json_files_by_game_started(json_files)
        assign_match_ids(sorted_json_files)
        print("Sorting and assigning MatchIDs completed successfully.")

    def change_player_name(self, player_name, new_name):
        for filename in os.listdir(self.directory):
            if filename.endswith('.json'):
                data = self.read_json_file(filename)
                if 'players' in data:
                    players = data['players'].split(',')
                    if player_name in players:
                        players[players.index(player_name)] = new_name
                        data['players'] = ','.join(players)
                        self.write_json_file(filename, data)
                        print(f"Player name '{player_name}' updated to '{new_name}' in {filename}")

                if isinstance(data, list):
                    for event in data:
                        if 'Name' in event and event['Name'] == player_name:
                            event['Name'] = new_name
                        if 'Player' in event and event['Player'] == player_name:
                            event['Player'] = new_name
                        if 'Target' in event and event['Target'] == player_name:
                            event['Target'] = new_name
                        if 'Killer' in event and event['Killer'] == player_name:
                            event['Killer'] = new_name
                        if 'DeadPlayer' in event and player_name in event['DeadPlayer']:
                            event['DeadPlayer'] = event['DeadPlayer'].replace(player_name, new_name)
                    self.write_json_file(filename, data)
                    print(f"Player name '{player_name}' updated to '{new_name}' in {filename}")

    def clean_trailing_spaces(self):
        """Remove leading/trailing spaces from player names in 'players' and 'impostors' fields of all _match.json files."""
        for filename in os.listdir(self.directory):
            if filename.endswith('_match.json'):
                file_path = os.path.join(self.directory, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                changed = False
                # Clean players
                if 'players' in data:
                    players = [p.strip() for p in data['players'].split(',')]
                    new_players = ','.join(players)
                    if new_players != data['players']:
                        data['players'] = new_players
                        changed = True
                # Clean impostors
                if 'impostors' in data:
                    impostors = [p.strip() for p in data['impostors'].split(',')]
                    new_impostors = ','.join(impostors)
                    if new_impostors != data['impostors']:
                        data['impostors'] = new_impostors
                        changed = True
                if changed:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)
                    print(f"Cleaned: {filename}")
        print("Trailing spaces removed from all player and impostor names in _match.json files.")

# Example usage:
directory = "Preseason"
json_manager = JsonFileManager(directory)
json_manager.clean_trailing_spaces()