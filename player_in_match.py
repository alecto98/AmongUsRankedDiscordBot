import yaml
import os

# Load config from YAML
with open(os.path.join('config', 'config.yaml'), 'r', encoding='utf-8') as f:
    all_configs = yaml.safe_load(f)
use_config = all_configs['use'] if 'use' in all_configs else 'main'
config = all_configs[use_config]

class PlayerInMatch:
    def __init__(self, 
                 name="",
                 team="",
                 crewmate_current_mmr = None,
                 impostor_current_mmr = None,
                 current_mmr = None
                 ):
        
        #player details
        self.match_id = None
        self.name = name
        self.discord = 0
        self.color = None
        self.current_mmr = current_mmr if current_mmr is not None else config['current_mmr']
        self.crewmate_current_mmr = crewmate_current_mmr if crewmate_current_mmr is not None else config['crewmate_current_mmr']
        self.impostor_current_mmr = impostor_current_mmr if impostor_current_mmr is not None else config['impostor_current_mmr']
        self.team = team
        self.match_result = None
        self.mmr_gain = 0.0
        self.crewmate_mmr_gain = 0.0
        self.impostor_mmr_gain = 0.0
        self.percentage_of_winning = 0.0
        #performance
        self.won = None
        self.p = 1.0
        self.performance = 1.0
        self.alive = True
        #survivability
        self.alive_time = None
        self.match_time = None
        self.time_of_death = None
        self.rounds_survived = 0
        self.total_rounds = 0
        self.ejected_in_meeting = False # 0 if never ejected
        #voting accuracy
        self.number_of_placed_votes = 0
        self.number_of_correct_votes = 0
        self.number_of_incorrect_votes = 0
        self.number_of_skip_votes = 0
        self.last_voted = None
        self.voting_accuracy = 0
        self.got_crew_voted = []
        #crew
        self.died_first_round = False
        self.finished_tasks_alive = False 
        self.finished_tasks_dead = False
        self.tasks_complete = 0
        self.voted_wrong_on_crit = False 
        self.correct_vote_on_eject = []
        self.right_vote_on_crit_but_loss = False 
        #imp
        self.number_of_kills = 0
        self.ejected_early_as_imp = False 
        self.solo_imp = False
        self.kills_as_solo_imp = 0 
        self.won_as_solo_imp = False 

    def correct_vote(self):
        if self.team.lower() == "crewmate":
            self.number_of_correct_votes += 1
            self.number_of_placed_votes += 1

    def incorrect_vote(self):
        if self.team.lower() == "crewmate":
            self.number_of_incorrect_votes += 1
            self.number_of_placed_votes += 1

    def skipped_vote(self):
        if self.team.lower() == "crewmate":
            self.number_of_skip_votes += 1
            self.number_of_placed_votes += 1

    def finished_task(self):
        if self.team.lower() == "crewmate":
            self.tasks_complete += 1

    def crew_voted_out_crew(self):
        if self.team.lower() == "crewmate":
            self.got_crew_voted+=1

    def imp_voted_out_crew(self):
        if self.team.lower() == "impostor":
            self.got_crew_voted+=1

    def got_a_kill(self):
        if self.team.lower() == "impostor":
            self.number_of_kills+=1