class PlayerInMatch:
    def __init__(self, 
                 team="",
                 name="",
                 time_of_death=None,
                 died_first_round=False,
                 crewmate_current_elo = 1100,
                 impostor_current_elo = 900,
                 current_elo = 1000,
                 won = True):
        
        self.name = name
        self.discord = ""
        self.team = team 
        self.time_of_death = time_of_death
        self.died_first_round = died_first_round
        self.number_of_placed_votes = 0
        self.number_of_correct_votes = 0
        self.tasks = 0
        self.crewmate_elo_gain = 0.0
        self.impostor_elo_gain = 0.0
        self.pecentage_of_winning = 0.0
        self.p = 1.0
        self.performance = 1.0
        self.crewmate_current_elo = crewmate_current_elo
        self.impostor_current_elo = impostor_current_elo
        self.current_elo = current_elo
        self.number_of_kills = 0
        self.total_kills = 0
        self.killing_performance = 1
        self.voting_accuracy = 1
        self.alive = True
        self.ejected = False
        self.won = won
        self.k = 32
        self.color = None
        self.last_voted = None
        self.voted_wrong_on_crit = False #crew only 
        self.correct_vote_on_eject = 0 #crew only 
        self.right_vote_on_crit_but_loss = False #crew only 
        self.ejected_early_as_imp = False #imp only
        self.got_crew_voted = 0 #imp only
        self.solo_imp = False #imp only
        self.kills_as_solo_imp = 0 #imp only
        self.won_as_solo_imp = False #imp only

    def get_voting_accuracy(self):
        if self.number_of_placed_votes != 0:
            self.voting_accuracy = round(self.number_of_correct_votes/ self.number_of_placed_votes, 3)
            return self.voting_accuracy
        else:
            return 0
        
    def correct_vote(self):
        if self.team.lower() == "crewmate":
            self.number_of_correct_votes += 1
            self.number_of_placed_votes += 1

    def incorrect_vote(self):
        if self.team.lower() == "crewmate":
            self.number_of_placed_votes += 1

    def finished_task(self):
        if self.team.lower() == "crewmate":
            self.tasks += 1
    
    def update_elo(self):
        self.crewmate_current_elo += self.crewmate_elo_gain
        self.impostor_current_elo += self.impostor_elo_gain
        self.current_elo = (self.crewmate_current_elo + self.impostor_current_elo)/2

    def got_a_kill(self):
        self.number_of_kills+=1
    
    def killing_percentage(self):
        self.killing_performance = self.number_of_kills/self.total_kills

    def calculate_performance_and_elo(self):
        odds_of_winning = self.pecentage_of_winning
        # voting_accuracy = self.get_voting_accuracy()
        # tasks_complete = self.tasks / 10

        
        if self.team == 'impostor':
            if self.ejected_early_as_imp: self.performance -= 0.15  
            if self.solo_imp : self.performance += 0.15 
            if self.got_crew_voted > 0 : self.performance += (0.05 * self.got_crew_voted)
            if self.kills_as_solo_imp > 0: self.performance += (0.05 * self.kills_as_solo_imp)
            if self.won_as_solo_imp : self.performance += 0.20
            
        elif self.team == 'crewmate': #bad crewmate -0.30 /// good crewmate 0.20
            if self.voted_wrong_on_crit: self.performance -= 0.30
            if self.correct_vote_on_eject: self.performance += 0.20
            if self.right_vote_on_crit_but_loss: self.performance +=0.20

        if self.won:
            if self.died_first_round:
                self.performance = 0.65
            self.p = (1 - odds_of_winning)
            self.p *= self.performance

        else:
            if self.died_first_round:
                self.performance = 1.35
            self.p = odds_of_winning
            self.p /= self.performance
            self.p *= -1
            

        self.p = round(self.p, 2)
        if self.team == 'impostor':
            self.impostor_elo_gain = round(self.p * self.k, 2)   
        elif self.team == 'crewmate':
            self.crewmate_elo_gain = round(self.p * self.k, 2) 
        self.update_elo()
        