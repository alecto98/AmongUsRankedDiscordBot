import os
import json

def find_matches_with_player(player_name, directory):
    matching_files = []

    # Iterate through all files in the directory
    for filename in os.listdir(directory):
        if filename.endswith("_match.json"):  # Check if the file ends with 'match.json'
            file_path = os.path.join(directory, filename)
            with open(file_path, 'r') as file:
                try:
                    match_data = json.load(file)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON in file '{filename}'")
                    continue
                
            # Check if the player name is in the match data
            if player_name in match_data.get("players", []):
                matching_files.append(filename)

    return matching_files

# Example usage:
directory_path = "Preseason/"
player_name = "Aiden 1"
matching_files = find_matches_with_player(player_name, directory_path)
print("Matching files:", matching_files)