import pandas as pd
import os
from datetime import datetime, timedelta
import json
import logging  # Add this import
import yaml

# Load config from YAML
with open(os.path.join('config', 'config.yaml'), 'r', encoding='utf-8') as f:
    all_configs = yaml.safe_load(f)
use_config = all_configs['use'] if 'use' in all_configs else 'main'
config = all_configs[use_config]

class PremiumMember:
    def __init__(self, member_id, discord_name, server_nickname, discord_id, role, subscription_end, logs_dir, parent):
        self.member_id = str(member_id)
        self.discord_name = discord_name
        self.server_nickname = server_nickname
        self.discord_id = discord_id
        self.role = role
        self.subscription_end = subscription_end
        self.logs_file = os.path.join(logs_dir, f"{self.member_id}_logs.csv")
        self.balance_file = os.path.join(logs_dir, f"{self.member_id}_balance.json")
        self.parent = parent
        self.pending_games = []
        self.init_files()

    def init_files(self):
        # Initialize logs file if it doesn't exist
        if not os.path.exists(self.logs_file):
            df = pd.DataFrame(columns=[
                'timestamp', 'action_type', 'match_id', 'balance_change', 
                'balance_type', 'transaction_id', 'member_name', 'notes'
            ])
            df.to_csv(self.logs_file, index=False)

            # Log initial VIP membership
            self.log_action(
                action_type='membership_start',
                balance_type='membership',
                notes=f'Became {self.role} member'
            )

        # Initialize balance file if it doesn't exist
        if not os.path.exists(self.balance_file):
            initial_balance = self.get_initial_balance()
            role_settings = self.parent.config['vip_roles'].get(self.role, {})
            mmr_type = role_settings.get('mmr_type', 'double')
            balance_data = {
                'discord_name': self.discord_name,
                'server_nickname': self.server_nickname,
                'discord_id': self.discord_id,
                'weekly_balance': initial_balance if mmr_type == 'double' else 0,
                'quad_balance': initial_balance if mmr_type == 'quad' else 0,
                'purchased_balances': {
                    'double': 0,
                    'triple': 0,
                    'quad': 0
                },
                'last_refresh': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                'next_refresh': (datetime.now() + timedelta(days=7)).strftime('%d/%m/%Y %H:%M:%S'),
                'subscription_end': self.subscription_end.strftime('%d/%m/%Y %H:%M:%S')
            }
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.balance_file), exist_ok=True)
            
            with open(self.balance_file, 'w') as f:
                json.dump(balance_data, f, indent=4)

            # Log initial weekly balance
            self.log_action(
                action_type='balance_update',
                balance_change=initial_balance,
                balance_type='weekly_' + mmr_type,
                notes=f'Initial {self.role} weekly balance ({mmr_type})'
            )
        else:
            # Migrate existing balance file to ensure quad fields exist
            try:
                with open(self.balance_file, 'r') as f:
                    data = json.load(f)
                changed = False
                # Ensure purchased_balances structure exists
                if 'purchased_balances' not in data or not isinstance(data['purchased_balances'], dict):
                    data['purchased_balances'] = {'double': 0, 'triple': 0, 'quad': 0}
                    changed = True
                else:
                    for key in ['double', 'triple', 'quad']:
                        if key not in data['purchased_balances']:
                            data['purchased_balances'][key] = 0
                            changed = True
                # Ensure quad weekly bucket exists
                if 'quad_balance' not in data:
                    data['quad_balance'] = 0
                    changed = True
                if changed:
                    with open(self.balance_file, 'w') as f:
                        json.dump(data, f, indent=4)
            except Exception:
                # If migration fails, do not block bot startup
                pass

    def get_initial_balance(self):
        """Get initial balance based on role"""
        return self.get_role_balance(self.role)

    def get_role_balance(self, role):
        """Get the balance amount for a specific VIP role from config"""
        return self.parent.config['vip_roles'].get(role, {}).get('balance', 0)

    def check_and_refresh_balance(self):
        with open(self.balance_file, 'r') as f:
            data = json.load(f)
        
        now = datetime.now()
        try:
            # Parse next refresh date
            next_refresh = datetime.strptime(data['next_refresh'], '%d/%m/%Y %H:%M:%S')
            
            # Get role settings from config
            role_settings = self.parent.config['vip_roles'].get(self.role, {})
            refresh_days = role_settings.get('refresh_days', 7)  # default to 7 if not specified
            mmr_type = role_settings.get('mmr_type', 'double')  # default to double if not specified
            
            if now >= next_refresh:
                # Reset weekly balance
                initial_balance = self.get_initial_balance()
                # Ensure quad field exists
                if 'quad_balance' not in data:
                    data['quad_balance'] = 0
                # Apply refresh based on mmr type
                if mmr_type == 'double':
                    data['weekly_balance'] = initial_balance
                    data['quad_balance'] = data.get('quad_balance', 0)
                elif mmr_type == 'quad':
                    data['quad_balance'] = initial_balance
                    data['weekly_balance'] = data.get('weekly_balance', 0)
                else:
                    # For other types (e.g., triple) keep both weekly stores unchanged
                    data['weekly_balance'] = data.get('weekly_balance', 0)
                    data['quad_balance'] = data.get('quad_balance', 0)
                data['last_refresh'] = now.strftime('%d/%m/%Y %H:%M:%S')
                data['next_refresh'] = (now + timedelta(days=refresh_days)).strftime('%d/%m/%Y %H:%M:%S')
                
                with open(self.balance_file, 'w') as f:
                    json.dump(data, f, indent=4)
                
                # Log the balance refresh
                self.log_action(
                    action_type='balance_refresh',
                    balance_change=initial_balance,
                    balance_type=mmr_type,  # Use the configured MMR type
                    notes=f'Weekly balance refresh ({mmr_type} MMR)'
                )
                
                # Notify about the refresh
                self.parent.notify_balance_refresh(
                    self.member_id,
                    self.discord_id,
                    0,  # old balance
                    initial_balance,  # new balance
                    self.role,
                    mmr_type=mmr_type,  # Pass MMR type to notification
                    next_refresh_days=refresh_days  # Pass refresh days to notification
                )
                
                return True, f"Balance refreshed to {initial_balance} {mmr_type} MMR games"
                
            return True, None
            
        except Exception as e:
            return False, str(e)

    def log_action(self, action_type, match_id=None, balance_change=0, 
                   balance_type='weekly', transaction_id=None, notes=None):
        new_log = pd.DataFrame([{
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'action_type': action_type,
            'match_id': match_id,
            'balance_change': balance_change,
            'balance_type': balance_type,
            'transaction_id': transaction_id,
            'member_name': self.discord_name,
            'notes': notes
        }])
        logs_df = pd.read_csv(self.logs_file)
        logs_df = pd.concat([logs_df, new_log], ignore_index=True)
        logs_df.to_csv(self.logs_file, index=False)

    def get_balance(self, balance_type='double'):
        with open(self.balance_file, 'r') as f:
            data = json.load(f)
        
        if 'quad_balance' not in data:
            data['quad_balance'] = 0
        if balance_type in ['double', 'triple', 'quad']:
            weekly = data.get('weekly_balance', 0) if balance_type == 'double' else (data.get('quad_balance', 0) if balance_type == 'quad' else 0)
            purchased = data['purchased_balances'].get(balance_type, 0)
            return weekly + purchased
        return 0

    def update_balance(self, change, balance_type='double', is_purchased=False, reason='manual', match_id=None, transaction_id=None):
        with open(self.balance_file, 'r') as f:
            data = json.load(f)
        
        if 'quad_balance' not in data:
            data['quad_balance'] = 0
        if is_purchased:
            if balance_type not in data['purchased_balances']:
                data['purchased_balances'][balance_type] = 0
            data['purchased_balances'][balance_type] += change
        else:
            if balance_type == 'double':
                data['weekly_balance'] = data.get('weekly_balance', 0) + change
            elif balance_type == 'quad':
                data['quad_balance'] = data.get('quad_balance', 0) + change
            else:
                # No weekly store for other types currently
                pass
        
        with open(self.balance_file, 'w') as f:
            json.dump(data, f, indent=4)
            
        self.log_action(
            action_type='balance_update',
            match_id=match_id,
            balance_change=change,
            balance_type=f"{'purchased' if is_purchased else 'weekly'}_{balance_type}",
            transaction_id=transaction_id,
            notes=reason
        )

    def use_balance(self, games, channel_id, member_id, balance_type):
        try:
            refresh_success, refresh_result = self.check_and_refresh_balance()
            if not refresh_success and refresh_result is not None:
                return False, f"Error checking balance: {refresh_result}"
                
            with open(self.balance_file, 'r') as f:
                data = json.load(f)
            
            # Ensure fields
            if 'quad_balance' not in data:
                data['quad_balance'] = 0
            # Get current balances for the requested type
            if balance_type == 'double':
                weekly_balance = data.get('weekly_balance', 0)
            elif balance_type == 'quad':
                weekly_balance = data.get('quad_balance', 0)
            else:
                weekly_balance = 0
            purchased_balance = data['purchased_balances'].get(balance_type, 0)
            total_balance = weekly_balance + purchased_balance
            
            # Check if enough total balance
            if total_balance < games:
                return False, f"Insufficient balance. Current total balance: {total_balance} ({weekly_balance} weekly + {purchased_balance} purchased)"
            
            # Calculate how many games to take from each balance type
            games_from_weekly = min(weekly_balance, games)
            games_from_purchased = games - games_from_weekly
            
            # Deduct from weekly first, then purchased if needed
            if games_from_weekly > 0:
                if balance_type == 'double':
                    data['weekly_balance'] = data.get('weekly_balance', 0) - games_from_weekly
                elif balance_type == 'quad':
                    data['quad_balance'] = data.get('quad_balance', 0) - games_from_weekly
                self.log_action(
                    action_type='balance_used',
                    balance_change=-games_from_weekly,
                    balance_type=f'weekly_{balance_type}',
                    notes=f'Used {games_from_weekly} weekly games for {balance_type} MMR'
                )
                
            if games_from_purchased > 0:
                if balance_type not in data['purchased_balances']:
                    data['purchased_balances'][balance_type] = 0
                data['purchased_balances'][balance_type] -= games_from_purchased
                self.log_action(
                    action_type='balance_used',
                    balance_change=-games_from_purchased,
                    balance_type=f'purchased_{balance_type}',
                    notes=f'Used {games_from_purchased} purchased games for {balance_type} MMR'
                )
            
            # Save updated balance
            with open(self.balance_file, 'w') as f:
                json.dump(data, f, indent=4)
            
            # Initialize pending games list for tracking
            self.pending_games = [{
                'channel_id': channel_id,
                'balance_type': balance_type
            } for _ in range(games)]
            
            return True, f"Balance updated successfully (Used {games_from_weekly} weekly + {games_from_purchased} purchased games)"
            
        except Exception as e:
            self.parent.logger.error(f"Error in use_balance: {str(e)}")
            return False, str(e)

    def log_special_match(self, match_id: int, time_of_match: datetime, multiplier='double'):
        if not self.pending_games:
            return False, False, "No pending games to log"  # (success, games_completed, message)

        game_info = self.pending_games.pop(0)
        
        # Add to special matches file
        new_match = pd.DataFrame([{
            'match_id': match_id,
            'timestamp': time_of_match.strftime('%Y-%m-%d %H:%M:%S'),
            'channel_id': game_info['channel_id'],
            'multiplier': multiplier,
            'member_name': self.discord_name,
            'member_id': self.member_id,
            'transaction_id': None
        }])
        
        matches_df = pd.read_csv(self.parent.special_matches_file)
        matches_df = pd.concat([matches_df, new_match], ignore_index=True)
        matches_df.to_csv(self.parent.special_matches_file, index=False)

        # Check if this was the last pending game
        games_completed = len(self.pending_games) == 0

        return True, games_completed, "Match logged successfully"

    def add_purchased_games(self, amount: int, transaction_id: str, balance_type='double'):
        self.update_balance(
            amount,
            balance_type=balance_type,
            is_purchased=True,
            reason='purchased_balance',
            transaction_id=transaction_id
        )
        return True, f"Added {amount} purchased {balance_type} MMR games"

class PremiumMembers:
    def __init__(self, config):
        self.config = config
        self.file_path = config['premium_members_file']
        self.logs_dir = config['vip_logs_directory']
        self.special_matches_file = config['special_matches_file']
        self.vip_roles = config['vip_roles']
        self.logger = logging.getLogger('Premium_Members')
        self.notifications = []
        self.active_special_games = {}  # channel_id: game_info
        
        # Create necessary directories
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.special_matches_file), exist_ok=True)
        
        # Initialize special matches file if it doesn't exist
        if not os.path.exists(self.special_matches_file):
            pd.DataFrame(columns=[
                'match_id', 'channel_id', 'time_of_match', 
                'balance_type', 'completed', 'member_id'
            ]).to_csv(self.special_matches_file, index=False)
        
        # Load or create the CSV file
        self.df = self.load_or_create_file()
        
        # Clean up duplicates automatically during initialization
        self.cleanup_duplicates()
        
        # Initialize members dictionary and next_id
        self.members = {}
        self.next_id = self.initialize_members()

    def cleanup_duplicates(self):
        """Clean up duplicate entries in the CSV file"""
        try:
            # Sort by discord_id and subscription_start to keep the latest entry
            self.df.sort_values(['discord_id', 'subscription_start'], inplace=True)
            
            # Count duplicates before cleanup
            duplicate_count = sum(self.df.duplicated(subset=['discord_id']) & 
                                (self.df['status'] == 'active'))
            
            if duplicate_count > 0:
                # Mark all but the latest entry for each discord_id as inactive
                self.df.loc[
                    self.df.duplicated(subset=['discord_id'], keep='last') & 
                    (self.df['status'] == 'active'),
                    'status'
                ] = 'inactive'
                
                # Save changes
                self.save()
                
                self.logger.info(f"Cleaned up {duplicate_count} duplicate VIP entries")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up duplicates: {str(e)}")

    def load_or_create_file(self):
        try:
            df = pd.read_csv(self.file_path)
            # Ensure discord_id is string type
            df['discord_id'] = df['discord_id'].astype(str)
            return df
        except FileNotFoundError:
            # Create new DataFrame with required columns
            df = pd.DataFrame(columns=[
                'member_id', 'discord_name', 'server_nickname', 'discord_id', 
                'role', 'subscription_start', 'subscription_end', 'status'
            ])
            df.to_csv(self.file_path, index=False)
            return df

    def notify_balance_refresh(self, member_id: str, discord_id: str, old_balance: int, new_balance: int, role: str, mmr_type: str = 'double', next_refresh_days: int = 7):
        """Send notification to admin logs when balance refreshes"""
        try:
            # Create notification message
            message = (
                f"🔄 Weekly Balance Refresh\n"
                f"Member: <@{discord_id}>\n"
                f"Role: {role}\n"
                f"Old Balance: {old_balance}\n"
                f"New Balance: {new_balance} ({mmr_type} MMR)\n"
                f"Next Refresh: <t:{int((datetime.now() + timedelta(days=next_refresh_days)).timestamp())}:R>"
            )
            
            # Add to notification queue for bot to process
            self.notifications.append({
                'type': 'balance_refresh',
                'channel': 'admin_logs',
                'message': message
            })
            
        except Exception as e:
            self.logger.error(f"Error in notify_balance_refresh: {str(e)}")

    def initialize_members(self):
        """Initialize members dictionary and return the next available ID"""
        members = {}
        next_id = 1  # Start with 1
        
        try:
            if not self.df.empty:
                # Extract existing IDs and find the maximum
                existing_ids = []
                for mid in self.df['member_id']:
                    try:
                        if mid.startswith('vip_'):
                            id_num = int(mid.split('_')[1])
                            existing_ids.append(id_num)
                    except (ValueError, IndexError):
                        continue
                
                if existing_ids:
                    next_id = max(existing_ids) + 1
                
                # Initialize active members
                active_members = self.df[self.df['status'] == 'active']
                for _, row in active_members.iterrows():
                    try:
                        subscription_end = datetime.strptime(row['subscription_end'], '%d/%m/%Y %H:%M:%S')
                        member = PremiumMember(
                            row['member_id'],
                            row['discord_name'],
                            row['server_nickname'],
                            row['discord_id'],
                            row['role'],
                            subscription_end,
                            self.logs_dir,
                            self
                        )
                        members[row['member_id']] = member
                    except Exception as e:
                        self.logger.error(f"Error loading member {row['discord_name']}: {str(e)}")
                        continue
        except Exception as e:
            self.logger.error(f"Error initializing members: {str(e)}")
        
        self.members = members
        return next_id

    def save(self):
        self.df.to_csv(self.file_path, index=False)

    def add_member(self, discord_name, discord_id, server_nickname, role, subscription_days, subscription_date=None):
        try:
            # Generate member_id using self.next_id
            member_id = f"vip_{self.next_id}"
            
            # Handle subscription_date input
            if subscription_date is None:
                subscription_date = datetime.now()
            elif isinstance(subscription_date, datetime):
                pass
            else:
                try:
                    if isinstance(subscription_date, str):
                        subscription_date = datetime.strptime(subscription_date, '%d/%m/%Y')
                    else:
                        subscription_date = datetime.combine(subscription_date, datetime.min.time())
                except Exception as e:
                    self.logger.error(f"Error parsing subscription date: {str(e)}")
                    return False, "Invalid date format. Please use DD/MM/YYYY or provide a datetime object."

            # Format dates consistently
            subscription_start = subscription_date.strftime('%d/%m/%Y %H:%M:%S')
            subscription_end = (subscription_date + timedelta(days=subscription_days)).strftime('%d/%m/%Y %H:%M:%S')
            
            # Add new member to DataFrame
            new_member = pd.DataFrame([{
                'member_id': member_id,  # Use the generated member_id
                'discord_name': discord_name,
                'server_nickname': server_nickname,
                'discord_id': str(discord_id),
                'role': role,
                'subscription_start': subscription_start,
                'subscription_end': subscription_end,
                'status': 'active'
            }])
            
            self.df = pd.concat([self.df, new_member], ignore_index=True)
            self.save()
            
            # Initialize member object
            member = PremiumMember(
                member_id,
                discord_name,
                server_nickname,
                str(discord_id),
                role,
                subscription_date + timedelta(days=subscription_days),
                self.logs_dir,
                self
            )
            
            # Add to members dictionary and increment next_id
            self.members[member_id] = member
            self.next_id += 1
            
            return True, member_id
            
        except Exception as e:
            self.logger.error(f"Error adding VIP member: {str(e)}")
            return False, str(e)

    def use_double_mmr(self, member_id, match_id):
        if member_id not in self.members:
            return False, "Member not found"
            
        member = self.members[member_id]
        current_balance = member.get_balance()
        
        if current_balance <= 0:
            return False, "Insufficient balance"
            
        member.update_balance(
            -1,
            reason='used_double_mmr',
            match_id=match_id,
            balance_type='weekly'
        )
        return True, "Double MMR activated"

    def add_purchased_balance(self, member_id, amount, transaction_id):
        if member_id not in self.members:
            return False, "Member not found"
            
        member = self.members[member_id]
        member.update_balance(
            amount,
            reason='purchased_balance',
            balance_type='purchased',
            transaction_id=transaction_id
        )
        return True, f"Added {amount} games to balance"

    def refresh_balances(self):
        """
        Check each member's balance refresh time
        """
        now = datetime.now()
        for member_id, member in self.members.items():
            # Check subscription status
            if now >= member.subscription_end:
                self.df.loc[self.df['member_id'] == member_id, 'status'] = 'expired'
                self.save()
                del self.members[member_id]
                continue
            
            # Check and refresh balance if needed
            member.check_and_refresh_balance()

    def get_member_info(self, member_id):
        if member_id not in self.members:
            return None
            
        member = self.members[member_id]
        with open(member.balance_file, 'r') as f:
            balance_data = json.load(f)
            
        logs_df = pd.read_csv(member.logs_file)
        special_matches_df = pd.read_csv(self.special_matches_file)
        
        # Filter special matches for this member
        special_matches_df = special_matches_df[special_matches_df['member_id'] == member_id]
        
        # Ensure fields
        if 'quad_balance' not in balance_data:
            balance_data['quad_balance'] = 0
        # Calculate total balances
        double_balance = balance_data.get('weekly_balance', 0) + balance_data['purchased_balances'].get('double', 0)
        triple_balance = balance_data['purchased_balances'].get('triple', 0)
        quad_balance = balance_data.get('quad_balance', 0) + balance_data['purchased_balances'].get('quad', 0)
        
        return {
            'member_id': member_id,
            'discord_name': balance_data['discord_name'],
            'server_nickname': balance_data['server_nickname'],
            'discord_id': balance_data['discord_id'],
            'role': member.role,
            'balances': {
                'weekly': balance_data.get('weekly_balance', 0),
                'weekly_quad': balance_data.get('quad_balance', 0),
                'purchased_double': balance_data['purchased_balances'].get('double', 0),
                'purchased_triple': balance_data['purchased_balances'].get('triple', 0),
                'purchased_quad': balance_data['purchased_balances'].get('quad', 0),
                'total_double': double_balance,
                'total_triple': triple_balance,
                'total_quad': quad_balance
            },
            'next_refresh': balance_data['next_refresh'],
            'subscription_end': balance_data['subscription_end'],
            'recent_actions': logs_df.tail(5).to_dict('records'),
            'special_matches': special_matches_df.to_dict('records')
        }

    def get_member_by_discord_id(self, discord_id):
        member_row = self.df[
            (self.df['discord_id'] == str(discord_id)) & 
            (self.df['status'] == 'active')
        ]
        if member_row.empty:
            return None
        
        member_id = member_row.iloc[0]['member_id']
        return self.get_member_info(member_id)

    def get_member_by_name(self, name):
        member_row = self.df[
            (self.df['discord_name'].str.lower() == name.lower()) & 
            (self.df['status'] == 'active')
        ]
        if member_row.empty:
            return None
        
        member_id = member_row.iloc[0]['member_id']
        return self.get_member_info(member_id)

    def use_balance(self, member_id, games: int, channel_id: int, balance_type='double'):
        if member_id not in self.members:
            return False, "Member not found"
            
        member = self.members[member_id]
        success, message = member.use_balance(games, channel_id, member_id, balance_type)
        
        if success:
            # Store game info in dictionary instead of set
            self.active_special_games[channel_id] = {
                'member_id': member_id,
                'games_remaining': games,
                'balance_type': balance_type,
                'member_name': member.discord_name
            }
            
        return success, message

    def log_special_match(self, channel_id: int, match_id: int, time_of_match: datetime):
        if channel_id not in self.active_special_games:
            return False, False, "No active special games in this channel"
            
        active_game = self.active_special_games[channel_id]
        member = self.members[active_game['member_id']]
        
        success, games_completed, message = member.log_special_match(
            match_id=match_id,
            time_of_match=time_of_match,
            multiplier=active_game['balance_type']
        )
        
        if success:
            active_game['games_remaining'] -= 1
            if games_completed or active_game['games_remaining'] <= 0:
                del self.active_special_games[channel_id]  # Remove from dictionary instead of using discard
                
        return success, games_completed, message

    def get_active_special_games(self):
        # Now we can directly return the dictionary
        return self.active_special_games

    def is_channel_using_special_games(self, channel_id: int):
        return channel_id in self.active_special_games

    def upgrade_membership(self, member_id, new_role):
        if member_id not in self.members:
            return False, "Member not found"
            
        if new_role not in self.vip_roles:
            return False, f"Invalid role. Valid roles are: {', '.join(self.vip_roles)}"
            
        member = self.members[member_id]
        old_role = member.role
        
        # Check if it's actually an upgrade
        old_balance = member.get_initial_balance()
        new_balance = self.config['vip_roles'].get(new_role, {}).get('balance', 0)
        
        if new_balance <= old_balance:
            return False, f"Cannot downgrade from {old_role} to {new_role}"

        # Update role in database
        self.df.loc[self.df['member_id'] == member_id, 'role'] = new_role
        self.save()

        # Update member object
        member.role = new_role
        
        # Add the difference in weekly balance
        balance_difference = new_balance - old_balance
        member.update_balance(
            balance_difference,
            balance_type='weekly',
            reason='role_upgrade',
            notes=f'Upgraded from {old_role} to {new_role}'
        )

        return True, f"Successfully upgraded from {old_role} to {new_role} (+{balance_difference} weekly games)"

    def renew_membership(self, member_id, days):
        """Renew a member's subscription by adding days to their current subscription"""
        if member_id not in self.members:
            return False, "Member not found"
            
        member = self.members[member_id]
        
        # Get current subscription end date
        current_end = member.subscription_end
        
        # Calculate new end date
        new_end = current_end + timedelta(days=days)
        
        # Update in database
        self.df.loc[self.df['member_id'] == member_id, 'subscription_end'] = new_end.strftime('%Y-%m-%d %H:%M:%S')
        self.save()
        
        # Update member object
        member.subscription_end = new_end
        
        # Update balance file
        with open(member.balance_file, 'r') as f:
            balance_data = json.load(f)
        
        balance_data['subscription_end'] = new_end.strftime('%Y-%m-%d %H:%M:%S')
        
        with open(member.balance_file, 'w') as f:
            json.dump(balance_data, f, indent=4)
        
        # Log the renewal
        member.log_action(
            action_type='membership_renewal',
            balance_type='membership',
            notes=f'Renewed membership for {days} days'
        )
        
        return True, f"Successfully renewed membership until {new_end.strftime('%Y-%m-%d %H:%M:%S')}"

    def add_special_game(self, channel_id):
        """Mark a channel as using special games"""
        self.active_special_games.add(channel_id)

    def remove_special_game(self, channel_id):
        """Remove a channel from special games tracking"""
        self.active_special_games.discard(channel_id)

    def list_vip_members(self):
        """Get a list of all active VIP members"""
        try:
            # Filter for active members
            active_members = self.df[self.df['status'] == 'active']
            
            if active_members.empty:
                return "No active VIP members found."
            
            # Create embed description
            description = []
            for _, member in active_members.iterrows():
                end_date = datetime.strptime(member['subscription_end'], '%d/%m/%Y %H:%M:%S')
                days_left = (end_date - datetime.now()).days
                
                member_line = (
                    f"**{member['server_nickname']}** ({member['discord_name']})\n"
                    f"Role: {member['role']} | Days Left: {days_left}\n"
                    f"Expires: {member['subscription_end']}\n"
                )
                description.append(member_line)
            
            # Join all member entries with a separator
            full_description = "\n".join(description)
            
            # Create the title with correct member count
            title = f"VIP Members List\nCurrent active VIP members and their details\n"
            title += f"Total VIP Members: {len(active_members)} | Generated by Aiden"
            
            return {
                'title': title,
                'description': full_description
            }
            
        except Exception as e:
            self.logger.error(f"Error listing VIP members: {str(e)}")
            return f"Error listing VIP members: {str(e)}"

##########################################################
# Initialize with imported config
# premium = PremiumMembers(config)



# # Add members directly
# members_to_add = [
#     {
#         "discord_name": "ams_zzz",
#         "discord_id": "1162953896222793758",
#         "server_nickname": "ams",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 9,hour=13, minute=24)
#     },
#     {
#         "discord_name": "04ray",
#         "discord_id": "694600837695143977",
#         "server_nickname": "Ray",
#         "role": "VIPElite",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 12,hour=21, minute=2)
#     },
#     {
#         "server_nickname": "santo",
#         "discord_name": "0yy",
#         "discord_id": "1208347319238529046",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 13,hour=10, minute=25)
#     },
#     {
#         "discord_name": "zalovely",
#         "discord_id": "1251006944798576702",
#         "server_nickname": "zako",
#         "role": "VIP++",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 14,hour=10, minute=28)
#     },
#     {
#         "discord_name": "kingpinjames",
#         "discord_id": "195766452697956352",
#         "server_nickname": "Busa",
#         "role": "VIP++",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 16,hour=11, minute=53)
#     },
#     {
#         "discord_name": "soul.net",
#         "discord_id": "227068780746899456",
#         "server_nickname": "soul",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 19,hour=10, minute=11)
#     },
#     {
#         "discord_name": "dbrev",
#         "discord_id": "405133245592633345",
#         "server_nickname": "Rev",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 20,hour=12, minute=51)
#     },
#     {
#         "discord_name": "dani_94",
#         "discord_id": "530846544694476800",
#         "server_nickname": "Dani",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 23,hour=16, minute=25)
#     },
#     {
#         "discord_name": "cjay04x",
#         "discord_id": "567788277235712001",
#         "server_nickname": "alesha",
#         "role": "VIP",
#         "subscription_days": 28,
#         "subscription_date": datetime(2024, 10, 26,hour=12, minute=51)
#     }

# ]

# for member in members_to_add:
#     success, result = premium.add_member(**member)
#     if not success:
#         print(result)  # Print error message if member wasn't added

# # Get member info
# ams = premium.get_member_by_name("ams_zzz")
# if not ams:
#     print("Member not found")
#     exit()

# match_data = [(2, datetime(2024, 10, 11, 16, 37)), (3, datetime(2024, 10, 11, 16, 45)), 
#               (5, datetime(2024, 10, 11, 17, 10)), (8, datetime(2024, 10, 11, 17, 20)), 
#               (10, datetime(2024, 10, 11, 17, 31))]

# # Use the member_id from the member info dictionary
# if premium.use_balance(ams['member_id'], 5, 1287744166524223541, 'double')[0]:
#     for match_id, match_time in match_data:
#         success, completed, msg = premium.log_special_match(
#             channel_id=1287744166524223541,
#             match_id=match_id,
#             time_of_match=match_time
#         )
#         print(f"Match {match_id}: {msg}")




