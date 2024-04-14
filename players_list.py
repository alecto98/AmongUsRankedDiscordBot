from player_in_match import PlayerInMatch

class PlayersList:
    def __init__(self) :
        self.players = []
        self.crew_elo = 8000
        self.impostor_elo = 2000

    def add_player(self, player : PlayerInMatch):
        self.players.append(player)

    def get_player_by_name(self, name)->PlayerInMatch:
        for player in self.players:
            if player.name == name:
                return player 
            
    def is_player_impostor(self, name) -> bool:
        for player in self.players:
            if player.name == name:
                return player.team == "impostor" 
            
    def get_players_by_team(self, team):
        team_players = []
        for player in self.players:
            if player.team.lower() == team:
                team_players.append(player)
        return team_players
    
    def set_player_colors(self, names, colors):
        for name, color in zip(names, colors):
            self.get_player_by_name(name).color=color

    def who_won(self, result):
        if result in ["Crewmates Win", "HumansByVote"]:
            for player in self.players:
                if player.team == 'impostor':
                    player.won = False
                else:
                    player.won = True
        else:
            for player in self.players:
                if player.team == 'crewmate':
                    player.won = False
                else:
                    player.won = True

    def calculate_total_elo(self):
        self.crew_elo = 0
        self.impostor_elo = 0
        for player in self.players:
            if player.team == 'impostor':
                self.impostor_elo += player.impostor_current_elo
            elif player.team == 'crewmate':
                self.crew_elo += player.crewmate_current_elo
    
    def calculate_percentage_of_winning(self):
        crew_win_rate = self.crew_elo/(self.crew_elo + self.impostor_elo)
        imp_win_rate = self.impostor_elo/(self.crew_elo + self.impostor_elo)
        for player in self.players:
            if player.team == 'impostor':
                player.pecentage_of_winning = imp_win_rate
            elif player.team == 'crewmate':
                player.pecentage_of_winning = crew_win_rate


