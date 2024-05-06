# import pandas as pd
# import numpy as np
# from sklearn.model_selection import train_test_split
# from sklearn.preprocessing import StandardScaler
# from sklearn.linear_model import LogisticRegression
# import joblib

# # Load the data
# data_df = pd.read_csv('game_data.csv')

# # Prepare the features and target variable
# X = data_df[['Avg Crewmate MMR', 'Avg Impostor MMR']]
# y = data_df['Win Status']

# # Split the data into training and testing sets
# X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# # Standardize the features
# scaler = StandardScaler()
# X_train_scaled = scaler.fit_transform(X_train)
# X_test_scaled = scaler.transform(X_test)

# # Train the logistic regression model
# model = LogisticRegression(random_state=42, max_iter=1000)
# model.fit(X_train_scaled, y_train)

# # Save the trained model
# joblib.dump(model, 'logistic_regression_model.pkl')

# # Define a custom function to map probabilities to the desired range
# def map_probability(probability):
#     return 0.6 + (probability * 0.32)

# # Use the loaded model for predictions
# # Example usage:
# new_data_point = [[1100, 1100]]  # Example data point
# scaled_data_point = scaler.transform(new_data_point)
# probability = model.predict_proba(scaled_data_point)[:, 1]  # Probability of winning as impostor
# mapped_probability = map_probability(probability)
# print(f"Predicted probability of winning: {mapped_probability, probability}")

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
import joblib

def map_probability(probability):
    if probability > 0.8:
        return 0.4 + (probability * 0.52)
    elif probability > 0.6:
        return 0.72 + ((probability-0.6) / 2)
    else:
        return 0.57 + (probability * 0.32)
    
data_df = pd.read_csv('game_data.csv')
X = data_df[['Avg Crewmate MMR', 'Avg Impostor MMR']]
y = data_df['Win Status']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = LogisticRegression(random_state=42, max_iter=1000)
model.fit(X_train, y_train)

joblib.dump(model, 'logistic_regression_model.pkl')

# Make predictions on the test set
probabilities = model.predict_proba(X_test)[:, 1]
probabilities_mapped = np.array(list(map(map_probability, probabilities)))

print(f"Model accuracy: {model.score(X_test, y_test)}")

# Plot the predictions
plt.figure(figsize=(10, 6))

# Plot for wins
plt.scatter(X_test[y_test == 1]['Avg Crewmate MMR'], probabilities_mapped[y_test == 1], color='green', label='Wins')

# Plot for losses
plt.scatter(X_test[y_test == 0]['Avg Crewmate MMR'], probabilities_mapped[y_test == 0], color='red', label='Losses')

# Add labels and title
plt.xlabel('Avg Crewmate MMR')
plt.ylabel('Predicted Probability of Winning')
plt.title('Predicted Probability vs Avg Crewmate MMR')
plt.legend()

# Show the plot
plt.show()

# # Make predictions on the test set
# probabilities = model.predict_proba(X_test_scaled)[:, 1]
# probabilities_mapped = map(map_probability, probabilities)
# probabilities_mapped = np.array(list(probabilities_mapped))
# # Plot the predictions
# plt.figure(figsize=(10, 6))

# # Plot for wins
# plt.scatter(X_test[y_test == 1]['Avg Crewmate MMR'], probabilities_mapped[y_test == 1], color='green', label='Wins')

# # Plot for losses
# plt.scatter(X_test[y_test == 0]['Avg Crewmate MMR'], probabilities_mapped[y_test == 0], color='red', label='Losses')

# # Add labels and title
# plt.xlabel('Avg Crewmate MMR')
# plt.ylabel('Predicted Probability of Winning')
# plt.title('Predicted Probability vs Avg Crewmate MMR')
# plt.legend()

# # Show the plot
# plt.show()

# scaler = StandardScaler()
# model = joblib.load('logistic_regression_model.pkl') 
# crewmate_mmr = 1000
# impostor_mmr = 1100
# X_new = np.array([[crewmate_mmr, impostor_mmr]])
# X_new_scaled = scaler.transform(X_new)
# probabilities_new = model.predict_proba(X_new_scaled)[:, 1]
# probabilities_mapped_new = map(map_probability, probabilities_new)
# probabilities_mapped_new = np.array(list(probabilities_mapped_new))
# print(f"Predicted probability of winning: { probabilities_mapped_new}")
def map_probability(probability):
    if probability > 0.8:
        return 0.4 + (probability * 0.52)
    elif probability > 0.6:
        return 0.72 + ((probability-0.6) / 2)
    else:
        return 0.57 + (probability * 0.32)
model = joblib.load('logistic_regression_model.pkl')

# Prepare input data for prediction (example)
crewmate_mmr = 1100
impostor_mmr = 1200
X_new = np.array([[crewmate_mmr, impostor_mmr]])
probabilities = model.predict_proba(X_new)[:, 1]
mapped_probability = map_probability(probabilities)

print(f"Predicted probability of winning: {mapped_probability}")