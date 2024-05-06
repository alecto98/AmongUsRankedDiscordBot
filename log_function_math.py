import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

ruleset = {
    500: 0.16,
    400: 0.15,
    300: 0.139,
    200: 0.123,
    100: 0.1,
    50: 0.065,
    0: 0,
}

x_data = np.array(list(ruleset.keys()))
y_data = np.array(list(ruleset.values()))

def log_function(x, a, b, c, d):
    return a * np.log(b * x + c) + d

params, _ = curve_fit(log_function, x_data, y_data)
a, b, c, d = params

plt.scatter(x_data, y_data, color='blue', label='Original Data')
x_range = np.linspace(min(x_data), max(x_data), 1000)
y_fitted = log_function(x_range, a, b, c, d)
plt.plot(x_range, y_fitted, color='red', label='Fitted Logarithmic Function')
plt.xlabel('Difference (Crew - Impostor)')
plt.ylabel('Probability')
plt.title('Fitted Logarithmic Function vs. Original Data')
plt.legend()
plt.grid(True)
plt.show()

print(f'Fitted Parameters: a={a}, b={b}, c={c}, d={d}')


# Fitted Parameters: a=0.07416865609596561, b=0.02188284234744941, c=1.3188566776518948, d=-0.021900704104131766

# def winning_prob(difference):
#     def log_function_fitted(diff):
#         a=0.043290409437842466
#         b=7.855256175054392
#         c=98.05742514755777
#         d=-0.19883086302819628
#         return a * np.log(b * diff + c) + d
    
#     # difference = avg_crew_elo - avg_imp_elo
#     if difference < 0:
#         difference = abs(difference)
#         prob_change = log_function_fitted(difference)
#         return 0.78 - prob_change
#     else:
#         prob_change = log_function_fitted(difference)
#         return 0.78 + prob_change
    
# import numpy as np
# import matplotlib.pyplot as plt



# # Generate data for heatmap
# x = np.arange(-600, 601, 1)
# y = np.array([winning_prob(diff) for diff in x])

# # Plot the heatmap
# plt.figure(figsize=(10, 6))
# plt.plot(x, y, color='blue')
# plt.xlabel('Difference (Crew - Impostor)')
# plt.ylabel('Probability')
# plt.title('Probability vs. Difference')
# plt.grid(True)
# plt.show()

    

