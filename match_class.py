from players_list import PlayersList
from player_in_match import PlayerInMatch

class Match:
    def __init__(self, 
                 id=None, 
                 match_start_time=None, 
                 match_end_time=None, 
                 players : PlayersList = None, 
                 result=None, 
                 match_file_name=None, 
                 event_file_name=None, 
                 logged=False):
        
        self.id = id
        self.match_start_time = match_start_time
        self.match_end_time = match_end_time
        self.players = players
        self.result = result
        self.match_file_name = match_file_name
        self.event_file_name = event_file_name
        self.logged = logged
        self.meetings = []
 

    def get_players(self):
        return self.players.players
    

    def print_match(self):
        filename = "matches.csv"
        
        string = ""
        players = self.get_players()
        for player in players:
            if player.team == "crewmate":
                mmr_gain = f'c{player.crewmate_mmr_gain}'
            else:
                mmr_gain = f'i{player.impostor_mmr_gain}'
            string += f"{player.name}{mmr_gain},"
        with open(filename, 'a') as file:
            file.write(string+"\n")

    def match_details(self):
        string = ""
        string+=f"Match ({self.id}) - Result ({self.result}) - Crew Avg Elo({self.players.avg_crewmate_mmr}) - Imp Avg Elo({self.players.avg_impostor_mmr})\n"
        players = self.players.players
        for player in players:
            if player.team == "crewmate":
                string+=f"{player.name}: CElo({player.crewmate_current_mmr}) C-+({player.crewmate_mmr_gain}) P/Per({round(player.p,2)},{round(player.performance,2)}) VAcc({player.voting_accuracy}) "
                if player.died_first_round:
                    string+="(Dead1st) "
                if player.voted_wrong_on_crit:
                    string+="(Voted Wrong on Crit) "
                if player.right_vote_on_crit_but_loss:
                    string+="(Voted Right on Crit & L) "
                if player.correct_vote_on_eject > 0:
                    string+=f"(Voted {player.correct_vote_on_eject} Imp)"
                string +="\n"

        for player in players:
            if player.team == "impostor":
                string += f"{player.name}: IElo({player.impostor_current_mmr}) I-+({player.impostor_mmr_gain}) P/Per({round(player.p,2)},{round(player.performance,2)}) "
                if player.ejected_early_as_imp:
                    string+="(EjEarly) "
                if player.solo_imp:
                    string+=f"(SoloImp-kills {player.kills_as_solo_imp})"
                if player.got_crew_voted >0:
                    string+=f"(Voted {player.got_crew_voted} Crewmates)"
                if player.won_as_solo_imp:
                    string+="(Solo Imp Win)"
                string += "\n"
        return string 
    




