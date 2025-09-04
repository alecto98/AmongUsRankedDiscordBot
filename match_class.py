from player_in_match import PlayerInMatch
from rapidfuzz import fuzz
import numpy as np
import yaml
import os

# Load ranked percentages config
with open(os.path.join('config', 'ranked_percentages.yaml'), 'r', encoding='utf-8') as f:
    ranked_percentages = yaml.safe_load(f)

class Match:
    def __init__(self, 
                 id:int=None,
                 players:list=None,
                 match_start_time=None, 
                 match_end_time=None,
                 result:str=None, 
                 match_file_name:str=None, 
                 event_file_name:str=None,
                 k = 32
                 ):
        self.id = id
        self.match_start_time = match_start_time
        self.match_end_time = match_end_time
        self.match_duration = None
        self.players = players
        self.impostors:list = None
        self.crewmates_count = 0
        self.impostors_count = 0
        self.avg_impostor_mmr = 0
        self.avg_crewmate_mmr = 0
        self.crew_winning_percentage = ranked_percentages['crew_base_win_percentage']
        self.imp_winning_percentage = ranked_percentages['imp_base_win_percentage']
        self.rounds = 1
        self.solo_imp_game = False
        self.alive_players = 10
        self.alive_impostors = 2
        
        self.k = ranked_percentages['k_factor'] if k is None else k
        self.result = result
        self.match_file_name = match_file_name
        self.event_file_name = event_file_name
        
    def add_player(self, player : PlayerInMatch):
        self.players.append(player)
        if player.team == 'impostor':
            self.impostors_count += 1
        elif player.team == 'crewmate':
            self.crewmates_count += 1

    def set_player_colors_in_match(self, colors)->None:
        player : PlayerInMatch
        for player, color in zip(self.players, colors):
            player.color = color

    def calculate_avg_mmr(self)->None:
        crewmate_mmr = 0
        impostor_mmr = 0
        player:PlayerInMatch
        for player in self.players:
            if player.team == 'impostor':
                impostor_mmr += player.impostor_current_mmr
            elif player.team == 'crewmate':
                crewmate_mmr += player.crewmate_current_mmr
        if self.crewmates_count == 0 or self.impostors_count == 0:
            return
        self.avg_impostor_mmr = impostor_mmr / self.impostors_count
        self.avg_crewmate_mmr = crewmate_mmr / self.crewmates_count
    
    def calculate_percentage_of_winning(self):
        player : PlayerInMatch
        
        def winning_prob(avg_crew_elo, avg_imp_elo):
            
            def log_function(diff):
                a = ranked_percentages['win_prob_a']
                b = ranked_percentages['win_prob_b']
                c = ranked_percentages['win_prob_c']
                d = ranked_percentages['win_prob_d']
                return a * np.log(b * diff + c) + d

            difference = avg_crew_elo - avg_imp_elo
            if difference < 0:
                difference = abs(difference)
                prob_change = log_function(difference)
                win_prob = ranked_percentages['crew_base_win_percentage'] - prob_change
                if win_prob < ranked_percentages['min_win_probability']: 
                    win_prob = ranked_percentages['min_win_probability']
                return win_prob
            else:
                prob_change = log_function(difference)
                win_prob = ranked_percentages['crew_base_win_percentage'] + prob_change
                if win_prob > ranked_percentages['max_win_probability']: 
                    win_prob = ranked_percentages['max_win_probability']
                return win_prob
        
        self.crew_winning_percentage = winning_prob(self.avg_crewmate_mmr, self.avg_impostor_mmr)
        self.imp_winning_percentage = 1 - self.crew_winning_percentage
        for player in self.players:
            if player.team == 'impostor':
                player.percentage_of_winning = self.imp_winning_percentage
            elif player.team == 'crewmate':
                player.percentage_of_winning = self.crew_winning_percentage
        # a = 0.043290409437842466
        # b = 7.855256175054392
        # c = 98.05742514755777
        # d = -0.19883086302819628

    def calculate_percentage_of_winning_elo(self): # not used
        """Calculate win probabilities using the ELO formula"""
        player : PlayerInMatch
        
        def elo_expected_score(avg_crew_mmr, avg_imp_mmr):
            # Expected Score (Ev) = 1 / (1 + 10^((Rating2 - Rating1) / 400))
            # Here Rating2 is avg_imp_mmr and Rating1 is avg_crew_mmr
            exponent = (avg_imp_mmr - avg_crew_mmr) / 400
            crew_win_prob = 1 / (1 + pow(10, exponent))
            
            # Crew win probability is the direct result of the ELO formula
            return crew_win_prob
        
        # Calculate crew win probability using ELO formula
        self.crew_winning_percentage = elo_expected_score(self.avg_crewmate_mmr, self.avg_impostor_mmr)
        self.imp_winning_percentage = 1 - self.crew_winning_percentage
        
        # Assign win probabilities to players
        for player in self.players:
            if player.team == 'impostor':
                player.percentage_of_winning = self.imp_winning_percentage
            elif player.team == 'crewmate':
                player.percentage_of_winning = self.crew_winning_percentage

    def get_players_by_team(self, team)->list:
        player : PlayerInMatch
        team_players = []
        for player in self.players:
            if player.team.lower() == team:
                team_players.append(player)
        return team_players
    
    def get_player_by_name(self, name)->PlayerInMatch:
        for player in self.players:
            if player.name == name:
                return player 
        for player in self.players:
            if fuzz.ratio(player.name, name)>=70:
                return player

    def calculate_mmr(self):
        if self.result.lower() in ["canceled", "unknown"]:
            return
        player:PlayerInMatch
        for player in self.players:

            if player.team == 'crewmate': 
                if player.number_of_correct_votes: player.performance *= 1 + (player.number_of_correct_votes * ranked_percentages['crew_correct_vote_bonus'])
                if player.number_of_incorrect_votes: player.performance /= 1 + (player.number_of_incorrect_votes * ranked_percentages['crew_incorrect_vote_penalty'])
                if player.got_crew_voted: player.performance /= 1 + (ranked_percentages['crew_got_voted_penalty'] * len(player.got_crew_voted))
                if player.tasks_complete: player.performance *= 1 + (player.tasks_complete * ranked_percentages['crew_task_bonus'])

                if player.voted_wrong_on_crit: player.performance /= 1 + ranked_percentages['crew_wrong_crit_penalty']
                if player.correct_vote_on_eject != None: player.performance *= 1 + sum(correct_vote[0] * ranked_percentages['crew_correct_eject_bonus'] for correct_vote in player.correct_vote_on_eject) #correct_vote[0] is players alive
                if player.right_vote_on_crit_but_loss: player.performance *= 1 + ranked_percentages['crew_right_crit_loss_bonus']
            
                if player.won:
                    player.performance *= 1 + (player.rounds_survived * ranked_percentages['crew_win_survival_bonus'])
                else:
                    player.performance /= 1 + (player.rounds_survived * ranked_percentages['crew_loss_survival_penalty'])
                    if self.solo_imp_game:
                        player.performance /= 1 + (player.rounds_survived * ranked_percentages['crew_solo_imp_survival_penalty'])

            elif player.team == 'impostor':
                if player.ejected_early_as_imp: player.performance /= 1 + ranked_percentages['imp_early_eject_penalty']
                if player.solo_imp : player.performance *= 1 + ranked_percentages['imp_solo_bonus']
                if player.got_crew_voted: player.performance *= 1 + (ranked_percentages['imp_got_voted_bonus'] * len(player.got_crew_voted))
                if player.kills_as_solo_imp > 0: player.performance *= 1 + (ranked_percentages['imp_solo_kill_bonus'] * player.kills_as_solo_imp)
                if player.won_as_solo_imp : player.performance *= 1 + ranked_percentages['imp_solo_win_bonus']
                if player.number_of_kills > 0: player.performance *= 1 + (player.number_of_kills * ranked_percentages['imp_kill_bonus'])
                        
            if player.performance < ranked_percentages['min_performance']:
                player.performance = ranked_percentages['min_performance']

            if player.won:
                if player.died_first_round:
                    player.performance = ranked_percentages['died_first_win_performance']
                player.p = (1 - player.percentage_of_winning)
                player.p *= player.performance

            else:
                if player.died_first_round:
                    player.performance = ranked_percentages['max_loss_performance']
                player.p = player.percentage_of_winning
                player.p /= player.performance
                player.p *= -1
                
            player.p = round(player.p, 4)
            if player.team == 'impostor':
                player.impostor_mmr_gain = round(player.p * self.k, 2)
                player.impostor_mmr_gain = player.impostor_mmr_gain
            elif player.team == 'crewmate':
                player.crewmate_mmr_gain = round(player.p * self.k, 2)
                player.crewmate_mmr_gain = player.crewmate_mmr_gain

            player.mmr_gain = (player.impostor_mmr_gain + player.crewmate_mmr_gain)/2

    def match_details(self):
        string = ""
        string+=f"Match ({self.id}) - Result ({self.result}) - Crew Avg Elo({self.avg_crewmate_mmr}) - Imp Avg Elo({self.avg_impostor_mmr})\n"
        player : PlayerInMatch
        for player in self.players:
            if player.team == "crewmate":
                string+=f"{player.name}: CElo({player.crewmate_current_mmr}) C-+({player.crewmate_mmr_gain}) P/Per({round(player.p,2)},{round(player.performance,2)}) VAcc({player.voting_accuracy}) "
                if player.died_first_round:
                    string+=f"(Dead1st {ranked_percentages['died_first_win_performance']*100:.0f}%) "
                if player.voted_wrong_on_crit:
                    string+=f"(Voted Wrg on Crit -{ranked_percentages['crew_wrong_crit_penalty']*100:.0f}%) "
                if player.right_vote_on_crit_but_loss:
                    string+=f"(Voted Rgt on Crit & L +{ranked_percentages['crew_right_crit_loss_bonus']*100:.0f}%) "
                if player.correct_vote_on_eject:
                    string+=f"(Voted {len(player.correct_vote_on_eject)} Imp on Ej +{sum(correct_vote[0] * ranked_percentages['crew_correct_eject_bonus']*100 for correct_vote in player.correct_vote_on_eject):.0f}%) "
                if player.number_of_correct_votes:
                    string+=f"(Voted {player.number_of_correct_votes} Imp +{player.number_of_correct_votes*ranked_percentages['crew_correct_vote_bonus']*100:.0f}%) "
                if player.got_crew_voted:
                    string+=f"(Voted {len(player.got_crew_voted)} Crew on Ej -{len(player.got_crew_voted)*ranked_percentages['crew_got_voted_penalty']*100:.0f}%) "
                if player.number_of_incorrect_votes > 0:
                    string+=f"(Voted {player.number_of_incorrect_votes} Crew -{player.number_of_incorrect_votes*ranked_percentages['crew_incorrect_vote_penalty']*100:.0f}%) "
                if player.tasks_complete > 0:
                    string+=f"({player.tasks_complete} Tasks +{player.tasks_complete*ranked_percentages['crew_task_bonus']*100:.0f}%) "
                if player.won:
                    if player.rounds_survived: 
                        string+=f"(Rounds survived +{player.rounds_survived*ranked_percentages['crew_win_survival_bonus']*100:.0f}%) "
                else:
                    if player.rounds_survived: 
                        if not self.solo_imp_game:
                            string+=f"(Rounds survived -{player.rounds_survived*ranked_percentages['crew_loss_survival_penalty']*100:.0f}%) "
                        else: #solo imp -4%
                            string+=f"(Rounds survived -{player.rounds_survived*(ranked_percentages['crew_loss_survival_penalty']+ranked_percentages['crew_solo_imp_survival_penalty'])*100:.0f}%) "
                string +="\n"

        for player in self.players:
            if player.team == "impostor":
                string += f"{player.name}: IElo({player.impostor_current_mmr}) I-+({player.impostor_mmr_gain}) P/Per({round(player.p,2)},{round(player.performance,2)}) "
                if player.ejected_early_as_imp:
                    string+=f"(EjEarly -{ranked_percentages['imp_early_eject_penalty']*100:.0f}%) "
                if player.solo_imp:
                    string+=f"(SoloImp-kills {player.kills_as_solo_imp} +{player.kills_as_solo_imp*ranked_percentages['imp_solo_kill_bonus']*100:.0f}) +{ranked_percentages['imp_solo_bonus']*100:.0f}%(SImp) "
                if player.got_crew_voted:
                    string+=f"(Voted {len(player.got_crew_voted)} Crewmates +{len(player.got_crew_voted)*ranked_percentages['imp_got_voted_bonus']*100:.0f}%) "
                if player.won_as_solo_imp:
                    string+=f"(Solo Imp Win +{ranked_percentages['imp_solo_win_bonus']*100:.0f}%) "
                if player.number_of_kills > 0: string+=f"Kills {player.number_of_kills} +({player.number_of_kills*ranked_percentages['imp_kill_bonus']*100:.0f}%) "
                string += "\n"
        return string 

    def is_player_imp(self, player_name : str):
        try:
            if player_name == "none": return False
            return self.get_player_by_name(player_name).team.lower() == "impostor"
        except:
            print(player_name)