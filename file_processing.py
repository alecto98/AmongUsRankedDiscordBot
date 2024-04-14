import pandas as pd
import os
from player_in_match import PlayerInMatch
from players_list import PlayersList
from match_class import Match
from leaderboard import Leaderboard

class FileHandler:
    def __init__(self, matches_path, database_location):
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
            if old_player:
                player.crewmate_current_elo = self.leaderboard.get_player_crew_elo(player.name)
                player.impostor_current_elo = self.leaderboard.get_player_imp_elo(player.name)
                player.current_elo = self.leaderboard.get_player_elo(player.name)
            else:
                self.leaderboard.new_player(player.name)

    def get_players_from_df(self, match_df) -> PlayersList:
        players_array = [x.strip() for x in match_df.players.split(',')]
        impostors_array = match_df.impostors.split(", ")
        players_list = PlayersList()
        result = match_df.result
        for player_name in players_array:
            if not self.leaderboard.is_player_in_leaderboard(player_name):
                self.leaderboard.new_player(player_name)
            team = "impostor" if player_name in impostors_array else "crewmate"
            players_list.add_player(PlayerInMatch(name=player_name, team=team))
        self.get_players_info_from_leaderboard(players_list)
        players_list.calculate_total_elo()
        players_list.calculate_percentage_of_winning()
        players_list.who_won(result)
        
        return players_list

    def match_from_dataframe(self, match_df, events_df, players_list):
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
                else:
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
                        if imp.name != ejected_player_name:
                            imp.solo_imp = True
                    imps_alive -= 1

                    for player in match.players.players:
                        if players_alive >= 8:
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

    def calculate_elo_gain_loss(self, match):
        for player in match.players.players:
            player.calculate_performance_and_elo()
            self.leaderboard.update_player(player)

    def match_from_file(self, path=None, json_file=None):
        try:
            match_df, events_df = self.df_from_json(path, json_file)
        except Exception as e:
            print(str(e)+"Error reading match from file"+str(json_file))
            return None
        
        if match_df.result in ["Canceled", "Cancelled"] or events_df is None or match_df is None:
            try:
                players_list = self.get_players_from_df(match_df)
                match = self.match_from_dataframe(match_df, events_df, players_list)
                match.match_file_name = json_file
                return match
            except:
                print(match_df.eventsLogFile)

        players_list = self.get_players_from_df(match_df)
        match = self.match_from_dataframe(match_df, events_df, players_list)
        match.match_file_name = json_file
        # match.players.calculate_percentage_of_winning()
        self.calculate_elo_gain_loss(match)
        return match
        
    def get_sorted_files_with_match(self):
        files = os.listdir(self.matches_path)
        filtered_files = [file for file in files if "match" in file.lower()]
        sorted_files = sorted(filtered_files, key=lambda x: os.path.getmtime(os.path.join(self.matches_path, x)))
        return sorted_files

    def process_unprocessed_matches(self):
        if not os.path.exists(self.processed_matches_csv):
            pd.DataFrame(columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        processed_matches = set(pd.read_csv(self.processed_matches_csv)['Match File Name'])
        sorted_files_with_match = self.get_sorted_files_with_match()

        for file in sorted_files_with_match:
            if file not in processed_matches:
                # print(file)
                match = self.match_from_file(self.matches_path, file)
                if match:
                    processed_matches.add(file)
        pd.DataFrame(processed_matches, columns=['Match File Name']).to_csv(self.processed_matches_csv, index=False)
        if match:
            return match


# path = "~/eloScripts/matches_full/"
# file_name =  "2JLP1bguhCOpOTv1_match.json"
# f = FileHandler(path, "db_Full.csv")
# f.process_unprocessed_matches()
# match_z = f.match_from_file(path,file_name)
# print(match_z.players.__dict__)
# print(match_z.__dict__)
# for player in match_z.players.players:
#     print(player.__dict__)
# print(match_z.players.players[0].__dict__)