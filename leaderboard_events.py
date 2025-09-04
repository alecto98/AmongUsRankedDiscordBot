import pandas as pd
from player_in_match import PlayerInMatch
from match_class import Match
import os
from rapidfuzz import process
from rapidfuzz import fuzz

class EventsLeaderboard:
    def __init__(self, csv_file=None):
        self.csv_file = csv_file
        self.dtype_dict = {
            'Index': 'int', 'Match ID': 'int', 'Player Name': 'object', 'Match Result': 'object', 'MMR': 'float', 
            'Crewmate MMR': 'float', 'Impostor MMR': 'float', 'Player Team': 'object', 'MMR Gain': 'float',
            'Crewmate MMR Gain': 'float', 'Impostor MMR Gain': 'float', 'Percentage of Winning': 'float',
            'Won': 'bool', 'Alive': 'bool',
            'Alive Time': 'object', 'Match Time': 'object', 'Match Start Time': 'object', 'Rounds Survived': 'int', 'Total Rounds': 'int', 'Ejected in Meeting': 'bool',
            'Placed Votes': 'int', 'Correct Votes': 'int', 'Incorrect Votes': 'int', 'Skip Votes': 'int', 'Voting Accuracy': 'float',
            'Died First Round': 'bool', 'Finished Tasks Alive': 'bool', 'Finished Tasks Dead': 'bool',
            'Tasks Complete': 'int', 'Correct Vote on Eject': 'object', 'Voted Wrong on Crit': 'bool',
            'Voted Right on Crit but Lost': 'bool',
            'Number of Kills': 'int', 'Ejected Early as Imp': 'bool', 'Got Crew Voted': 'object',
            'Solo Imp': 'bool', 'Kills as Solo Imp': 'int', 'Won as Solo Imp': 'bool'
        }
        self.load_leaderboard_events()

    def load_leaderboard_events(self):
        if self.csv_file and os.path.exists(self.csv_file):
            self.events_lb = pd.read_csv(self.csv_file, dtype=self.dtype_dict)
            self.events_lb.fillna(0, inplace=True)
            # Ensure the DataFrame doesn't have an index column
            self.events_lb.reset_index(drop=True, inplace=True)
        else:
            self.create_empty_leaderboard()

    def create_empty_leaderboard(self):
        self.events_lb = pd.DataFrame(columns=self.dtype_dict.keys()).astype(self.dtype_dict)

    def save(self):
        # Always reset to default integer index (do not keep the old index as a column)
        self.events_lb.reset_index(drop=True, inplace=True)
        # Reorder columns so 'Index' is first
        cols = list(self.events_lb.columns)
        if 'Index' in cols:
            cols.insert(0, cols.pop(cols.index('Index')))
        self.events_lb = self.events_lb[cols]
        # Save without writing the DataFrame index
        self.events_lb.to_csv(self.csv_file, index=False, float_format='%.2f')

    def add_player_in_match(self, player:PlayerInMatch, match_start_time=None):
        new_player_in_match_data = {
                'Index': len(self.events_lb),
                'Match ID': player.match_id,
                'Player Name': player.name,
                'Match Result': player.match_result,
                'MMR': player.current_mmr, 
                "Crewmate MMR": player.crewmate_current_mmr,
                "Impostor MMR": player.impostor_current_mmr,
                'Player Team': player.team,
                'MMR Gain': player.mmr_gain,
                'Crewmate MMR Gain': player.crewmate_mmr_gain,
                'Impostor MMR Gain': player.impostor_mmr_gain,
                'Percentage of Winning': player.percentage_of_winning,
                #performance
                'Won': player.won,
                'Alive': player.alive,
                #survivability
                'Alive Time': player.alive_time,
                'Match Time': player.match_time,
                'Match Start Time': match_start_time if match_start_time is not None else getattr(player, 'match_start_time', None),
                'Rounds Survived': player.rounds_survived,
                'Total Rounds': player.total_rounds,
                'Ejected in Meeting': player.ejected_in_meeting,
                #voting accuracy
                'Placed Votes': player.number_of_placed_votes,
                'Correct Votes': player.number_of_correct_votes,
                'Incorrect Votes': player.number_of_incorrect_votes,
                'Skip Votes': player.number_of_skip_votes,
                'Voting Accuracy': player.voting_accuracy,
                #crew
                'Died First Round': player.died_first_round,
                'Finished Tasks Alive': player.finished_tasks_alive,
                'Finished Tasks Dead': player.finished_tasks_dead,
                'Tasks Complete': player.tasks_complete,
                'Correct Vote on Eject': player.correct_vote_on_eject,
                'Voted Wrong on Crit': player.voted_wrong_on_crit,
                'Voted Right on Crit but Lost': player.right_vote_on_crit_but_loss,
                #imp
                'Number of Kills': player.number_of_kills,
                'Ejected Early as Imp': player.ejected_early_as_imp,
                'Got Crew Voted': player.got_crew_voted,
                'Solo Imp': player.solo_imp,
                'Kills as Solo Imp': player.kills_as_solo_imp,
                'Won as Solo Imp': player.won_as_solo_imp
        }
        new_row = pd.DataFrame([new_player_in_match_data])
        self.events_lb = pd.concat([self.events_lb, new_row], ignore_index=True)

    def add_match_events(self, match : Match):
        player : PlayerInMatch
        for player in match.players:
            self.add_player_in_match(player, match_start_time=match.match_start_time)
        self.events_lb = self.events_lb.fillna(0).infer_objects(copy=False)
        self.events_lb.to_csv(self.csv_file, index=False, float_format='%.2f')

    def stats_leaderboard(self):
        # Filter out matches with results that are 'unknown' or 'canceled'
        valid_matches = self.events_lb[~self.events_lb['Match Result'].str.lower().isin(['unknown', 'canceled'])].copy()

        # If no valid matches, return empty DataFrame with proper columns
        if valid_matches.empty:
            empty_df = pd.DataFrame(columns=[
                'Number Of Games Won', 'Number Of Impostor Games Played', 'Number Of Games Died First',
                'Voted Wrong on Crit', 'Voted Right on Crit but Lost', 'Number of Kills',
                'Ejected Early as Imp', 'Got Crew Voted', 'Solo Imp', 'Kills as Solo Imp',
                'Won as Solo Imp', 'Alive Time', 'Match Time', 'Total Number Of Games Played',
                'Number Of Crewmate Games Played', 'Number Of Impostor Games Won',
                'Number Of Crewmate Games Won', 'Crewmate Win Streak', 'Best Crewmate Win Streak',
                'Impostor Win Streak', 'Best Impostor Win Streak', 'Survivability (Impostor)',
                'Survivability (Crewmate)', 'Voting Accuracy (Crewmate games)'
            ])
            empty_df.index.name = 'Player Name'
            return empty_df

        # Ensure 'Alive Time' and 'Match Time' are timedelta objects
        valid_matches['Alive Time'] = pd.to_timedelta(valid_matches['Alive Time'])
        valid_matches['Match Time'] = pd.to_timedelta(valid_matches['Match Time'])
        def count_length(arrays):
            return sum(len(eval(array)) if isinstance(array, str) else len(array) for array in arrays)

        # Group by player and aggregate necessary data
        player_stats = valid_matches.groupby('Player Name').agg({
            'Won': 'sum',
            'Player Team': lambda x: (x == 'impostor').sum(),
            'Died First Round': 'sum',
            'Voted Wrong on Crit': 'sum',
            'Voted Right on Crit but Lost': 'sum',
            'Number of Kills': 'sum',
            'Ejected Early as Imp': 'sum',
            'Got Crew Voted': count_length,
            'Solo Imp': 'sum',
            'Kills as Solo Imp': 'sum',
            'Won as Solo Imp': 'sum',
            'Alive Time': 'sum',
            'Match Time': 'sum'
        }).rename(columns={
            'Player Team': 'Number Of Impostor Games Played',
            'Died First Round': 'Number Of Games Died First',
            'Won': 'Number Of Games Won'
        })

        # Calculate the total number of games played
        player_stats['Total Number Of Games Played'] = valid_matches.groupby('Player Name').size()
        player_stats['Number Of Crewmate Games Played'] = player_stats['Total Number Of Games Played'] - player_stats['Number Of Impostor Games Played']
        player_stats['Number Of Impostor Games Won'] = valid_matches[valid_matches['Player Team'] == 'impostor'].groupby('Player Name')['Won'].sum()
        player_stats['Number Of Crewmate Games Won'] = valid_matches[valid_matches['Player Team'] != 'impostor'].groupby('Player Name')['Won'].sum()

        valid_matches.sort_values(['Player Name', 'Match ID'], inplace=True)

        # Initialize a function to calculate the current winning streak
        def calculate_streaks(df):
            streak = 0
            best_streak = 0
            current_streak = 0
            for won in df['Won']:
                if won:
                    streak += 1
                else:
                    streak = 0
                best_streak = max(best_streak, streak)

            current_streak = streak if df.iloc[-1]['Won'] == 1 else 0
            return current_streak, best_streak

        crewmate_data = valid_matches[valid_matches['Player Team'] != 'impostor']
        impostor_data = valid_matches[valid_matches['Player Team'] == 'impostor']

        # Calculate streaks
        crewmate_streaks = crewmate_data.groupby('Player Name').apply(calculate_streaks, include_groups=False).apply(pd.Series)
        impostor_streaks = impostor_data.groupby('Player Name').apply(calculate_streaks, include_groups=False).apply(pd.Series)

        # Assigning current and best streaks
        if not crewmate_streaks.empty:
            player_stats['Crewmate Win Streak'] = crewmate_streaks[0]
            player_stats['Best Crewmate Win Streak'] = crewmate_streaks[1]
        else:
            player_stats['Crewmate Win Streak'] = 0
            player_stats['Best Crewmate Win Streak'] = 0
            
        if not impostor_streaks.empty:
            player_stats['Impostor Win Streak'] = impostor_streaks[0]
            player_stats['Best Impostor Win Streak'] = impostor_streaks[1]
        else:
            player_stats['Impostor Win Streak'] = 0
            player_stats['Best Impostor Win Streak'] = 0

        # Calculate survivability ratios
        for team in ['impostor', 'crewmate']:
            team_matches = valid_matches[valid_matches['Player Team'] == team]
            survivability = team_matches.groupby('Player Name').apply(
                lambda df: (df['Alive Time'].sum().total_seconds() / df['Match Time'].sum().total_seconds())
                if df['Match Time'].sum() != pd.Timedelta(0) else 0,
                include_groups=False
            )
            player_stats[f'Survivability ({team.capitalize()})'] = survivability.round(3)

        # Calculate voting accuracy for Crewmate games only, excluding those who died first round
        crewmate_data_ex_dead_st = valid_matches[(valid_matches['Player Team'] != 'impostor') & (~valid_matches['Died First Round'])]
        votes_accuracy = crewmate_data_ex_dead_st.groupby('Player Name').apply(
            lambda df: round(df['Correct Votes'].sum() / (df['Placed Votes'].sum() - df['Skip Votes'].sum()) if (df['Placed Votes'].sum() - df['Skip Votes'].sum()) > 0 else 0, 3),
            include_groups=False
        )
        player_stats['Voting Accuracy (Crewmate games)'] = votes_accuracy

        player_stats.index.name = 'Player Name'
        return player_stats

    def remove_match(self, match_id):
        self.events_lb = self.events_lb[self.events_lb['Match ID'] != match_id]
        self.save()
       
    def fetch_mmr_changes(self, player_name:str):
        valid_matches = self.events_lb[~self.events_lb['Match Result'].str.lower().isin(['unknown', 'canceled'])].copy()
        player_data = valid_matches[valid_matches['Player Name'] == player_name]
        mmr_changes = player_data['MMR Gain'].tolist()
        crew_changes = player_data['Crewmate MMR Gain'].tolist()
        imp_changes = player_data['Impostor MMR Gain'].tolist()
        return mmr_changes, crew_changes, imp_changes


