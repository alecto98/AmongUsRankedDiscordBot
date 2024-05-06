import pandas as pd
import os
from player_in_match import PlayerInMatch
from players_list import PlayersList
from match_class import Match
from leaderboard import Leaderboard
from datetime import datetime
import json 
import logging
import numpy as np

class FileHandler:
    def __init__(self, matches_path, database_location):
        logging.getLogger("os").setLevel(logging.CRITICAL)
        logging.getLogger("pandas").setLevel(logging.CRITICAL)
        logging.getLogger("json").setLevel(logging.CRITICAL)
        logging.getLogger("datetime").setLevel(logging.CRITICAL)
        logging.basicConfig(level=logging.DEBUG, encoding='utf-8', format="%(asctime)s [%(levelname)s] %(message)s")
        self.logger = logging.getLogger('FileHandler')
        self.matches_path = os.path.expanduser(matches_path)
        self.processed_matches_csv = "processed_matches.csv"
        self.database_location = database_location
        self.leaderboard = Leaderboard(database_location)
        self.match = Match()


    def df_from_json(self, path, json_file):
        match_df = pd.read_json(os.path.join(path, json_file), typ='series')
        events_df = pd.read_json(os.path.join(path, match_df.eventsLogFile), typ='series')
        return match_df, events_df


    def get_players_info_from_leaderboard(self, players_list : PlayersList):
        for player in players_list.players:
            old_player = self.leaderboard.is_player_in_leaderboard(player.name)
            if not old_player:
                self.leaderboard.new_player(player.name)
            player_row = self.leaderboard.get_player_row(player.name)
            player.crewmate_current_mmr = self.leaderboard.get_player_crew_mmr(player_row)
            player.impostor_current_mmr = self.leaderboard.get_player_imp_mmr(player_row)
            player.current_mmr = self.leaderboard.get_player_mmr(player_row)
            player.discord = self.leaderboard.get_player_discord(player_row)


    def get_players_from_df(self, match_df) -> PlayersList:
        players_array = [x.strip() for x in match_df.players.split(',')]
        impostors_array = match_df.impostors.split(", ")
        players_list = PlayersList()
        result = match_df.result
        for player_name in players_array:
            team = "impostor" if player_name in impostors_array else "crewmate"
            players_list.add_player(PlayerInMatch(name=player_name, team=team))
        self.get_players_info_from_leaderboard(players_list)
        # self.logger.debug(f"Imported Players data from leaderboard for match {match_df.MatchID}")
        try:
            players_list.calculate_total_mmr()
            # self.logger.debug(f"Calculated MMR changes for match {match_df.MatchID}")
        except Exception as e:
            self.logger.error(f"Error calculating MMR for match {match_df.eventsLogFile} {e}")

        self.calculate_percentage_of_winning(players_list)
        players_list.who_won(result)
        
        return players_list


    def calculate_percentage_of_winning(self, players:PlayersList):
        def winning_prob(avg_crew_elo, avg_imp_elo):
            def log_function(diff):
                a=0.07416865609596561 
                b=0.02188284234744941
                c=1.3188566776518948
                d=-0.021900704104131766
                return a * np.log(b * diff + c) + d

            difference = avg_crew_elo - avg_imp_elo
            if difference < 0:
                difference = abs(difference)
                prob_change = log_function(difference)
                win_prob = 0.78 - prob_change
                if win_prob < 0.62: win_prob = 0.62
                return win_prob
            else:
                prob_change = log_function(difference)
                win_prob = 0.78 + prob_change
                if win_prob > 0.94: win_prob = 0.94
                return win_prob
            
        players.crewmate_win_rate = winning_prob(players.avg_crewmate_mmr, players.avg_impostor_mmr)
        players.impostor_win_rate = 1 - players.crewmate_win_rate

        for player in players.players:
            if player.team == 'impostor':
                player.pecentage_of_winning = players.impostor_win_rate
            elif player.team == 'crewmate':
                player.pecentage_of_winning = players.crewmate_win_rate

        # a = 0.043290409437842466
        # b = 7.855256175054392
        # c = 98.05742514755777
        # d = -0.19883086302819628


    def match_from_dataframe(self, match_df, events_df, players_list):
        self.logger.debug(f"Filling Match {match_df.MatchID} object from the events file")
        match = Match(id=match_df.MatchID, match_start_time=match_df.gameStarted,
                      result=match_df.result, players=players_list, event_file_name=match_df.eventsLogFile)
        death_happened = False
        meeting_called_after_death = False
        match_end_time = match_df.gameStarted
        players_alive = 10
        imps_alive = 2

        for event in events_df:
            event_type = event.get('Event')
            if event_type == "Task":
                player_name = event.get('Name')
                match.players.get_player_by_name(player_name).finished_task()

            elif event_type == "PlayerVote":
                if death_happened:
                    meeting_called_after_death = True
                    
                player_name = event.get('Player')
                if match.players.is_player_impostor(event.get('Target')):
                    match.players.get_player_by_name(player_name).correct_vote()
                    
                elif event.get('Target') !='none':
                    match.players.get_player_by_name(player_name).incorrect_vote()

                match.players.get_player_by_name(player_name).last_voted = event.get('Target')

                if match_end_time < event.get('Time'):
                    match_end_time = event.get('Time')

            elif event_type == "Death":
                players_alive -= 1 # one player killed
                death_happened = True
                player_name = event.get('Name')
                match.players.get_player_by_name(player_name).alive = False
                match.players.get_player_by_name(player_name).time_of_death = event.get('Time')
                if meeting_called_after_death:
                    match.players.get_player_by_name(player_name).died_first_round = False
                else:
                    match.players.get_player_by_name(player_name).died_first_round = True
                killer = match.players.get_player_by_name(event.get('Killer'))

                if killer and killer.solo_imp: killer.kills_as_solo_imp += 1

            elif event_type == "BodyReport":
                meeting_called_after_death = True

            elif event_type == "MeetingStart":
                if death_happened:
                    meeting_called_after_death = True

            elif event_type == "Exiled":
                ejected_player_name = event.get('Player')
                match.players.get_player_by_name(ejected_player_name).alive = False
                match.players.get_player_by_name(ejected_player_name).time_of_death = event.get('Time')
                ejected_imp = match.players.is_player_impostor(event.get('Player'))
                if ejected_imp:
                    impostors = match.players.get_players_by_team("impostor")
                    for imp in impostors:
                        if imp.name != ejected_player_name and players_alive >= 7:
                            imp.solo_imp = True
                    imps_alive -= 1

                    for player in match.players.players:
                        if players_alive >= 7:
                            player.ejected_early_as_imp = True
                        if player.last_voted == ejected_player_name: #crewmate voted an imp out
                            player.correct_vote_on_eject +=1

                else: # voted a crewmate 
                    for player in match.players.players:
                        if player.last_voted == ejected_player_name: # voted a crewmate out
                            if player.team == "impostor":
                                player.got_crew_voted +=1
                            if player.team == "crewmate":
                                if ((players_alive in [3,4]) or ((players_alive in [5,6,7]) and (imps_alive == 2))) and player.alive:
                                    player.voted_wrong_on_crit = True
                        else: #didn't vote the crewmate who got voted
                            if player.team == "crewmate":
                                if ((players_alive in [3,4]) or ((players_alive in [5,6,7]) and (imps_alive == 2))) and player.alive:
                                    player.right_vote_on_crit_but_loss = True
                players_alive -= 1 # one player ejected

            elif event_type == "MeetingEnd":
                if (event.get("Result") == "Skipped") and ((players_alive in [5,6]) and (imps_alive == 2)) and player.alive:
                    for player in match.players.players:
                        if player.team == "crewmate":
                            if player.last_voted == "none":
                                player.voted_wrong_on_crit = True
                            else: 
                                voted_imp = match.players.is_player_impostor(player.last_voted)
                                if not voted_imp:
                                    player.voted_wrong_on_crit = True

        for player in match.players.players:
            if player.time_of_death is None:
                player.time_of_death = match_end_time
        match.match_end_time = match_end_time
        return match


    def calculate_mmr_gain_loss(self, match):
        for player in match.players.players:
            player.calculate_performance_and_mmr()


    def update_leaderboard(self, match):
        for player in match.players.players:
            self.leaderboard.update_player(player)


    def match_from_file(self, json_file=None) -> Match:
        try:
            match_df, events_df = self.df_from_json(self.matches_path, json_file)
        except Exception as e:
            self.logger.error(str(e)+"Error reading match from file"+str(json_file))
            return None

        if match_df.result in ["Canceled", "Cancelled", "Unknown"] or events_df is None or match_df is None:
            try:
                players_list = self.get_players_from_df(match_df)
                match = self.match_from_dataframe(match_df, events_df, players_list)
                match.match_file_name = json_file
                return match
            except:
                self.logger.error(f"Error with file {match_df.eventsLogFile}")

        players_list = self.get_players_from_df(match_df)
        match = self.match_from_dataframe(match_df, events_df, players_list)
        match.match_file_name = json_file
        return match
        

    def get_sorted_files_with_match(self):
        files = os.listdir(self.matches_path)
        filtered_files = [file for file in files if "match.json" in file.lower()]
        sorted_files = sorted(filtered_files, key=lambda x: self.get_game_started_timestamp(x))
        return sorted_files


    def get_game_started_timestamp(self, file_name):
        file_path = os.path.join(self.matches_path, file_name)
        with open(file_path, 'r') as file:
            data = json.load(file)
            game_started = data["gameStarted"]
            game_started_time = datetime.strptime(game_started, "%m/%d/%Y %H:%M:%S")
            return game_started_time


    def process_unprocessed_matches(self):
        if not os.path.exists(self.processed_matches_csv):
            pd.DataFrame(columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        processed_matches = set(pd.read_csv(self.processed_matches_csv)['Match File Name'])
        sorted_files_with_match = self.get_sorted_files_with_match()
        match = None
        # data_df = pd.DataFrame(columns=['Avg Impostor MMR', 'Avg Crewmate MMR', 'Win Status'])
        for file in sorted_files_with_match:
            if file not in processed_matches:
                match = self.match_from_file(file)
                if match:
                    if match.result == "Canceled" or match.result == "Unknown":
                        self.logger.info(f"Skipped {match.match_file_name} because result is {match.result}")
                    else:
                        # res = 0
                        # if match.result == "Crewmates Win":
                        #     res = 1
                        # data_df = pd.concat([pd.DataFrame([[match.players.avg_impostor_mmr,match.players.avg_crewmate_mmr,res]], columns=data_df.columns), data_df], ignore_index=True)
                        self.logger.info(f"Processed Match ID:{match.id}")
                        self.calculate_mmr_gain_loss(match)
                        self.update_leaderboard(match)
                    processed_matches.add(file)
        # data_df.to_csv('game_data.csv', index=False)
        pd.DataFrame(processed_matches, columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        if match:
            return match
        else:
            return None


    def process_match_by_id(self, match_id):
        if not os.path.exists(self.processed_matches_csv):
            pd.DataFrame(columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        processed_matches = set(pd.read_csv(self.processed_matches_csv)['Match File Name'])  
        match_file_name = self.find_matchfile_by_id(match_id)
        match = self.match_from_file(match_file_name)
        if match_file_name in processed_matches:
            return match
        if match.result != "Canceled" and match.result != "Unknown":
            self.calculate_mmr_gain_loss(match)
            self.update_leaderboard(match)
        processed_matches.add(match_file_name)
        pd.DataFrame(processed_matches, columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        return match


    def find_matchfile_by_id(self, match_id):
        json_files = [file for file in os.listdir(self.matches_path) if file.endswith('_match.json')]
        for match_file_name in json_files:
            match_file_path = os.path.join(self.matches_path, match_file_name)
            with open(match_file_path, 'r') as f:
                match_data = json.load(f)
                if str(match_data.get('MatchID')) == str(match_id):
                    return match_file_name
        return None


    def change_result_to_cancelled(self, match_id):

        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not change match to Cancelled")
            return False

        match = self.match_from_file(match_file_name)
        if match.result == "Canceled":
            self.logger.info(f"Match {match_id} is already a Cancel")
            return False
        
        self.logger.info(f"Changing match {match_id} to Canceled")
        for player in match.players.players:
            player.canceled = True

        self.calculate_mmr_gain_loss(match)
        self.update_leaderboard(match)

        match.result == 'Canceled'
        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        match_data['result'] = 'Canceled'
        with open(file_path, 'w') as f:
            json.dump(match_data, f, indent=4)
        return match
    

    def change_result_to_crew_win(self, match_id):
        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not change match to a Crewmates Win")
            return False
        
        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        if match_data['result'] != 'Crewmates Win':
            self.change_result_to_cancelled(match_id)
            match_data['result'] = 'Crewmates Win'
            with open(file_path, 'w') as f:
                json.dump(match_data, f, indent=4)
            match = self.match_from_file(match_file_name)
            self.calculate_mmr_gain_loss(match)
            self.update_leaderboard(match)
            self.logger.info(f"Changed {match_id} to a Crewmates Win")
            return True
        else:
            self.logger.error(f"Match {match_id} Is already a Crewmates Win")
            return False
    

    def change_result_to_imp_win(self, match_id):
        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not change match to Impostors Win")
            return False
        
        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        if match_data['result'] != 'Impostors Win': 
            self.change_result_to_cancelled(match_id)
            match_data['result'] = 'Impostors Win'
            with open(file_path, 'w') as f:
                json.dump(match_data, f, indent=4)
            match = self.match_from_file(match_file_name)
            self.calculate_mmr_gain_loss(match)
            self.update_leaderboard(match)
            self.logger.error(f"Changed {match_id} to an Impostors Win")
            return True
        else:
            self.logger.error(f"Match {match_id} Is already an Impostors Win")
            return False
        

    def match_info_by_id(self, match_id):
        match_file_name = self.find_matchfile_by_id(match_id)
        if match_file_name is None:
            self.logger.error(f"Can't find {match_id} - Could not generate info for this match")
            return None
        file_path = os.path.join(self.matches_path, match_file_name)
        with open(file_path, 'r') as f:
            match_data = json.load(f)
        return match_data
    

    def change_player_name(self, old_name, new_name):
        def read_json_file(filename):
            with open(os.path.join(self.matches_path, filename), 'r') as file:
                return json.load(file)
    
        def write_json_file(filename, data):
            with open(os.path.join(self.matches_path, filename), 'w') as file:
                json.dump(data, file, indent=4)

        for filename in os.listdir(self.matches_path):
            if filename.endswith('.json'):
                data = read_json_file(filename)
                change_made = False
                
                if 'players' in data:
                    players = data['players'].split(',')
                    if old_name in players:
                        players[players.index(old_name)] = new_name
                        data['players'] = ','.join(players)
                        self.logger.debug(f"Player name '{old_name}' updated to '{new_name}' in {filename}")
                        change_made = True
                    impostors = data.get('impostors', '').split(', ')
                    if old_name in impostors:
                        impostors[impostors.index(old_name)] = new_name
                        data['impostors'] = ', '.join(impostors)
                        self.logger.debug(f"Impostor name '{old_name}' updated to '{new_name}' in {filename}")
                        change_made = True

                if isinstance(data, list):
                    for event in data:
                        for key in ['Name', 'Player', 'Target', 'Killer','DeadPlayer', 'Impostors']:
                            if key in event:
                                if event[key].endswith(" |"):
                                    event[key] = event[key][:-2]  # Remove last two characters
                                if event[key] == old_name:
                                    change_made = True
                                    event[key] = new_name
                                if key == 'Impostors':
                                    if old_name in event[key].split(','): 
                                        event[key] = event[key].replace(old_name, new_name)
                                        change_made = True
                if change_made: 
                    write_json_file(filename, data)
                    self.logger.debug(f"Player name '{old_name}' updated to '{new_name}' in {filename}")

        player_row = self.leaderboard.get_player_row(old_name)
        if player_row is not None:
            index = player_row['Rank']
            self.leaderboard.leaderboard.at[index, 'Player Name'] = new_name
            self.leaderboard.save_leaderboard()
            self.logger.debug(f"Player name '{old_name}' updated to '{new_name}' in Leaderboard")


    def mine_matches_data(self): #testing and development only
        match : Match
        sorted_files_with_match = self.get_sorted_files_with_match()
        match=None
        data_df = pd.DataFrame(columns=['MMR diff'])
        for file in sorted_files_with_match:
            match = self.match_from_file(file)
            if match:
                if match.result == "Canceled" or match.result == "Unknown":
                    self.logger.info(f"skipped {match.match_file_name} because result is {match.result}")
                else:
                    res = 0
                    if match.result == "Crewmates Win":
                        res = 1
                    data_df = pd.concat([pd.DataFrame([[round(match.players.avg_crewmate_mmr,1)-round(match.players.avg_impostor_mmr,1)]], columns=data_df.columns), data_df], ignore_index=True)
                    self.logger.info(f"Processed Match ID:{match.id}")

        data_df.to_csv('game_data.csv', index=False)
    


###############################################
# path = "~/Resistance/Preseason/"

# path = "~/plugins/MatchLogs/Preseason"
# f = FileHandler(path, "leaderboard_full.csv")
# print(f.find_matchfile_by_id(25))
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
