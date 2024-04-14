from players_list import PlayersList

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

    def get_players(self) -> PlayersList:
        return self.players.players
    
