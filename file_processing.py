import pandas as pd
import os
from player_in_match import PlayerInMatch
from match_class import Match
from leaderboard import Leaderboard
from leaderboard_events import EventsLeaderboard
from datetime import datetime
import json
import logging
import yaml

# Load config from YAML
with open(os.path.join('config', 'config.yaml'), 'r', encoding='utf-8') as f:
    all_configs = yaml.safe_load(f)
use_config = all_configs['use'] if 'use' in all_configs else 'main'
config = all_configs[use_config]

class FileHandler:
    def __init__(self, matches_path, season_name:str):
        self.season_name = season_name.replace(" ", "_")
        logging.getLogger("os").setLevel(logging.CRITICAL)
        logging.getLogger("pandas").setLevel(logging.CRITICAL)
        logging.getLogger("json").setLevel(logging.CRITICAL)
        logging.getLogger("datetime").setLevel(logging.CRITICAL)
        logging.basicConfig(level=logging.INFO, encoding='utf-8', format="%(asctime)s [%(levelname)s] %(message)s")
        self.logger = logging.getLogger('FileHandler')
        self.matches_path = os.path.expanduser(matches_path)
        self.leaderboard = Leaderboard(f"{self.season_name}_leaderboard.csv")
        self.events_leaderboard = EventsLeaderboard(f"{self.season_name}_events.csv")
        self.special_matches_file = config['special_matches_file']  # Add this line

    def parse_time(self, time_str):
        """Parse time robustly; if missing or malformed, return a safe minimal datetime."""
        if not time_str:
            self.logger.warning("Missing game start time; defaulting to minimal datetime")
            return datetime.min

        time_formats = ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"]
        for time_format in time_formats:
            try:
                return datetime.strptime(str(time_str), time_format)
            except ValueError:
                continue

        self.logger.warning(f"Time format not recognized: {time_str}; defaulting to minimal datetime")
        return datetime.min

    def df_from_json(self, path, json_file):
        # Load match JSON and normalize keys to lowercase
        match_path = os.path.join(path, json_file)
        with open(match_path, 'r', encoding='utf-8') as f:
            match_obj = json.load(f)
        match_norm = {str(k).lower(): v for k, v in match_obj.items()}

        # Load events JSON and normalize keys to lowercase
        events_file = match_norm.get('eventslogfile')
        events_path = os.path.join(path, events_file)
        with open(events_path, 'r', encoding='utf-8') as f:
            events_raw = json.load(f)
        if isinstance(events_raw, list):
            events_norm = [{str(k).lower(): v for k, v in ev.items()} for ev in events_raw]
        elif isinstance(events_raw, dict):
            # Some files might be dict of events
            events_norm = [{str(k).lower(): v for k, v in events_raw.items()}]
        else:
            events_norm = []

        match_df = pd.Series(match_norm)
        events_df = events_norm
        return match_df, events_df

    def get_players_info_from_leaderboard(self, match : Match):
        players = match.players
        player : PlayerInMatch
        for player in players:
            old_player = self.leaderboard.is_player_in_leaderboard(player.name)
            if not old_player and match.result.lower() not in {"canceled", "unknown"}:
                self.leaderboard.new_player(player.name)
            if not old_player and match.result.lower() in {"canceled", "unknown"}:
                player_row = self.leaderboard.canceled_new_player_row(player.name)
            else:
                player_row = self.leaderboard.get_player_row(player.name)
            player.current_mmr = self.leaderboard.get_player_mmr(player_row)
            player.crewmate_current_mmr = self.leaderboard.get_player_crew_mmr(player_row)
            player.impostor_current_mmr = self.leaderboard.get_player_imp_mmr(player_row)
            player.discord = self.leaderboard.get_player_discord(player_row)

    def match_from_dataframe(self, match_df, events_df, k=32) -> Match:
        player:PlayerInMatch
        self.logger.debug(f"Filling Match {match_df['matchid']} object from the events file")
        match = Match(id=match_df['matchid'], match_start_time=match_df['gamestarted'],
                      result=match_df['result'], event_file_name=match_df['eventslogfile'], players = [], k=k)

        players_array = [x.strip() for x in match_df['players'].split(',')]
        impostors_array = [x.strip() for x in match_df['impostors'].split(",")]
        match.impostors = str(impostors_array)
        for player_name in players_array:
            team = "impostor" if player_name in impostors_array else "crewmate"
            match.add_player(PlayerInMatch(name=player_name, team=team))

        self.get_players_info_from_leaderboard(match)
        for player in match.players:
            player.won = (player.team.lower() == 'crewmate' and match.result.lower() in ["crewmates win", "humansbyvote", "humansbytask"]) or \
                        (player.team.lower() == 'impostor' and match.result.lower().startswith("impostor"))

        death_happened = False
        meeting_called_after_death = False
        match.match_end_time = match_df['gamestarted']
        players_alive = len(players_array)
        imps_alive = len(impostors_array)

        match.crewmates_count = players_alive - imps_alive
        match.impostors_count = imps_alive
        player : PlayerInMatch
        imp : PlayerInMatch

        for event in events_df:
            event_type = event.get('event')
            if event_type == "Task":
                player_name = event.get('name')
                player = match.get_player_by_name(player_name)
                player.finished_task()
                if player.tasks_complete == 10:
                    if player.alive:
                        player.finished_tasks_alive = True
                    else:
                        player.finished_tasks_dead = True

            elif event_type == "Death":
                player_name = event.get('name')
                if (match.get_player_by_name(player_name).alive == False):
                    continue
                players_alive -= 1 # one player killed
                death_happened = True
                match.get_player_by_name(player_name).alive = False
                match.get_player_by_name(player_name).time_of_death = event.get('time')
                match.get_player_by_name(player_name).rounds_survived = match.rounds
                if meeting_called_after_death:
                    match.get_player_by_name(player_name).died_first_round = False
                else:
                    match.get_player_by_name(player_name).died_first_round = True

                killer = match.get_player_by_name(event.get('killer'))
                if killer is not None:
                    killer.got_a_kill()
                    if killer.solo_imp: killer.kills_as_solo_imp += 1
                if match.match_end_time < event.get('time'):
                    match.match_end_time = event.get('time')

            elif event_type == "BodyReport":
                meeting_called_after_death = True

            elif event_type == "MeetingStart":
                if death_happened:
                    meeting_called_after_death = True

            elif event_type == "PlayerVote":
                if death_happened:
                    meeting_called_after_death = True

                player_name = event.get('player')

                if str(event.get('target')).lower() =='none':
                    match.get_player_by_name(player_name).skipped_vote()

                elif match.is_player_imp(event.get('target')):
                    match.get_player_by_name(player_name).correct_vote()

                else:
                    match.get_player_by_name(player_name).incorrect_vote()

                match.get_player_by_name(player_name).last_voted = event.get('target')

                if match.match_end_time < event.get('time'):
                    match.match_end_time = event.get('time')


            elif event_type == "Exiled":
                ejected_player_name = event.get('player')
                if match.get_player_by_name(ejected_player_name).alive == False: continue
                match.get_player_by_name(ejected_player_name).alive = False
                match.get_player_by_name(ejected_player_name).time_of_death = event.get('time')
                match.get_player_by_name(ejected_player_name).rounds_survived = match.rounds
                match.get_player_by_name(ejected_player_name).ejected_in_meeting = True

                if match.is_player_imp(ejected_player_name):
                    imps_alive -= 1
                    if players_alive >= 7:
                        impostors = match.get_players_by_team("impostor")
                        for player in impostors:
                            if player.name == ejected_player_name:
                                player.ejected_early_as_imp = True
                            else:
                                player.solo_imp = True
                                match.solo_imp_game = True
                    for player in match.get_players_by_team("crewmate"):
                        if player.last_voted == ejected_player_name and player.alive: #crewmate voted an imp out
                            player.correct_vote_on_eject.append([players_alive, 1])

                else: # voted a crewmate or skipped
                    for player in match.players:
                        if player.alive:
                            if player.last_voted == ejected_player_name and player.team == "crewmate":
                                player.got_crew_voted.append([players_alive, 1]) # all players who voted out a crewmate

                            elif player.team == "impostor":
                                player.got_crew_voted.append([players_alive, 1])

                            if ((players_alive in [3,4]) or ((players_alive in [5,6,7]) and (imps_alive == 2))) and player.team == "crewmate" and not player.won: #crit
                                if match.is_player_imp(player.last_voted):
                                    player.right_vote_on_crit_but_loss = True

                                elif players_alive in [3,5,6]:
                                    player.voted_wrong_on_crit = True
                                elif players_alive in [4,7] and (player.last_voted != "Skipped" and player.last_voted != "none"):
                                    player.voted_wrong_on_crit = True

                players_alive -= 1 # one player ejected
                if imps_alive == 0 or (players_alive==1 and imps_alive==1) or (players_alive==2 and imps_alive==2): #game ended
                    pass
                else:
                    match.rounds+=1

            elif event_type == "MeetingEnd" and (event.get("result") == "Skipped" or event.get("result") == "Tie"):
                match.rounds+=1
                if (((players_alive in [5,6]) and (imps_alive == 2)) or players_alive == 3):
                    for player in match.players:
                        if not player.alive: continue
                        if player.team == "crewmate" and not player.won:
                            if (player.last_voted == "none" or player.last_voted == None or player.last_voted == "missed" or not match.is_player_imp(player.last_voted)):
                                player.voted_wrong_on_crit = True
                            elif match.is_player_imp(player.last_voted):
                                player.right_vote_on_crit_but_loss = True

        match_start_time = self.parse_time(match.match_start_time)
        match_end_time = self.parse_time(match.match_end_time)
        match.match_duration = str(match_end_time - match_start_time)
        for player in match.players:
            player.match_id = match.id
            player.match_result = match.result
            player.total_rounds = match.rounds
            player.voting_accuracy = player.number_of_correct_votes / (player.number_of_placed_votes - player.number_of_skip_votes) if player.team == 'crewmate' and (player.number_of_placed_votes - player.number_of_skip_votes) != 0 else 0
            if player.time_of_death is None:
                player.time_of_death = match.match_end_time
            time_of_death = self.parse_time(player.time_of_death)
            player.alive_time = str(time_of_death - match_start_time)
            player.match_time = match.match_duration
            if player.match_result == "Impostors Win" and player.solo_imp:
                player.won_as_solo_imp = True
        match.alive_players = players_alive
        match.alive_impostors = imps_alive
        for player in match.players:
            if match.get_player_by_name(player.name).rounds_survived == 0:
                match.get_player_by_name(player.name).rounds_survived = match.rounds
        return match

    def match_from_file(self, json_file=None, k=32) -> Match:
        try:
            match_df, events_df = self.df_from_json(self.matches_path, json_file)
        except Exception as e:
            error_message = f"Error reading match from file {json_file}: {str(e)}"
            self.logger.error(error_message)
            return None

        if match_df is None or events_df is None:
            error_message = f"Error with file {json_file}: {match_df} {events_df}"
            self.logger.error(error_message)
            return None

        match_id = match_df['matchid']

        # Check if this is a special match
        try:
            special_matches_df = pd.read_csv(self.special_matches_file)
            special_match = special_matches_df[special_matches_df['match_id'] == match_id]
            if not special_match.empty:
                # Get the multiplier type and set appropriate k value
                multiplier = special_match.iloc[0]['multiplier']
                k = 64 if multiplier == 'double' else 96 if multiplier == 'triple' else 32
                self.logger.info(f"Processing special match {match_id} with {multiplier} multiplier (k={k})")
        except Exception as e:
            self.logger.error(f"Error checking special matches file: {str(e)}")
            # Continue with default k value if there's an error
            pass

        match = self.match_from_dataframe(match_df, events_df, k=k)
        match.match_file_name = json_file
        if match.result in ["Canceled", "Unknown"]:
            return match

        match.calculate_avg_mmr()
        match.calculate_percentage_of_winning()
        match.calculate_mmr()
        return match

    def get_sorted_match_files(self):
        def get_game_started_timestamp(file_name):
            file_path = os.path.join(self.matches_path, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
            except Exception as e:
                self.logger.error(f"Failed to read match file {file_name}: {e}")
                return datetime.min

            # Prefer 'gameStarted' then fallback
            game_started = data.get("gameStarted") or data.get("gamestarted") or data.get("GameStarted") or data.get("GameStart")
            game_started_time = self.parse_time(game_started)
            return game_started_time

        files = os.listdir(self.matches_path)
        filtered_files = [file for file in files if "match.json" in file.lower()]
        # Sort with robust key; files without timestamps will be first (datetime.min)
        sorted_files = sorted(filtered_files, key=lambda x: get_game_started_timestamp(x))
        return sorted_files

    def update_leaderboard(self, match:Match):
        for player in match.players:
            self.leaderboard.update_player(player)
        self.leaderboard.save()

    def fully_update_lb(self):
        player_stats = self.events_leaderboard.stats_leaderboard()
        if self.leaderboard.leaderboard.index.name != 'Player Name':
            self.leaderboard.leaderboard.reset_index(inplace=True)
            self.leaderboard.leaderboard.set_index('Player Name', inplace=True)
        self.leaderboard.leaderboard.update(player_stats)
        self.leaderboard.leaderboard.reset_index(inplace=True)
        self.leaderboard.leaderboard.set_index('Rank', inplace=True)
        self.leaderboard.leaderboard = self.leaderboard.leaderboard.fillna(0)
        self.leaderboard.save()

    def process_match_by_id(self, match_id, k=32):
        processed_matches = set(self.events_leaderboard.events_lb['Match ID'].unique())
        match_file_name = self.find_matchfile_by_id(match_id)
        match = self.match_from_file(match_file_name, k=k)
        if match_id in processed_matches:
            self.logger.info(f"Match {match_id} has already been processed - skipping")
            return match
        if match.result != "Unknown":
            self.events_leaderboard.add_match_events(match=match)
        if match.result != "Canceled" and match.result != "Unknown":
            self.update_leaderboard(match)
            self.fully_update_lb()
            self.logger.info(f"Match {match_id} has been added to the leaderboard")
        else:
            self.logger.info(f"Match {match_id} is a Cancel - skipping")
        
        return match

    def process_unprocessed_matches(self):
        processed_matches = set(self.events_leaderboard.events_lb['Match ID'].unique())
        sorted_files_with_match = self.get_sorted_match_files()
        match = None
        special_matches_df = None
        try:
            special_matches_df = pd.read_csv(config['special_matches_file'])
        except Exception as e:
            self.logger.error(f"Error loading special matches file: {str(e)}")

        # Check if this is a fresh calculation (events file is empty)
        is_fresh_calculation = len(self.events_leaderboard.events_lb) == 0
        if is_fresh_calculation:
            self.logger.info("Events file is empty - this is a fresh calculation, will apply stored MMR changes after processing")

        for file in sorted_files_with_match:
            try:
                with open(os.path.join(self.matches_path, file), 'r') as f:
                    match_data = json.load(f)
                    match_id = match_data.get('MatchID') or match_data.get('matchid')
                    if match_id in processed_matches:
                        continue

                    # Check if it's a special match
                    k = 32  # default k value
                    if special_matches_df is not None and match_id:
                        special_match = special_matches_df[special_matches_df['match_id'] == match_id]
                        if not special_match.empty:
                            multiplier = special_match.iloc[0]['multiplier']
                            k = 64 if multiplier == 'double' else 96 if multiplier == 'triple' else 32
                            self.logger.info(f"Found special match {match_id} with {multiplier} multiplier (k={k})")

                    # Create match with appropriate k value
                    match = self.match_from_file(file, k=k)

                    if match:
                        self.events_leaderboard.add_match_events(match)
                        if match.result == "Canceled" or match.result == "Unknown":
                            self.logger.info(f"Skipped {match.match_file_name} because result is {match.result}")
                        elif len(match.players) != 10:
                            self.logger.info(f"Skipped {match.match_file_name} because it doesn't have 10 players")
                        else:
                            self.logger.info(f"Processed Match ID:{match.id}")
                            self.update_leaderboard(match)
                    processed_matches.add(match_id) # Add match_id to processed_matches set

            except Exception as e:
                self.logger.error(f"Error processing file {file}: {str(e)}")
                continue
        self.fully_update_lb()
        
        # Only apply stored MMR changes if this was a fresh calculation
        if is_fresh_calculation:
            self.logger.info("Applying stored MMR changes after fresh calculation...")
            self.apply_stored_mmr_changes()
        else:
            self.logger.info("Skipping stored MMR changes - this was not a fresh calculation")
        
        return match

    def find_matchfile_by_id(self, match_id):
        json_files = [file for file in os.listdir(self.matches_path) if file.endswith('_match.json')]
        for match_file_name in json_files:
            match_file_path = os.path.join(self.matches_path, match_file_name)
            with open(match_file_path, 'r') as f:
                match_data = json.load(f)
                found_id = match_data.get('MatchID') or match_data.get('matchid')
                if str(found_id) == str(match_id):
                    return match_file_name
        return None

    def change_player_name(self, old_name, new_name):
        def read_json_file(filename):
            with open(os.path.join(self.matches_path, filename), 'r') as file:
                return json.load(file)

        def write_json_file(filename, data):
            with open(os.path.join(self.matches_path, filename), 'w') as file:
                json.dump(data, file, indent=4)

        player_row = self.leaderboard.get_player_row(old_name)
        if player_row is None:
            return False

        index = player_row['Rank']
        self.leaderboard.leaderboard.at[index, 'Player Name'] = new_name
        self.leaderboard.save()
        self.logger.info(f"Player name '{old_name}' updated to '{new_name}' in Leaderboard")
        self.events_leaderboard.events_lb.loc[self.events_leaderboard.events_lb['Player Name'] == player_row['Player Name'], 'Player Name'] = new_name
        self.events_leaderboard.save()
        self.logger.info(f"Player name '{old_name}' updated to '{new_name}' in Events Leaderboard")

        for filename in os.listdir(self.matches_path):
            if filename.endswith('.json'):
                data = read_json_file(filename)
                change_made = False

                if 'players' in data:
                    players = data['players'].split(',')
                    for player in players: player = player.rstrip()
                    if old_name in players:
                        players[players.index(old_name)] = new_name
                        data['players'] = ','.join(players)
                        self.logger.debug(f"Player name '{old_name}' updated to '{new_name}' in {filename}")
                        change_made = True
                    impostors = data.get('impostors', '').split(',')
                    for imp in impostors: imp = imp.rstrip()
                    if old_name in impostors:
                        impostors[impostors.index(old_name)] = new_name
                        data['impostors'] = ','.join(impostors)
                        self.logger.debug(f"Impostor name '{old_name}' updated to '{new_name}' in {filename}")
                        change_made = True

                if isinstance(data, list):
                    for event in data:
                        # Normalize event keys to lowercase for in-place updates
                        if any(k for k in event.keys() if k != k.lower()):
                            keys_lower = {k: event[k] for k in list(event.keys())}
                            for k in list(keys_lower.keys()):
                                if k != k.lower():
                                    event[k.lower()] = keys_lower[k]
                                    del event[k]
                        for key in ['name', 'player', 'target', 'killer','deadplayer', 'impostors']:
                            if key in event:
                                if isinstance(event[key], str) and event[key].endswith(" |"):
                                    event[key] = event[key][:-2]
                                if event[key] == old_name:
                                    change_made = True
                                    event[key] = new_name
                                if key == 'impostors' and isinstance(event[key], str):
                                    if old_name in event[key].split(','):
                                        event[key] = event[key].replace(old_name, new_name)
                                        change_made = True
                if change_made:
                    write_json_file(filename, data)
                    self.logger.debug(f"Player name '{old_name}' updated to '{new_name}' in {filename}")
        return True

    def apply_stored_mmr_changes(self):
        """Apply all stored MMR changes from the CSV file"""
        try:
            mmr_changes_file = 'mmr_changes.csv'
            if not os.path.exists(mmr_changes_file):
                self.logger.info("No MMR changes file found, skipping stored changes")
                return
                
            df = pd.read_csv(mmr_changes_file)
            if df.empty:
                self.logger.info("MMR changes file is empty, skipping stored changes")
                return
                
            self.logger.info(f"Applying {len(df)} stored MMR changes...")
            
            for index, row in df.iterrows():
                try:
                    player_name = row['Player Name']
                    mmr_value = float(row['MMR Value'])
                    change_type = row['Change Type']
                    moderator = row['Moderator']
                    reason = row.get('Reason', '')
                    
                    # Get player row
                    player_row = self.leaderboard.get_player_row(player_name)
                    if player_row is None:
                        self.logger.warning(f"Player {player_name} not found in leaderboard, skipping MMR change")
                        continue
                    
                    # Apply the MMR change based on type
                    if change_type == 'crew':
                        self.leaderboard.mmr_change_crew(player_row, mmr_value)
                        change_text = "Crew"
                    elif change_type == 'imp':
                        self.leaderboard.mmr_change_imp(player_row, mmr_value)
                        change_text = "Impostor"
                    else:  # total
                        self.leaderboard.mmr_change(player_row, mmr_value)
                        change_text = "Total"
                    
                    self.logger.info(f"Applied stored MMR change: {player_name} {mmr_value:+} ({change_text}) by {moderator}")
                    
                except Exception as e:
                    self.logger.error(f"Error applying stored MMR change at row {index}: {str(e)}")
                    continue
            
            self.logger.info("Finished applying stored MMR changes")
            
        except Exception as e:
            self.logger.error(f"Error applying stored MMR changes: {str(e)}")

    def match_info_by_id(self, match_id):
        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not generate info for this match")
            return None
        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        return match_data

    def change_match_result(self, match_id, new_result:str)->tuple[Match, str]:
        new_result_lower = new_result.lower()
        if new_result_lower.startswith('crew'):
            result = 'Crewmates Win'
        elif new_result_lower.startswith('imp'):
            result = 'Impostors Win'
        elif new_result_lower.startswith('canc'):
            result = 'Canceled'
        else:
            return False, "Wrong input"

        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not change match to {result}")
            return False, f"Can't find {match_id} - Could not change match to {result}"

        match = self.match_from_file(match_file_name)
        if match.result == result:
            self.logger.info(f"Match {match_id} is already a {result}")
            return False, f"Match {match_id} is already a {result}"

        self.logger.info(f"Changing match {match_id} to {result}")
        match_rows = self.events_leaderboard.events_lb[self.events_leaderboard.events_lb['Match ID'] == match_id]

        self.leaderboard.leaderboard.reset_index(inplace=True)
        changes_df = match_rows[['Player Name', 'MMR Gain', 'Crewmate MMR Gain', 'Impostor MMR Gain']].set_index('Player Name')
        self.leaderboard.leaderboard = self.leaderboard.leaderboard.set_index('Player Name').join(changes_df, how='left')
        for change_col, target_col in zip(['MMR Gain', 'Crewmate MMR Gain', 'Impostor MMR Gain'], ['MMR', 'Crewmate MMR', 'Impostor MMR']):
            self.leaderboard.leaderboard[target_col] -= self.leaderboard.leaderboard[change_col].fillna(0)
        self.leaderboard.leaderboard.drop(columns=['MMR Gain', 'Crewmate MMR Gain', 'Impostor MMR Gain'], inplace=True)
        self.leaderboard.leaderboard.reset_index(inplace=True)
        self.leaderboard.leaderboard.set_index('Rank', inplace=True)

        match.result = result
        self.events_leaderboard.remove_match(match_id)

        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        match_data['result'] = result
        with open(file_path, 'w') as f:
            json.dump(match_data, f, indent=4)

        self.process_match_by_id(match_id)
        self.events_leaderboard.events_lb = self.events_leaderboard.events_lb.sort_values(by='Match ID')
        self.events_leaderboard.save()

        return match, f"Match {match_id} changed to {result}"


###############################################
# path = "~/Resistance/Full_Matches/"
# path = "~/Resistance/crit/"

# path = "~/plugins/MatchLogs/Preseason"
# path = "c:/Users/Ayman/among us development/AmongUsRankedDiscordBot/Preseason"
# f = FileHandler(path, "preseason")

# print(f.match_from_file("531_match.json").match_details())
# print(f.match_from_file("2310_match.json").match_details())
# print(f.match_from_file("2211_match.json").match_details())

#f.process_unprocessed_matches()
    # await database_manager.add_match(match)
    # await database_manager.add_match(match2)
    # await database_manager.add_match(match3)
# start_time = datetime.now()
# f.process_unprocessed_matches()
# f.leaderboard.save()
# f.events_leaderboard.save()
# f.fully_update_lb()
# end_time = datetime.now()
# print(end_time-start_time)
    # await database_manager.add_match(match2)

    # Your code to add matches or other operations
    # await db.add_match(match)

# match = f.process_match_by_id(25)
# print(match)
# f.mine_matches_data()
# file_name = "QCoX1nqM5o2u11Js_match.json"

# # # f.change_result_to_crew_win(485)
# f.process_unprocessed_matches()
# f.mine_matches_data()
# match = f.match_from_file(file_name)
# f.calculate_mmr_gain_loss(match)
# print(match.match_details())