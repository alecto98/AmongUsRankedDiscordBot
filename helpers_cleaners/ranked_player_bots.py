import numpy as np
import matplotlib.pyplot as plt

def winning_prob(avg_crew_elo, avg_imp_elo):
    def log_function(diff):
        # a = 0.043290409437842466
        # b = 7.855256175054392
        # c = 98.05742514755777
        # d = -0.19883086302819628

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

# Generate ELO ratings for the Impostor from 750 to 1250
imp_elo_range = np.arange(750, 1251)

# Calculate winning probabilities for each Impostor ELO rating with fixed Crew ELO at 1000
# winning_probs = np.zeros(len(imp_elo_range))
# for i, imp_elo in enumerate(imp_elo_range):
#     winning_probs[i] = winning_prob(1000, imp_elo)

# Plot the winning probabilities
# plt.plot(imp_elo_range, winning_probs, color='blue')
# plt.xlabel('Impostor ELO')
# plt.ylabel('Winning Probability')
# plt.title('Winning Probability vs. Impostor ELO (Crew ELO = 1000)')
# plt.grid(True)
# plt.show()
print(winning_prob(-300,0))
print(winning_prob(-200,0))
print(winning_prob(-150,0))
print(winning_prob(-100,0))
print(winning_prob(-50,0))
print(winning_prob(0,0))
print(winning_prob(50,0))
print(winning_prob(100,0))
print(winning_prob(150,0))
print(winning_prob(200,0))
print(winning_prob(300,0))
