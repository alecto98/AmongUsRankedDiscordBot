from player_in_match import PlayerInMatch
import pandas as pd
import joblib
import sklearn #needed for ML processing
from rapidfuzz import fuzz
class PlayersList:
    def __init__(self) :
        self.players = []
        self.crewmate_mmr = 0
        self.impostor_mmr = 0
        self.impostor_win_rate = 0
        self.avg_impostor_mmr = 0
        self.avg_crewmate_mmr = 0
        self.crewmate_win_rate = 0
        self.crewmates_count = 0
        self.impostors_count = 0
        self.mmr_expected_win_rate = 0


    def add_player(self, player : PlayerInMatch):
        self.players.append(player)
        if player.team == 'impostor':
            self.impostors_count += 1
        elif player.team == 'crewmate':
            self.crewmates_count += 1


    def get_player_by_name(self, name)->PlayerInMatch:
        for player in self.players:
            if player.name == name:
                return player 
        for player in self.players:
            if fuzz.ratio(player.name, name)>=70:
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
    

    def set_player_colors_by_names(self, names, colors):
        for name, color in zip(names, colors):
            self.get_player_by_name(name).color=color


    def set_player_colors_in_match(self, colors):
        for player, color in zip(self.players, colors):
            player.color = color


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


    def calculate_total_mmr(self):
        self.crew_mmr = 0
        self.impostor_mmr = 0
        for player in self.players:
            if player.team == 'impostor':
                self.impostor_mmr += player.impostor_current_mmr
            elif player.team == 'crewmate':
                self.crewmate_mmr += player.crewmate_current_mmr
        self.avg_impostor_mmr = self.impostor_mmr / self.impostors_count
        self.avg_crewmate_mmr = self.crewmate_mmr / self.crewmates_count
