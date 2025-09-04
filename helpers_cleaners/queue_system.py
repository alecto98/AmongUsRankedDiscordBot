import discord
from discord.ui import Button, View
import asyncio
import random
from typing import List, Dict, Set
import logging
from discord.ext import commands
from discord import app_commands

class QueueView(discord.ui.View):
    def __init__(self, queue_manager):
        super().__init__(timeout=None)
        self.queue_manager = queue_manager

    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.green, custom_id="join_queue")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle join queue button press"""
        await interaction.response.defer()
        
        # Check if player is already in queue
        if any(p['member'].id == interaction.user.id for p in self.queue_manager.queue):
            await interaction.followup.send("⚠️ You are already in queue!", ephemeral=True)
            return
            
        # Check if player is in an active game
        for lobby in self.queue_manager.active_lobbies.values():
            if interaction.user.id in lobby['members']:
                await interaction.followup.send("⚠️ You are already in a game!", ephemeral=True)
                return
        
        # Add player to queue with VIP status
        roles = interaction.user.roles
        is_vip = any(role.id in self.queue_manager.vip_roles['VIP']['ids'] for role in roles)
        is_vip_plus = any(role.id in self.queue_manager.vip_roles['VIP++']['ids'] for role in roles)
        is_vip_elite = any(role.id in self.queue_manager.vip_roles['VIPElite']['ids'] for role in roles)
        
        new_player = {
            'member': interaction.user,
            'is_vip': is_vip or is_vip_plus or is_vip_elite,
            'is_vip_plus': is_vip_plus,
            'is_vip_elite': is_vip_elite
        }
        
        # Insert player in correct position based on priority
        def get_player_priority(player):
            if player.get('is_vip_elite'):
                return 1
            elif player.get('is_vip_plus'):
                return 2
            elif player.get('is_vip'):
                return 3
            return 4
        
        # Find insertion point
        insert_index = 0
        new_priority = get_player_priority(new_player)
        for i, player in enumerate(self.queue_manager.queue):
            if get_player_priority(player) > new_priority:
                insert_index = i
                break
            insert_index = i + 1
        
        self.queue_manager.queue.insert(insert_index, new_player)
        
        # Notify player
        await interaction.followup.send("✅ You have joined the queue!", ephemeral=True)
        
        # Update queue message
        await self.queue_manager.update_queue_message()
        
        # Check if queue is full
        if len(self.queue_manager.queue) >= self.queue_manager.queue_size and not self.queue_manager.game_starting:
            self.queue_manager.game_starting = True
            await self.queue_manager.start_game()

    @discord.ui.button(label="Leave Queue", style=discord.ButtonStyle.red, custom_id="leave_queue")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle leave queue button press"""
        await interaction.response.defer()
        
        # Check if player is in queue
        was_in_queue = False
        self.queue_manager.queue = [
            p for p in self.queue_manager.queue 
            if p['member'].id != interaction.user.id
        ]
        
        # Notify player
        if was_in_queue:
            await interaction.followup.send("✅ You have left the queue!", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ You were not in the queue!", ephemeral=True)
        
        # Update queue message
        await self.queue_manager.update_queue_message()

class QueueManager:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('QueueManager')
        self.queue = []  # List of {member, is_vip}
        self.active_lobbies = {}  # channel_id: lobby_info
        self.queue_message = None
        self.game_starting = False
        self.view = None
        
        # Config values
        self.ranked_channels = bot.channels
        self.ranked_queue_channel = bot.config['ranked_queue_channel']
        self.vip_roles = bot.config['vip_roles']
        self.queue_size = bot.config.get('queue_size', 10)
        self.queue_timer = bot.config.get('queue_timer', 120)
        self.guild_id = bot.config['guild_id']
        
        # State tracking
        self.game_states = {}  # channel_id: state ("waiting_for_players", "waiting_to_start", "in_progress")
        self.game_embeds = {}  # channel_id: notification_message
        self.lobby_timers = {}  # channel_id: timer_task

    def add_commands(self):
        """Add queue-related commands to the bot"""
        
        @self.bot.command(name="q")
        async def queue_command(ctx):
            """Initialize or show the queue message"""
            if ctx.channel.id != self.ranked_queue_channel:
                return
                
            # Delete the command message
            await ctx.message.delete()
            
            # Delete existing queue message if any
            if self.queue_message:
                try:
                    await self.queue_message.delete()
                except discord.NotFound:
                    pass
            
            # Create new queue message with buttons
            self.view = QueueView(self)
            embed = discord.Embed(
                title="Ranked Queue",
                description="Click the buttons below to join or leave the queue",
                color=discord.Color.blue()
            )
            embed.add_field(
                name=f"Queue (0 players)",
                value="Empty",
                inline=False
            )
            embed.set_footer(text="AU++ Queue System")
            
            self.queue_message = await ctx.send(embed=embed, view=self.view)

        @self.bot.command(name="force_start")
        @commands.has_permissions(administrator=True)
        async def force_start(ctx):
            """Force start a game with the current queue (admin only)"""
            if ctx.channel.id != self.ranked_queue_channel:
                return
                
            if len(self.queue) < self.queue_size:
                await ctx.send(f"⚠️ Not enough players in queue ({len(self.queue)}/{self.queue_size})", delete_after=5)
                return
                
            if self.game_starting:
                await ctx.send("⚠️ A game is already starting!", delete_after=5)
                return
                
            self.game_starting = True
            await self.start_game()
            await ctx.message.delete()

        @self.bot.command(name="clear_queue")
        @commands.has_permissions(administrator=True)
        async def clear_queue(ctx):
            """Clear the current queue (admin only)"""
            if ctx.channel.id != self.ranked_queue_channel:
                return
                
            self.queue.clear()
            await self.update_queue_message()
            await ctx.message.delete()
            await ctx.send("✅ Queue cleared!", delete_after=5)

    async def start_game(self):
        """Initialize a new game when queue is full"""
        try:
            self.logger.info("\n=== Starting New Game ===")
            
            # Sort queue by VIP and select players
            self.queue.sort(key=lambda x: x['is_vip'], reverse=True)
            selected_players = self.queue[:self.queue_size]
            self.queue = self.queue[self.queue_size:]
            
            self.logger.info(f"Selected Players: {[p['member'].display_name for p in selected_players]}")

            # Find available lobby
            available_lobby = None
            lobby_name = None
            for name, lobby in self.ranked_channels.items():
                if not self.active_lobbies.get(lobby['voice_channel_id']):
                    available_lobby = lobby
                    lobby_name = name.upper()
                    self.logger.info(f"Found available lobby: {lobby_name}")
                    break

            if not available_lobby:
                self.logger.error("No available lobbies found")
                self.queue.extend(selected_players)
                return

            # Get channels
            voice_channel = self.bot.get_channel(available_lobby['voice_channel_id'])
            text_channel = self.bot.get_channel(available_lobby['text_channel_id'])
            queue_channel = self.bot.get_channel(self.ranked_queue_channel)
            guild = self.bot.get_guild(self.guild_id)

            # Register active lobby
            self.active_lobbies[available_lobby['voice_channel_id']] = {
                'members': {p['member'].id for p in selected_players},
                'channel': voice_channel,
                'lobby_name': lobby_name,
                'players': selected_players,
                'role_id': available_lobby['role']
            }
            
            # Assign lobby roles to selected players
            role = guild.get_role(available_lobby['role'])
            if role:
                for player in selected_players:
                    await player['member'].add_roles(role)
                    self.logger.info(f"Assigned {role.name} to {player['member'].display_name}")
            else:
                self.logger.error(f"Could not find role with ID {available_lobby['role']}")
            
            self.logger.info(f"Registered lobby with {len(selected_players)} players")

            # Move players to voice channel
            self.logger.info("Moving players to voice channel...")
            move_tasks = []
            for player in selected_players:
                if player['member'].voice:
                    self.logger.info(f"Moving {player['member'].display_name} to voice channel")
                    move_tasks.append(player['member'].move_to(voice_channel))
            if move_tasks:
                await asyncio.gather(*move_tasks)

            # Create and send initial embed
            embed = await self.create_game_embed(lobby_name, voice_channel, text_channel, selected_players)
            mentions = " ".join(p['member'].mention for p in selected_players)
            notification = await queue_channel.send(
                content=f"**🟠 LOBBY STARTING!** {mentions}",
                embed=embed
            )

            # Set initial state and store references
            self.game_states[available_lobby['voice_channel_id']] = "waiting_for_players"
            self.game_embeds[available_lobby['voice_channel_id']] = notification

            # Check initial state of voice channel
            current_members = set(m.id for m in voice_channel.members)
            expected_members = self.active_lobbies[available_lobby['voice_channel_id']]['members']
            all_present = expected_members.issubset(current_members)
            
            self.logger.info(f"\nInitial Voice Channel State:")
            self.logger.info(f"Current members: {[m.display_name for m in voice_channel.members]}")
            self.logger.info(f"Expected members: {[p['member'].display_name for p in selected_players]}")
            self.logger.info(f"All players present: {all_present}")

            if all_present:
                self.logger.info("All players already in channel - setting waiting_to_start state")
                await self.set_lobby_state(available_lobby['voice_channel_id'], "waiting_to_start")
            else:
                self.logger.info("Starting join timer for missing players")
                await self.start_join_timer(available_lobby['voice_channel_id'])

        except Exception as e:
            self.logger.error(f"Error starting game: {str(e)}", exc_info=True)
            if available_lobby and available_lobby['voice_channel_id'] in self.active_lobbies:
                del self.active_lobbies[available_lobby['voice_channel_id']]
            self.queue.extend(selected_players)
        finally:
            self.game_starting = False
            await self.update_queue_message()

    async def create_game_embed(self, lobby_name, voice_channel, text_channel, players):
        """Create the initial game embed"""
        embed = discord.Embed(
            title=f"🟠 Waiting for Players - {lobby_name}",
            description=f"Players have **{self.queue_timer} seconds** to join {voice_channel.mention}!",
            color=discord.Color.orange()
        )
        players_text = "\n".join([
            f"{i+1}. {'👑 ' if p['is_vip'] else ''}{p['member'].mention}"
            for i, p in enumerate(players)
        ])
        embed.add_field(name="Players", value=players_text, inline=False)
        embed.add_field(name="Voice Channel", value=voice_channel.mention, inline=True)
        embed.add_field(name="Text Channel", value=text_channel.mention, inline=True)
        embed.set_footer(text="AU++ Queue System")
        return embed

    async def handle_voice_state_update(self, member, before, after):
        """Handle voice state changes"""
        try:
            before_channel_id = before.channel.id if before and before.channel else None
            after_channel_id = after.channel.id if after and after.channel else None
            
            # Check if member left a lobby channel
            if before_channel_id and before_channel_id in self.active_lobbies:
                lobby_info = self.active_lobbies[before_channel_id]
                if member.id in lobby_info['members']:
                    # Remove lobby role when player leaves
                    role = member.guild.get_role(lobby_info['role_id'])
                    if role and role in member.roles:
                        await member.remove_roles(role)
                        self.logger.info(f"Removed {role.name} from {member.display_name} (left channel)")
            
            # Continue with normal lobby status check
            for voice_channel_id, lobby_info in self.active_lobbies.items():
                if voice_channel_id in (before_channel_id, after_channel_id):
                    if member.id in lobby_info['members']:
                        voice_channel = self.bot.get_channel(voice_channel_id)
                        await self.check_lobby_status(voice_channel_id, voice_channel)

        except Exception as e:
            self.logger.error(f"Error in handle_voice_state_update: {str(e)}", exc_info=True)

    async def check_lobby_status(self, voice_channel_id: int, voice_channel):
        """Check and update lobby status based on current voice channel state"""
        try:
            lobby_info = self.active_lobbies[voice_channel_id]
            current_state = self.game_states.get(voice_channel_id)
            
            self.logger.info(f"Checking status for {lobby_info['lobby_name']}")
            self.logger.info(f"Current State: {current_state}")
            
            # Get current voice channel members
            current_members = set(m.id for m in voice_channel.members)
            expected_members = lobby_info['members']
            
            self.logger.info(f"Current members in VC: {[m.display_name for m in voice_channel.members]}")
            self.logger.info(f"Expected members: {[p['member'].display_name for p in lobby_info['players']]}")
            
            # Check if all expected players are present
            all_present = expected_members.issubset(current_members)
            self.logger.info(f"All players present: {all_present}")
            
            if len(current_members.intersection(expected_members)) < self.queue_size:
                # Missing some players, start/restart timer
                if current_state != "waiting_for_players":
                    self.logger.info("Missing players - starting timer")
                    await self.set_lobby_state(voice_channel_id, "waiting_for_players")
                    await self.start_join_timer(voice_channel_id)
            elif all_present:
                # All players present, update state
                if current_state != "waiting_to_start":
                    self.logger.info("All players present - setting to waiting_to_start")
                    await self.set_lobby_state(voice_channel_id, "waiting_to_start")
                    await self.cancel_timer(voice_channel_id)
                
        except Exception as e:
            self.logger.error(f"Error checking lobby status: {str(e)}")

    async def set_lobby_state(self, voice_channel_id: int, new_state: str):
        """Central method to handle all lobby state changes"""
        try:
            lobby_info = self.active_lobbies[voice_channel_id]
            notification = self.game_embeds[voice_channel_id]
            
            self.logger.info(f"Changing state for {lobby_info['lobby_name']}: {new_state}")
            
            # Update state
            self.game_states[voice_channel_id] = new_state
            
            # Update embeds based on new state
            embed = notification.embeds[0]
            
            if new_state == "waiting_for_players":
                embed.title = f"🟠 Waiting for Players - {lobby_info['lobby_name']}"
                embed.description = f"Players have **{self.queue_timer} seconds** to join the voice channel!"
                embed.color = discord.Color.orange()
                # Start/restart timer
                await self.start_join_timer(voice_channel_id)
                
            elif new_state == "waiting_to_start":
                embed.title = f"🟡 Starting Game - {lobby_info['lobby_name']}"
                embed.description = "All players have joined! Game is starting..."
                embed.color = discord.Color.yellow()
                # Cancel timer if exists
                await self.cancel_timer(voice_channel_id)
                
            # Update the notification embed
            await notification.edit(embed=embed)
            
            # Update the queue message to reflect the new state
            await self.update_queue_message()
            
        except Exception as e:
            self.logger.error(f"Error setting lobby state: {str(e)}")

    async def start_join_timer(self, voice_channel_id: int):
        """Start or restart the join timer"""
        try:
            # Cancel existing timer if any
            await self.cancel_timer(voice_channel_id)
            
            # Create new timer
            self.lobby_timers[voice_channel_id] = asyncio.create_task(
                self.timer_expired(voice_channel_id)
            )
            
            self.logger.info(f"Started {self.queue_timer}s timer for voice channel {voice_channel_id}")
            
        except Exception as e:
            self.logger.error(f"Error starting timer: {str(e)}")

    async def cancel_timer(self, voice_channel_id: int):
        """Cancel existing timer if any"""
        if voice_channel_id in self.lobby_timers:
            self.lobby_timers[voice_channel_id].cancel()
            del self.lobby_timers[voice_channel_id]

    async def timer_expired(self, voice_channel_id: int):
        """Handle timer expiration"""
        try:
            await asyncio.sleep(self.queue_timer)
            
            if voice_channel_id not in self.active_lobbies:
                return
            
            lobby_info = self.active_lobbies[voice_channel_id]
            voice_channel = self.bot.get_channel(voice_channel_id)
            guild = self.bot.get_guild(self.guild_id)
            
            # Get current members in voice channel
            current_members = set(m.id for m in voice_channel.members)
            expected_members = lobby_info['members']
            
            # Identify missing players
            missing_players = [
                player for player in lobby_info['players']
                if player['member'].id not in current_members
            ]
            
            # Get players who were in VC
            lobby_members_in_vc = [
                player for player in lobby_info['players']
                if player['member'].id in current_members
            ]
            
            self.logger.info(f"Players in VC: {[p['member'].display_name for p in lobby_members_in_vc]}")
            self.logger.info(f"Missing players: {[p['member'].display_name for p in missing_players]}")
            
            # Sort queue by priority: canceled match players -> VIPElite -> VIP++ -> VIP -> normal
            def get_player_priority(player):
                roles = [r.id for r in player['member'].roles]
                if player in lobby_members_in_vc:
                    return 0  # Highest priority for players from canceled match
                for role_name, role_info in self.vip_roles.items():
                    if any(role_id in roles for role_id in role_info['ids']):
                        if role_name == 'VIPElite':
                            return 1
                        elif role_name == 'VIP++':
                            return 2
                        elif role_name == 'VIP':
                            return 3
                return 4  # Normal players
            
            # Add players who were in VC back to queue with priority
            if lobby_members_in_vc:
                # Sort existing queue by priority
                self.queue.sort(key=get_player_priority)
                # Add canceled match players at the start
                self.queue = lobby_members_in_vc + self.queue
                await self.update_queue_message()
                
                mentions = " ".join(p['member'].mention for p in lobby_members_in_vc)
                returned_players_msg = f"The following players have been returned to queue with high priority: {mentions}"
            else:
                returned_players_msg = "No players were in the voice channel."
            
            # Notify about game cancellation in queue channel
            notification = self.game_embeds[voice_channel_id]
            await notification.reply(
                "⚠️ Timer expired! Game has been cancelled.\n" +
                returned_players_msg
            )
            
            # Send notification to admin logs about missing players
            admin_logs_channel = self.bot.get_channel(self.bot.config['admin_logs_channel'])
            if admin_logs_channel and missing_players:
                missing_mentions = " ".join(p['member'].mention for p in missing_players)
                await admin_logs_channel.send(
                    f"⚠️ Game in {lobby_info['lobby_name']} was cancelled because the following players failed to join:\n"
                    f"{missing_mentions}"
                )
            
            # Clean up lobby
            await self.cleanup_lobby(voice_channel_id)
                
        except asyncio.CancelledError:
            self.logger.info(f"Timer cancelled for voice channel {voice_channel_id}")
        except Exception as e:
            self.logger.error(f"Error in timer expiration: {str(e)}")

    async def cleanup_lobby(self, voice_channel_id: int):
        """Clean up a lobby and all associated data"""
        try:
            if voice_channel_id not in self.active_lobbies:
                return
            
            lobby_info = self.active_lobbies[voice_channel_id]
            guild = self.bot.get_guild(self.guild_id)
            
            # Remove roles from any remaining players
            role = guild.get_role(lobby_info['role_id'])
            if role:
                for player in lobby_info['players']:
                    if role in player['member'].roles:
                        await player['member'].remove_roles(role)
                        self.logger.info(f"Removed {role.name} from {player['member'].display_name} (cleanup)")
            
            # Cancel timer and clean up lobby data
            await self.cancel_timer(voice_channel_id)
            del self.active_lobbies[voice_channel_id]
            if voice_channel_id in self.game_states:
                del self.game_states[voice_channel_id]
            if voice_channel_id in self.game_embeds:
                notification = self.game_embeds[voice_channel_id]
                await notification.delete()
                del self.game_embeds[voice_channel_id]
            
            await self.update_queue_message()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up lobby: {str(e)}")

    async def update_queue_message(self):
        """Update the queue status message"""
        try:
            if not self.queue_message:
                return
                
            embed = discord.Embed(
                title="Ranked Queue",
                description="Click the buttons below to join or leave the queue",
                color=discord.Color.blue()
            )
            
            # Queue status
            queue_text = "\n".join([
                f"{i+1}. {'👑 ' if p.get('is_vip_elite') else '💎 ' if p.get('is_vip_plus') else '⭐ ' if p.get('is_vip') else ''}{p['member'].mention}"
                for i, p in enumerate(self.queue)
            ]) or "Empty"
            
            embed.add_field(
                name=f"Queue ({len(self.queue)} players)",
                value=queue_text,
                inline=False
            )
            
            # Active games with detailed status
            if self.active_lobbies:
                games_text = ""
                for channel_id, lobby in self.active_lobbies.items():
                    state = self.game_states.get(channel_id, "unknown")
                    
                    if state == "in_progress":
                        games_text += f"🟢 {lobby['lobby_name']}: Game in Progress\n"
                    elif state == "waiting_to_start":
                        games_text += f"🟡 {lobby['lobby_name']}: Starting Game\n"
                    elif state == "waiting_for_players":
                        games_text += f"🟠 {lobby['lobby_name']}: Waiting for Players\n"
                    else:
                        games_text += f"⚪ {lobby['lobby_name']}: Unknown Status\n"
                
                if games_text:
                    embed.add_field(
                        name="Active Games",
                        value=games_text,
                        inline=False
                    )
            
            embed.set_footer(text="AU++ Queue System")
            await self.queue_message.edit(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error updating queue message: {str(e)}")

    async def initialize_queue_embed(self):
        """Initialize queue embed on bot startup"""
        try:
            # Get the queue channel
            queue_channel = self.bot.get_channel(self.ranked_queue_channel)
            if not queue_channel:
                self.logger.error(f"Could not find queue channel: {self.ranked_queue_channel}")
                return

            # Clear all messages in the queue channel
            self.logger.info("Clearing queue channel messages...")
            try:
                await queue_channel.purge(limit=100)
            except Exception as e:
                self.logger.error(f"Error clearing queue channel: {str(e)}")

            # Create new queue message with buttons
            self.view = QueueView(self)
            embed = discord.Embed(
                title="Ranked Queue",
                description="Click the buttons below to join or leave the queue",
                color=discord.Color.blue()
            )
            embed.add_field(
                name=f"Queue (0 players)",
                value="Empty",
                inline=False
            )
            embed.set_footer(text="AU++ Queue System")
            
            # Send new queue message
            self.logger.info("Creating new queue message...")
            self.queue_message = await queue_channel.send(embed=embed, view=self.view)
            
            # Reset queue and game states
            self.queue.clear()
            self.active_lobbies.clear()
            self.game_states.clear()
            self.game_embeds.clear()
            self.lobby_timers.clear()
            self.game_starting = False
            
            self.logger.info("Queue system initialized successfully")

        except Exception as e:
            self.logger.error(f"Error initializing queue embed: {str(e)}", exc_info=True)

    async def handle_game_started(self, game_channel, game_code, match_id):
        """Update queue embed when a game starts"""
        try:
            voice_channel_id = game_channel['voice_channel_id']
            if voice_channel_id in self.active_lobbies:
                # Update game state
                self.game_states[voice_channel_id] = "in_progress"
                
                # Get lobby name from active lobbies
                lobby_name = self.active_lobbies[voice_channel_id]['lobby_name']
                
                # Update embed
                await self.update_queue_message()
                
                # Update game notification embed if it exists
                if voice_channel_id in self.game_embeds:
                    game_msg = self.game_embeds[voice_channel_id]
                    embed = discord.Embed(
                        title=f"Game Started in {lobby_name}",
                        description=f"🎮 Match ID: {match_id}\n🔑 Code: {game_code}",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="Status",
                        value="🟢 Game in Progress",
                        inline=False
                    )
                    await game_msg.edit(embed=embed)
                    
                self.logger.info(f"Game started in {lobby_name} with Match ID: {match_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling game start: {str(e)}")

    async def handle_game_end(self, voice_channel_id, match_id, game_code):
        """Update queue embed when a game ends"""
        try:
            if voice_channel_id in self.active_lobbies:
                lobby_info = self.active_lobbies[voice_channel_id]
                lobby_name = lobby_info['lobby_name']
                
                # Update game state
                if voice_channel_id in self.game_states:
                    del self.game_states[voice_channel_id]
                
                # Update game notification embed if it exists
                if voice_channel_id in self.game_embeds:
                    game_msg = self.game_embeds[voice_channel_id]
                    embed = discord.Embed(
                        title=f"Game Ended in {lobby_name}",
                        description=f"✅ Match ID: {match_id} has concluded",
                        color=discord.Color.blue()
                    )
                    await game_msg.edit(embed=embed)
                    
                    # Delete the message after a delay
                    await asyncio.sleep(30)
                    await game_msg.delete()
                    del self.game_embeds[voice_channel_id]
                
                # Clean up lobby data
                if voice_channel_id in self.active_lobbies:
                    del self.active_lobbies[voice_channel_id]
                
                # Update queue message
                await self.update_queue_message()
                
                self.logger.info(f"Game ended in {lobby_name} with Match ID: {match_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling game end: {str(e)}")
