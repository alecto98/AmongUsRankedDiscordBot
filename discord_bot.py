import asyncio
import difflib
import json
import logging
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from discord import app_commands, Button, ButtonStyle

from file_processing import FileHandler
from match_class import Match
from player_in_match import PlayerInMatch
from premium_members import PremiumMembers
from views.votes_view import VotesView

from rapidfuzz import fuzz, process
import pandas as pd
import matplotlib.pyplot as plt
import os
import aiohttp
import yaml
import sys

with open(os.path.join('config', 'config.yaml'), 'r', encoding='utf-8') as f:
    all_configs = yaml.safe_load(f)
with open(os.path.join('config', 'emojis.yaml'), 'r', encoding='utf-8') as f:
    all_emojis = yaml.safe_load(f)

# Determine which config to use (main or test) from command-line or default to 'main'
if len(sys.argv) > 1 and sys.argv[1] in all_configs:
    use_config = sys.argv[1]
else:
    use_config = all_configs['use'] if 'use' in all_configs else 'main'

config = all_configs[use_config]
emojis = all_emojis[all_emojis['use'] if 'use' in all_emojis else 'main']

class DiscordBot(commands.Bot):
    def __init__(self, command_prefix='!', token=None, variables=None, **options):
        # init loggers
        # Configure root logger with handlers first
        root_handlers = [
            logging.FileHandler("DiscordBot.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=root_handlers
        )

        # Set levels for external loggers
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("websockets").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)
        logging.getLogger("matplotlib").setLevel(logging.INFO)
        
        # Configure Discord_Bot logger without additional handlers
        self.logger = logging.getLogger('Discord_Bot')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Prevent duplicate logs
        for handler in root_handlers:
            self.logger.addHandler(handler)

        # Initialize config first
        if variables is None:
            raise ValueError("Variables configuration is required")
        self.config = config

        # init guild variables
        try:
            self.matches_path = self.config['matches_path']
            self.channels = self.config['ranked_channels']
            self.guild_id = self.config['guild_id']
            self.match_logs = self.config['match_logs_channel']
            self.bot_commands = self.config['bot_commands_channel']
            self.moderator_role = self.config['moderator_role_id']
            self.staff_role = self.config['staff_role_id']
            self.owner_role = self.config['owner_role_id']
            self.cancels_channel = self.config['cancels_channel']
            self.admin_logs_channel = self.config['admin_logs_channel']
            self.ranked_chat_channel = self.config['ranked_chat']
            self.season_name : str = self.config['season_name'] 
            self.blocked_role_id = self.config['blocked_role_id']  
            self.ranked_access_role_id = self.config['ranked_access_role_id'] 
            self.premium = PremiumMembers(self.config)
        except KeyError as e:
            self.logger.error(f"Missing required configuration key: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing bot: {e}")
            raise

        # Rest of initialization
        self.ratio = 80
        self.fuzz_rapid = False
        self.auto_mute = True
        self.games_in_progress = []
        self.who_enabled = True
        self.version = "v1.3"
        self.token = token

        # init subclasses
        self.file_handler = FileHandler(self.matches_path, self.season_name)
        self.leaderboard = self.file_handler.leaderboard

        #check for unprocessed matches
        self.logger.info(f"Loading all match files from{self.matches_path}")
        match = self.file_handler.process_unprocessed_matches()
        if match:
            self.logger.info("Leaderboard has been updated")
            self.leaderboard.load_leaderboard()
        else:
            self.logger.info("Leaderboard is already up to date")

        # init bot
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.voice_states = True
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None, **options)
        self.add_commands()
        self.add_events()
        
        self.logger.info(f'Imported match files from {self.matches_path}')
        self.logger.info(f'Imported Database location from {self.season_name.replace(" ", "_")}_leaderboard.csv')
        self.logger.info(f'Guild ID is {self.guild_id}')

    def add_commands(self):
        @self.hybrid_command(name="stats", description = "Display Stats of yourself or a player")
        @app_commands.describe(player="Player name or @Player")
        async def stats(ctx: Context, player: Optional[str] = None):
            try:
                await ctx.defer(ephemeral=False)
                
                role_ranges = {
                    "Iron": (None, 850, "https://i.ibb.co/KNQNBdN/Iron.png"),
                    "Bronze": (850, 950, "https://i.ibb.co/BznPYmC/bronze.png"),
                    "Silver": (950, 1050, "https://i.ibb.co/PTHxR8S/silver.png"),
                    "Gold": (1050, 1150, "https://i.ibb.co/H7pZMvW/Gold.png"),
                    "Platinum": (1150, 1250, "https://i.ibb.co/C96H6ZV/plat.png"),
                    "Diamond": (1250, 1350, "https://i.ibb.co/f40p0Y5/diamond.png"),
                    "Master": (1350, 1450, "https://i.ibb.co/mHvMQPx/master.png"),
                    "Warrior": (1450, None, "https://i.ibb.co/RYjj8yC/warrior.png")
                }
                
                if ctx.channel.id != self.bot_commands and self.staff_role not in [role.id for role in ctx.author.roles]:
                    await ctx.send(f"Please use https://discord.com/channels/{self.guild_id}/{self.bot_commands}", delete_after=5)
                    await ctx.message.delete(delay=1)
                    return

                thumbnail = self.guild.icon.url if self.guild.icon else None
                if player is None:
                    player_name = ctx.author.display_name
                    player_row = self.leaderboard.get_player_by_discord(ctx.author.id)
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif player.startswith("<@"):
                    player_id = player.strip('<@!>')
                    player_row = self.leaderboard.get_player_by_discord(player_id)
                    member = self.guild.get_member(int(player_id))
                    if member is None:
                        await ctx.send(f"Member not found.", ephemeral=True)
                        return
                    player_name = member.display_name
                    thumbnail = member.avatar.url if member.avatar else member.default_avatar.url
                else:
                    player_name = player
                    player_row = self.leaderboard.get_player_row(player_name)
                    if player_row is None:
                        await ctx.send(f"Player {player_name} not found.", ephemeral=True)
                        return
                    
                if player_row is None:
                    await ctx.send(f"Player {player_name} not found.", ephemeral=True)
                    return
                
                player_mmr = self.leaderboard.get_player_mmr(player_row)
                embed_url = ""
                player_role = None
                for role, (lower_bound, upper_bound, url) in role_ranges.items():
                    if (lower_bound is None or player_mmr >= lower_bound) and (upper_bound is None or player_mmr <= upper_bound):
                        embed_url = url
                        player_role = role
                        break

                rank_emoji=emojis['ranks_emojis'].get(player_role, "")
                ace_emoji=emojis['ranks_emojis'].get("Ace" if self.leaderboard.get_player_ranking(player_row)==1 else "", "")
                sherlock_emoji=emojis['ranks_emojis'].get("Sherlock" if self.leaderboard.is_player_sherlock(player_name) else "", "") 
                jack_emoji=emojis['ranks_emojis'].get("Jack" if self.leaderboard.is_player_jack_the_ripper(player_name) else "", "") 
                
                embed = discord.Embed(title=f"{rank_emoji}Player {player_name} Stats{rank_emoji}", color=discord.Color.purple())
                embed.set_thumbnail(url=thumbnail)

                general_stats = (
                    f"- **Rank:** {self.leaderboard.get_player_ranking(player_row)}\n"
                    f"- **MMR:** {self.leaderboard.get_player_mmr(player_row)}\n"
                    f"- **Games Played:** {int(player_row['Total Number Of Games Played'])}\n"
                    f"- **Games Won:** {int(player_row['Number Of Games Won'])}\n"
                    f"- **Win Rate:** {round(self.leaderboard.get_player_win_rate(player_row), 1)}%"
                )
                
                crew_stats = (
                    f"- **MMR:** {self.leaderboard.get_player_crew_mmr(player_row)}\n"
                    f"- **Games Played:** {int(player_row['Number Of Crewmate Games Played'])}\n"
                    f"- **Games Won:** {int(player_row['Number Of Crewmate Games Won'])}\n"
                    f"- **WinRate:** {round(self.leaderboard.get_player_crew_win_rate(player_row), 1)}%\n"
                    f"- **WinStreak:** {int(player_row['Crewmate Win Streak'])}\n"
                    f"- **Best WinStreak:** {int(player_row['Best Crewmate Win Streak'])}\n"
                    f"- **Survivability:** {player_row['Survivability (Crewmate)']}"
                )

                imp_stats = (
                    f"- **MMR:** {self.leaderboard.get_player_imp_mmr(player_row)}\n"
                    f"- **Games Played:** {int(player_row['Number Of Impostor Games Played'])}\n"
                    f"- **Games Won:** {int(player_row['Number Of Impostor Games Won'])}\n"
                    f"- **WinRate:** {round(self.leaderboard.get_player_imp_win_rate(player_row), 1)}%\n"
                    f"- **Win Streak:** {int(player_row['Impostor Win Streak'])}\n"
                    f"- **Best Win Streak:** {int(player_row['Best Impostor Win Streak'])}\n"
                    f"- **Survivability:** {player_row['Survivability (Impostor)']}"
                )
                
                voting_stats = (
                    f"- **Voting Accuracy:** {round(self.leaderboard.get_player_voting_accuracy(player_row) * 100, 1)}%\n"
                    f"- **Voted :x: on Critical:** {int(player_row['Voted Wrong on Crit'])}\n"
                    f"- **Voted :white_check_mark: on Crit & Lost:** {int(player_row['Voted Right on Crit but Lost'])}"
                )

                embed.add_field(name=f"{ace_emoji}__**General Stats**__{ace_emoji}", value=general_stats, inline=False)
                embed.add_field(name=f"{sherlock_emoji}__**Crewmate Stats**__{sherlock_emoji}", value=crew_stats, inline=True)
                embed.add_field(name=f"{jack_emoji}__**Impostor Stats**__{jack_emoji}", value=imp_stats, inline=True)
                embed.add_field(name="__**Voting Stats**__", value=voting_stats, inline=False)
                embed.set_image(url=embed_url)
                embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
                await ctx.send(embed=embed)
                self.logger.info(f'Sent stats of {player_name} to Channel {ctx.channel.name}')
                
            except Exception as e:
                self.logger.error(f"Error in stats command: {str(e)}")
                await ctx.send(f"An error occurred while fetching stats: {str(e)}", ephemeral=True)

        @self.hybrid_command(name="lb", description = "Display Leaderboard of the top players")
        @app_commands.describe(length = "length of the leaderboard")
        @app_commands.describe(type = "[crew/imp/None]")
        async def lb(ctx:Context, length: Optional[int] = None, type: Optional[str] = None):
            if ctx.channel.id != self.bot_commands and self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send(f"Please use https://discord.com/channels/{self.guild_id}/{self.bot_commands}", delete_after=5)
                await ctx.message.delete(delay=1)
                return
            players_per_field = 20

            if type:
                if type.startswith('imp'):
                    top_players = self.leaderboard.top_players_by_impostor_mmr(length or 10)  
                    title = f"{length or 10} Top Impostors"
                    color = discord.Color.red()

                elif type.startswith('crew'):
                    top_players = self.leaderboard.top_players_by_crewmate_mmr(length or 10)
                    title = f"{length or 10} Top Crewmates"
                    color = discord.Color.green()

            else:
                top_players = self.leaderboard.top_players_by_mmr(length or 10)
                title = f"{length or 10} Top Players Overall"
                color = discord.Color.blue()


            embed = discord.Embed(title=title, color=color)
            embed.set_thumbnail(url=self.guild.icon.url)

            chunks = [top_players[i:i + players_per_field] for i in range(0, len(top_players), players_per_field)]

            for i, chunk in enumerate(chunks):
                leaderboard_text = ""
                for index, row in chunk.iterrows():
                    rank = emojis['top_emojis'][index] if index < len(emojis['top_emojis']) else f"**{index + 1}.**"
                    leaderboard_text += f"- {rank} **{row['Player Name']}**\n"
                    leaderboard_text += f"MMR: {row.iloc[1]}\n"
                embed.add_field(name=f"", value=leaderboard_text, inline=False)

            embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent stats of {length or 10} {title} to Channel {ctx.channel.name}')

        @self.command(name="who")
        async def who(ctx: Context):
            # Only respond in DMs
            if ctx.guild is not None:
                return

            # Only allow specific Discord user IDs
            if ctx.author.id not in {587034072392532103}:
                return

            # Check if who is enabled
            if not self.who_enabled:
                await ctx.send("The 'who' command is currently disabled.")
                return

            if not self.games_in_progress:
                await ctx.send("No games in progress.")
                return

            lines = []
            for game in self.games_in_progress:
                match_id = game.get("MatchID", "?")
                players = game.get("Players", set())
                impostors = game.get("Impostors", set())
                if isinstance(impostors, (set, list, tuple)):
                    impostors_list = sorted(str(x) for x in impostors)
                else:
                    impostors_list = [str(impostors)] if impostors else []
                if isinstance(players, (set, list, tuple)):
                    players_list = sorted(str(x) for x in players)
                else:
                    players_list = [str(players)] if players else []
                lines.append(
                    f"MatchID: {match_id} | Impostors: {','.join(impostors_list) if impostors_list else 'Unknown'} | Players: {','.join(players_list) if players_list else 'Unknown'}"
                )

            await ctx.send("\n".join(lines))

        @self.command(name="toggle")
        async def toggle(ctx: Context):
            # Only respond in DMs
            if ctx.guild is not None:
                return

            # Only allow specific Discord user IDs
            if ctx.author.id not in {587034072392532103}:
                return

            self.who_enabled = not self.who_enabled
            await ctx.send(f"'who' command is now {'enabled' if self.who_enabled else 'disabled'}.")

        @self.hybrid_command(name="graph_mmr", description = "Graph MMR change of yourself or a player")
        @app_commands.describe(player = "Player name or @Player")
        async def graph_mmr(ctx:Context, player: Optional[str]):
            if ctx.channel.id != self.bot_commands and self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send(f"Please use https://discord.com/channels/{self.guild_id}/{self.bot_commands}",delete_after=5)
                await ctx.message.delete(delay=1)
                return
            member = None
            player_name = None 
            player_row = None

            if player is None:  # If no argument is provided
                member = ctx.author
                discord_id = ctx.author.id
                player_name = ctx.author.display_name
                player_row = self.leaderboard.get_player_by_discord(discord_id)
                
            elif player.startswith('<@'):  # If a mention is provided
                try:
                    mentioned_id = int(player[2:-1])
                    member = ctx.guild.get_member(mentioned_id)
                    player_name = member.display_name
                    player_row = self.leaderboard.get_player_by_discord(mentioned_id)
                    
                except Exception as e:
                    self.logger.error(e, mentioned_id)
                    await ctx.send(f"Invalid mention provided: {player}")
                    return
                
            else:  # If a display name is provided
                player_name = player
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                            await ctx.channel.send(f"Player {player_name} not found.")
                            return
                discord_id = self.leaderboard.get_player_discord(player_row)
                    
            if player_row is None:
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                        await ctx.channel.send(f"Player {player_name} not found.")
                        return
            player_name = player_row['Player Name']

            mmr_changes, crew_changes, imp_changes = self.file_handler.events_leaderboard.fetch_mmr_changes(player_name)

            impostor_mmr = config['impostor_current_mmr']
            crew_mmr = config['crewmate_current_mmr']
            total_mmr = config['current_mmr']
            impostor_mmrs = [impostor_mmr]
            crew_mmrs = [crew_mmr]
            total_mmrs = [total_mmr]
            for i in range(len(mmr_changes)):
                impostor_mmr += imp_changes[i]
                crew_mmr += crew_changes[i]
                total_mmr += mmr_changes[i]
                impostor_mmrs.append(impostor_mmr)
                crew_mmrs.append(crew_mmr)
                total_mmrs.append(total_mmr)
            plt.plot(impostor_mmrs, color='red', label='Impostor MMR')
            plt.plot(crew_mmrs, color='blue', label='Crew MMR')
            plt.plot(total_mmrs, color='purple', label='Total MMR')
            plt.xlabel(player_name)
            plt.ylabel('MMR')
            plt.title('MMR Changes Over Time')
            plt.legend()
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            await ctx.send(file=discord.File(buf, filename='mmr_changes.png'))
            plt.clf()
            self.logger.info(f"Sent MMR Graph for player {player_name} in channel {ctx.channel.name}")

        @self.hybrid_command(name="link", description="Link a player or yourself to the bot")
        @app_commands.describe(player="Player name in game")
        @app_commands.describe(discord="Discord mention @Player")
        async def link(ctx: Context, player: str, discord: Optional[discord.Member] = None):
            if not player:
                await ctx.send("Please provide a player name.")
                return

            player_row = self.leaderboard.get_player_row(player)
            player_discord = self.leaderboard.get_player_discord(player_row)

            if discord is None:
                discord_id = ctx.author.id
            else:
                discord_id = discord.id

            if player_discord:
                await ctx.send(f"{player} is already linked to <@{int(player_discord)}>.")
                return

            if player_row is None:
                await ctx.send(f"Player {player} not found in the database.")
                return

            if self.leaderboard.add_player_discord(player, discord_id):
                await ctx.send(f"Linked {player} to <@{discord_id}> in the leaderboard.")
            else:
                await ctx.send("Failed to link the player. Please try again later.")

        @self.hybrid_command(name="unlink", description="Unlink a player from the bot")
        @app_commands.describe(player="Player name in game or @mention")
        async def unlink(ctx: Context, player: str):
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.channel.send("You don't have permission to unlink players.")
                return

            if player.startswith('<@'):  # unlinking a mention
                discord_id = int(player[2:-1])
                player_row = self.leaderboard.get_player_by_discord(discord_id)
                if player_row is not None:
                    self.leaderboard.delete_player_discord(player_row['Player Name'])
                    await ctx.send(f"Unlinked {player_row['Player Name']} from <@{discord_id}>")
                else:
                    await ctx.send(f"{player} is not linked to any account")

            else:  # unlinking a player name
                player_row = self.leaderboard.get_player_row(player)
                if player_row is not None:
                    discord_id = self.leaderboard.get_player_discord(player_row)
                    if discord_id is not None:
                        self.leaderboard.delete_player_discord(player)
                        await ctx.send(f"Unlinked {player} from <@{discord_id}>")
                    else:
                        await ctx.send(f"Player {player} is not linked to any account")
                else:
                    await ctx.send(f"Player {player} not found in the database.")

        @self.hybrid_command(name="change_match", description="Change a match outcome")
        @app_commands.describe(match_id="Match ID")
        @app_commands.describe(result="Result (cancel/crew/imp)")
        @app_commands.describe(reason="Reason for changing a match result")
        async def change_match(ctx: Context, match_id: int, result: str, reason:Optional[str] = None):
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.")
                return

            if match_id is None:
                await ctx.send("Please specify a valid match ID.")
                return

            if result is None or result.lower() not in ['cancel', 'crew', 'imp']:
                await ctx.send("Please specify a valid result: 'cancel', 'crew', or 'imp'.")
                return

            match_info = self.file_handler.match_info_by_id(match_id)
            if match_info is None:
                await ctx.send(f"Cannot find match with ID: {match_id}")
                return

            changed_match, output = self.file_handler.change_match_result(match_id=match_id, new_result=result)

            if changed_match != False:
                mentions = ""
                player:PlayerInMatch
                for player in changed_match.players:
                    try:
                        member = self.guild.get_member(int(player.discord))
                        mentions += f"{member.mention} "
                    except:
                        self.logger.warning(f"Player {player.name} has a wrong discord ID {player.discord}")

                await ctx.send(f"Match {match_id} changed to {result}! {mentions} {reason}")
                await self.get_channel(self.cancels_channel).send(f"Member {ctx.author.display_name} {output}! {mentions} {reason}")
            else:
                await ctx.send(output)

        @self.hybrid_command(name="update_lb", description="Update any unprocessed matches")
        async def update_lb(ctx:Context):
            try:
                await ctx.defer(ephemeral=True)
                if self.staff_role not in [role.id for role in ctx.author.roles]:
                    await ctx.send("You don't have permission to use this command.", ephemeral=True)
                    return
                member = ctx.author
                match = self.file_handler.process_unprocessed_matches()
                if match:
                    await ctx.send(f"{member.mention} Updated the Leaderboard!", ephemeral=True)
                else:
                    await ctx.send(f"Leaderboard is up to date.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
                self.logger.error(f"Error in update_lb command: {str(e)}")

        @self.hybrid_command(name="m", description="Mute all players but yourself in a Voice Channel")
        async def m(ctx: Context):
            if not any(role.id in [self.moderator_role, self.staff_role] for role in ctx.author.roles):
                await ctx.send("You don't have permission to use this command.", ephemeral=True)
                return
            
            # Defer the response to avoid interaction timeout
            await ctx.defer(ephemeral=True)
            
            member = ctx.author
            voice_state = member.voice  # Get the voice state of the member
            
            if voice_state is None or voice_state.channel is None:
                await ctx.send("You need to be in a voice channel to use this command.", ephemeral=True)
                return
            
            channel = voice_state.channel
            tasks = []
            for vc_member in channel.members:
                if vc_member != member:
                    tasks.append(vc_member.edit(mute=True, deafen=False))
            
            try:
                await asyncio.gather(*tasks)
                await ctx.send(f"Muted all other members in {channel.name}.", ephemeral=True)
            except discord.Forbidden:
                await ctx.send("I don't have permission to mute members in this channel.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
                self.logger.error(f"Error in m command: {str(e)}")

        @self.hybrid_command(name="um", description="Unmute all players in a Voice Channel")
        async def um(ctx: Context):
            if not any(role.id in [self.moderator_role, self.staff_role] for role in ctx.author.roles):
                await ctx.send("You don't have permission to use this command.", ephemeral=True)
                return
            
            # Defer the response to avoid interaction timeout
            await ctx.defer(ephemeral=True)
            
            member = ctx.author
            voice_state = member.voice  # Get the voice state of the member
            
            if voice_state is None or voice_state.channel is None:
                await ctx.send("You need to be in a voice channel to use this command.", ephemeral=True)
                return
            
            channel = voice_state.channel
            tasks = []
            for vc_member in channel.members:
                tasks.append(vc_member.edit(mute=False, deafen=False))
            
            try:
                await asyncio.gather(*tasks)
                await ctx.send(f"Unmuted all members in {channel.name}.", ephemeral=True)
            except discord.Forbidden:
                await ctx.send("I don't have permission to unmute members in this channel.", ephemeral=True)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
                self.logger.error(f"Error in um command: {str(e)}")

        @self.hybrid_command(name="automute", description="Toggle automute from the server side")
        @app_commands.describe(toggle="On/Off")
        async def automute(ctx:Context, toggle : str):
            try:
                await ctx.defer(ephemeral=True)  # Defer immediately for hybrid commands

                if self.staff_role not in [role.id for role in ctx.author.roles]:
                    await ctx.send("You don't have permission to turn off automute.", ephemeral=True)
                    return
                
                if toggle.lower() == "on":
                    self.auto_mute = True
                    await ctx.send("Automute is turned ON from the server side!", ephemeral=True)
                    self.logger.info("Automute has been turned ON")
                    await self.get_channel(self.admin_logs_channel).send(f"{ctx.author.mention} turned Automute ON")

                elif toggle.lower() == "off":
                    self.auto_mute = False
                    await ctx.send("Automute is turned OFF from the server side!", ephemeral=True)
                    self.logger.info("Automute has been turned OFF")
                    await self.get_channel(self.admin_logs_channel).send(f"{ctx.author.mention} turned Automute OFF")

                else:
                    await ctx.send("Please use !automute On or !automute Off to toggle serve-side automute", ephemeral=True)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
                self.logger.error(f"Error in automute command: {str(e)}")

        @self.hybrid_command(name="rules", description="Displays the rules for calculating MMR in this bot")
        async def rules(ctx:Context):
            embed = discord.Embed(title="Among Us Game Info", color=discord.Color.blurple())
            embed.add_field(name="Impostors", value="""
        If the impostor is **ejected** on **8, 9, 10** __THEN__ they will **lose 15%** performance.
        The other impostor who is a **solo** impostor will **gain 15%** performance.
        If an impostor got a crewmate __voted out__ in a meeting they will **gain 10%** for every crewmate voted out.
        For every kill you do as a **solo** impostor, you will **gain 7%** performance.
        If you win as a solo Impostor, you will **gain 20%** performance.
        """, inline=False)
            embed.add_field(name="Crewmates", value="""
        If the crewmate voted wrong on **__crit__(3, 4) players alive** or **(5, 6, 7) players alive with 2 imps** __THEN__ they will **LOSE 30%** performance.
        If the crewmate votes out an impostor they will **gain 10%** performance.
        If the crewmate votes correct on crit but loses then they will **gain 20%** performance.
        """, inline=False)
            embed.add_field(name="Winning Percentage", value="The percentage of winning is calculated by a logaritmic regression machine learning module trained on pre-season data.",inline=False)
            embed.add_field(name="MMR Gained", value="Your MMR gain will be your team's winning percentage * your performance * K(32)",inline=False)
            embed.set_footer(text=f"Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent game info to Channel {ctx.channel}')

        @self.hybrid_command(name="mmr_change", description="Change MMR of a Player")
        @app_commands.describe(player="Player name or @player")
        @app_commands.describe(value="Value to add/subtract (-10/10)")
        @app_commands.describe(change_type="Crew/Imp/None")
        async def mmr_change(ctx: Context, player: str, value: float, change_type: Optional[str] = None, reason : str = None):
            try:
                await ctx.defer(ephemeral=False)
                
                if self.staff_role not in [role.id for role in ctx.author.roles]:
                    await ctx.send("You don't have permission to change a player's MMR.")
                    return

                if not player or value is None:
                    await ctx.send("Please provide a player name and the value argument.")
                    return

                change_type = change_type.lower() if change_type else None
                if change_type and not change_type.startswith(("crew", "imp")):
                    await ctx.send("Invalid change_type. It must start with 'crew', 'imp', or None.")
                    return
                
                if player.startswith('<@'):  # unlinking a mention
                    discord_id = int(player[2:-1])
                    player_row = self.leaderboard.get_player_by_discord(discord_id)
                else:
                    player_row = self.leaderboard.get_player_row(player)

                if player_row is None:
                    await ctx.send(f"Player {player} not found.")
                    return

                try:
                    mmr_change_value = float(value)
                except ValueError:
                    await ctx.send("Please input a correct MMR change value.")
                    return

                # Get player name for logging
                player_name = player_row['Player Name']
                
                # Determine change type for logging
                change_type_log = "total"
                if change_type and change_type.startswith("crew"):
                    change_type_log = "crew"
                elif change_type and change_type.startswith("imp"):
                    change_type_log = "imp"

                # Log the MMR change to CSV
                self.log_mmr_change(player_name, mmr_change_value, change_type_log, ctx.author.display_name, reason)

                mmr_change_text = ""
                if change_type and change_type.startswith("crew"):
                    self.file_handler.leaderboard.mmr_change_crew(player_row, mmr_change_value)
                    mmr_change_text = "Crew "
                elif change_type and change_type.startswith("imp"):
                    self.file_handler.leaderboard.mmr_change_imp(player_row, mmr_change_value)
                    mmr_change_text = "Impostor "
                else:
                    self.file_handler.leaderboard.mmr_change(player_row, mmr_change_value)

                if mmr_change_value > 0:
                    await ctx.send(f"Added {mmr_change_value} {mmr_change_text} MMR to Player {player_name}")
                    await self.get_channel(self.admin_logs_channel).send(f"{ctx.author.mention} Added {mmr_change_value} {mmr_change_text}MMR to Player {player_name} because {reason}")
                elif mmr_change_value < 0:
                    await ctx.send(f"Subtracted {-mmr_change_value} {mmr_change_text} MMR from Player {player_name}")
                    await self.get_channel(self.admin_logs_channel).send(f"{ctx.author.mention} Subtracted {mmr_change_value} {mmr_change_text}MMR to Player {player_name} because {reason}")
                    
            except Exception as e:
                self.logger.error(f"Error in mmr_change command: {str(e)}")
                await ctx.send(f"An error occurred while changing MMR: {str(e)}", ephemeral=True)

        @self.hybrid_command(name="name_change", description="Change the name of a player in all matches and leaderboard")
        @app_commands.describe(old_name="Player old name (this name is case sensitive)")
        @app_commands.describe(new_name="Player new name")
        async def name_change(ctx: Context, old_name : str, new_name : str):
            try:
                await ctx.defer(ephemeral=False)
                
                if not any(role.id == self.owner_role for role in ctx.author.roles):
                    await ctx.send("You don't have permission to change a player's name.")
                    return
                    
                found_old_player = self.leaderboard.get_player_row(old_name)
                if found_old_player is not None and not found_old_player.empty:
                    self.file_handler.change_player_name(old_name, new_name)
                    await ctx.send(f'Changed player name from {old_name} to {new_name}')
                    await self.get_channel(self.admin_logs_channel).send(f'{ctx.author.mention} Changed player name from {old_name} to {new_name}')
                else:
                    await ctx.send(f"I can not find player {old_name}, please make sure the player is in the leaderboard")
                    
            except Exception as e:
                self.logger.error(f"Error in name_change command: {str(e)}")
                await ctx.send(f"An error occurred while changing player name: {str(e)}", ephemeral=True)

        @self.hybrid_command(name="rank_block", description="Rank block a player for a duration of time")
        @app_commands.describe(player="@Player")
        @app_commands.describe(duration="Duration [30m/12h/5d..]")
        @app_commands.describe(reason="Reason for the rankblock")
        async def rank_block(ctx: Context, player: discord.Member, duration: str, reason: str):
            # Check if the user has the staff role
            if not any(role.id == int(self.staff_role) for role in ctx.author.roles):
                await ctx.send("You don't have permission to rankblock a player.")
                return
            def calculate_unblock_time(duration_str):
                num = int(''.join(filter(str.isdigit, duration_str)))
                if 'm' in duration_str:
                    return datetime.now() + timedelta(minutes=num)
                elif 'h' in duration_str:
                    return datetime.now() + timedelta(hours=num)
                elif 'd' in duration_str:
                    return datetime.now() + timedelta(days=num)
                else:
                    return None

            now = datetime.now()
            unblock_time = calculate_unblock_time(duration)
            if not unblock_time:
                await ctx.send("Invalid duration format.")
                return
            data = {'Player ID': [player.id],
                    'Player Name': [player.name],
                    'Blocked At': [now.strftime("%Y-%m-%d %H:%M:%S")],
                    'Unblock Time': [unblock_time.strftime("%Y-%m-%d %H:%M:%S")],
                    'Reason': [reason]}
            df = pd.DataFrame(data)
            df.to_csv('rank_blocks.csv', mode='a', index=False, header=not os.path.exists('rank_blocks.csv'))

            blocked_role = ctx.guild.get_role(self.blocked_role_id)
            access_role = ctx.guild.get_role(self.ranked_access_role_id)
            await player.add_roles(blocked_role, reason=reason)
            await player.remove_roles(access_role, reason=reason)
            await ctx.send(f"Staff member {ctx.author.mention} Rankblocked player {player.display_name} for {duration}{' because ' + reason if reason else ''}")

        @self.hybrid_command(name="unblock", help="Unblock a player manually")
        @app_commands.describe(player="@Player")
        @app_commands.describe(reason="Reason for the unblock")
        async def unblock(ctx: Context, player: discord.Member, reason: str):
            if not any(role.id == int(self.staff_role) for role in ctx.author.roles):
                await ctx.channel.send("You don't have permission to unblock a player.")
                return

            blocked_role = ctx.guild.get_role(self.blocked_role_id)
            access_role = ctx.guild.get_role(self.ranked_access_role_id)
            await player.remove_roles(blocked_role, reason=reason)
            await player.add_roles(access_role, reason=reason)

            if os.path.exists('rank_blocks.csv'):
                df = pd.read_csv('rank_blocks.csv')
                df = df[df['Player ID'] != player.id]
                df.to_csv('rank_blocks.csv', index=False)
                await ctx.send(f"{player.mention} has been unblocked{' because ' + reason if reason else ''}")

            else:    
                await ctx.send(f"No one is ranked blocked, failed to unblock {player.display_name}")

        @self.hybrid_command(name="replay_match", description="Display match details of all the players in match")
        @app_commands.describe(match_id="Match ID")
        async def replay_match(ctx:Context, match_id : int):
            if not any(role.id == int(self.staff_role) for role in ctx.author.roles):
                await ctx.send("You don't have permission to redisplay an embed.")
                return
            if match_id == None: 
                return
            match_file = self.file_handler.find_matchfile_by_id(int(match_id))
            match = self.file_handler.match_from_file(match_file)
            end_embed = self.end_game_embed(match)
            events_embed = self.events_embed(match)
            view = VotesView(embed=events_embed)
            await ctx.send(embed=end_embed, view=view)
            await ctx.send(f"`{match.match_details()}`")
            self.logger.info(f"{ctx.author.display_name} Recieved Match {int(match_id)} Info")

        @self.hybrid_command(name="check_balance", description="Check your VIP game balance")
        async def check_balance(ctx: Context):
            # Check if user has VIP role
            member_roles = [role.id for role in ctx.author.roles]
            is_vip = any(any(role_id in member_roles for role_id in role_info['ids']) 
                        for role_info in self.config['vip_roles'].values())
            
            if not is_vip:
                await ctx.send("This command is only available for VIP members.", ephemeral=True)
                return
                
            try:
                # Get member info
                vip_member = self.premium.get_member_by_discord_id(str(ctx.author.id))
                if not vip_member:
                    await ctx.send("Your VIP membership was not found. Please contact staff.", ephemeral=True)
                    return

                # Parse dates with explicit format
                subscription_end = datetime.strptime(vip_member['subscription_end'], '%d/%m/%Y %H:%M:%S')
                next_refresh = datetime.strptime(vip_member['next_refresh'], '%d/%m/%Y %H:%M:%S')
                
                # Debug logging
                self.logger.info(f"Raw subscription end: {vip_member['subscription_end']}")
                self.logger.info(f"Parsed subscription end: {subscription_end}")
                self.logger.info(f"Current time: {datetime.now()}")

                # Create embed
                embed = discord.Embed(
                    title=f"VIP Balance for {ctx.author.display_name}",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Weekly Balance", 
                    value=f"**{vip_member['balances']['weekly']}** games\nRefreshes <t:{int(next_refresh.timestamp())}:R>",
                    inline=False
                )
                
                embed.add_field(
                    name="Purchased Balance",
                    value=f"Double MMR: **{vip_member['balances']['purchased_double']}** games\nTriple MMR: **{vip_member['balances']['purchased_triple']}** games",
                    inline=False
                )
                
                embed.add_field(
                    name="Subscription",
                    value=f"Expires <t:{int(subscription_end.timestamp())}:R>",
                    inline=False
                )
                
                embed.set_footer(text=f"VIP Role: {vip_member['role']}")
                
                await ctx.send(embed=embed, ephemeral=True)

            except Exception as e:
                self.logger.error(f"Error in check_balance: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="start_multiplier_lobby", 
            description="Use your VIP balance for double/triple/quad MMR games"
        )
        @app_commands.describe(
            games="Number of games to play with multiplier",
            multiplier="Choose double, triple or quad MMR",
            voice_channel="Voice channel to use the multiplier in"
        )
        @app_commands.choices(
            multiplier=[
                app_commands.Choice(name="Double MMR (2x)", value="double"),
                app_commands.Choice(name="Triple MMR (3x)", value="triple")
            ]
        )
        async def start_multiplier_lobby(
            ctx: Context, 
            games: int, 
            multiplier: str,
            voice_channel: str
        ):
            """Run multiplier MMR games in a specific voice channel"""
            # Parse selected channel id from autocomplete
            try:
                channel_id = int(voice_channel)
                voice_channel = self.get_channel(channel_id)
                if not isinstance(voice_channel, discord.VoiceChannel):
                    await ctx.send("Invalid voice channel selected.", ephemeral=True)
                    return
            except (ValueError, TypeError):
                await ctx.send("Invalid voice channel selected.", ephemeral=True)
                return

            # Check if channel is in config
            if voice_channel.id not in [ch['voice_channel_id'] for ch in self.channels.values()]:
                await ctx.send("Please select a valid ranked voice channel.", ephemeral=True)
                return

            # Check if user has VIP role
            member_roles = [role.id for role in ctx.author.roles]
            is_vip = any(any(role_id in member_roles for role_id in role_info['ids']) 
                        for role_info in self.config['vip_roles'].values())
            
            if not is_vip:
                await ctx.send("This command is only available for VIP members.", ephemeral=True)
                return

            # Validate channel is a ranked channel
            channel_id = voice_channel.id
            if not any(ch['voice_channel_id'] == channel_id for ch in self.channels.values()):
                await ctx.send("Please select a valid ranked voice channel.", ephemeral=True)
                return

            # Check if channel already has active multiplier
            if self.premium.is_channel_using_special_games(channel_id):
                await ctx.send("This channel already has an active MMR multiplier.", ephemeral=True)
                return

            # Get member info
            member = self.premium.get_member_by_discord_id(str(ctx.author.id))
            if not member:
                await ctx.send("Your VIP membership was not found. Please contact staff.", ephemeral=True)
                return

            # Try to use balance
            success, message = self.premium.use_balance(
                member_id=member['member_id'],
                games=games,
                channel_id=channel_id,
                balance_type=multiplier
            )

            if not success:
                await ctx.send(f"Error: {message}", ephemeral=True)
                return

            # Create success embed
            embed = discord.Embed(
                title="MMR Multiplier Activated",
                description=f"Successfully activated {multiplier} MMR for {games} games",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Channel", 
                value=voice_channel.mention,
                inline=True
            )
            
            embed.add_field(
                name="Games", 
                value=str(games),
                inline=True
            )
            
            embed.add_field(
                name="Multiplier", 
                value=multiplier.title(),
                inline=True
            )
            
            embed.set_footer(text=f"Activated by {ctx.author.display_name}")
            
            # Send to user and log channel
            await ctx.send(embed=embed, ephemeral=True)
            log_channel = self.get_channel(self.admin_logs_channel)
            if log_channel:
                await log_channel.send(
                    f"{ctx.author.mention} activated {multiplier} MMR for {games} games in {voice_channel.mention}"
                )
        
            # In the run_multiplier_mmr command, after successful balance use:
            if success:
                # Get the text channel associated with the voice channel
                text_channel = None
                for ch in self.channels.values():
                    if ch['voice_channel_id'] == channel_id:
                        text_channel = self.get_channel(ch['text_channel_id'])
                        break

                if text_channel:
                    # Create session start embed
                    start_embed = discord.Embed(
                        title="Special MMR Session Started",
                        description=f"{ctx.author.mention} has activated {multiplier} MMR for {games} games",
                        color=discord.Color.green()
                    )
                    
                    start_embed.add_field(
                        name="Games",
                        value=str(games),
                        inline=True
                    )
                    
                    start_embed.add_field(
                        name="Type",
                        value=f"{multiplier.title()} MMR",
                        inline=True
                    )
                    
                    start_embed.add_field(
                        name="Host",
                        value=ctx.author.mention,
                        inline=True
                    )
                    
                    await text_channel.send(embed=start_embed)

        @start_multiplier_lobby.autocomplete('voice_channel')
        async def voice_channel_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            choices: list[app_commands.Choice[str]] = []
            for channel_name, channel_data in self.channels.items():
                # Only suggest ranked voice channels
                if not channel_name.startswith('ranked'):
                    continue
                channel = self.get_channel(channel_data['voice_channel_id'])
                if isinstance(channel, discord.VoiceChannel):
                    display_name = f"{channel.name}"
                    choices.append(app_commands.Choice(
                        name=display_name,
                        value=str(channel.id)
                    ))
            if current:
                ci = current.lower()
                choices = [c for c in choices if ci in c.name.lower()]
            return choices[:25]

        @self.hybrid_command(
            name="add_vip",
            description="Add a new VIP member (Staff Only)"
        )
        @app_commands.describe(
            member="The member to add as VIP (mention)",
            role="VIP role level",
            start_date="Start date (DD/MM/YYYY) - Optional, defaults to today",
            start_time="Start time (HH:MM) - Optional, defaults to current time",
            subscription_days="Number of days for subscription"
        )
        @app_commands.choices(
            role=[
                app_commands.Choice(name="VIP", value="VIP"),
                app_commands.Choice(name="VIP++", value="VIP++"),
                app_commands.Choice(name="VIP Elite", value="VIPElite")
            ]
        )
        async def add_vip(
            ctx: Context,
            member: discord.Member,
            role: str,
            start_date: Optional[str] = None,
            start_time: Optional[str] = None,
            subscription_days: int = 28
        ):
            # Check if user has staff role
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to add VIP members.", ephemeral=True)
                return

            try:
                # Use current date/time if not provided
                if start_date is None or start_time is None:
                    subscription_date = datetime.now()
                    self.logger.info(f"Using current time for VIP subscription: {subscription_date}")
                else:
                    # Parse provided date and time
                    day, month, year = map(int, start_date.split('/'))
                    hour, minute = map(int, start_time.split(':'))
                    subscription_date = datetime(year, month, day, hour=hour, minute=minute)
                
                # Add member
                success, result = self.premium.add_member(
                    discord_name=member.name,
                    discord_id=str(member.id),
                    server_nickname=member.display_name,
                    role=role,
                    subscription_days=subscription_days,
                    subscription_date=subscription_date
                )

                if not success:
                    await ctx.send(f"Error adding VIP member: {result}", ephemeral=True)
                    return

                # Create success embed
                embed = discord.Embed(
                    title="VIP Member Added",
                    description=f"Successfully added {member.mention} as {role}",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Subscription Start",
                    value=subscription_date.strftime("%d/%m/%Y %H:%M"),
                    inline=True
                )
                
                embed.add_field(
                    name="Duration",
                    value=f"{subscription_days} days",
                    inline=True
                )
                
                embed.add_field(
                    name="Subscription End",
                    value=(subscription_date + timedelta(days=subscription_days)).strftime("%d/%m/%Y %H:%M"),
                    inline=True
                )
                
                embed.set_footer(text=f"Added by {ctx.author.display_name}")
                
                # Send confirmation messages
                await ctx.send(embed=embed)
                log_channel = self.get_channel(self.admin_logs_channel)
                if log_channel:
                    await log_channel.send(
                        f"{ctx.author.mention} added {member.mention} as {role} member"
                    )

            except ValueError as e:
                if start_date is not None or start_time is not None:
                    await ctx.send(
                        "Invalid date/time format. Please use DD/MM/YYYY for date and HH:MM for time.", 
                        ephemeral=True
                    )
                else:
                    await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
            except Exception as e:
                self.logger.error(f"Error in add_vip: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="add_balance",
            description="Add balance to a VIP member's account (Staff Only)"
        )
        @app_commands.describe(
            member="The VIP member to add balance to (mention)",
            games="Number of games to add",
            balance_type="Type of MMR multiplier"
        )
        @app_commands.choices(
            balance_type=[
                app_commands.Choice(name="Double MMR (2x)", value="double"),
                app_commands.Choice(name="Triple MMR (3x)", value="triple")
            ]
        )
        async def add_balance(
            ctx: Context,
            member: discord.Member,
            games: int,
            balance_type: str
        ):
            # Check if user has staff role
            if self.owner_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to add balance.", ephemeral=True)
                return

            # Check if target member is VIP
            member_roles = [role.id for role in member.roles]
            is_vip = any(any(role_id in member_roles for role_id in role_info['ids']) 
                        for role_info in self.config['vip_roles'].values())
            
            if not is_vip:
                await ctx.send("Target member must be a VIP member.", ephemeral=True)
                return

            # Get member info
            vip_member = self.premium.get_member_by_discord_id(str(member.id))
            if not vip_member:
                await ctx.send("VIP member not found in the system.", ephemeral=True)
                return

            try:
                # Generate a transaction ID
                transaction_id = f"staff_{ctx.author.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                # Add the balance
                success, result = self.premium.members[vip_member['member_id']].add_purchased_games(
                    amount=games,
                    transaction_id=transaction_id,
                    balance_type=balance_type
                )

                if not success:
                    await ctx.send(f"Error adding balance: {result}", ephemeral=True)
                    return

                # Create success embed
                embed = discord.Embed(
                    title="Balance Added",
                    description=f"Successfully added balance to {member.mention}",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Games Added",
                    value=str(games),
                    inline=True
                )
                
                embed.add_field(
                    name="Type",
                    value=f"{balance_type.title()} MMR",
                    inline=True
                )
                
                embed.add_field(
                    name="Transaction ID",
                    value=transaction_id,
                    inline=False
                )
                
                embed.set_footer(text=f"Added by {ctx.author.display_name}")
                
                # Send confirmation messages
                await ctx.send(embed=embed)
                log_channel = self.get_channel(self.admin_logs_channel)
                if log_channel:
                    await log_channel.send(
                        f"{ctx.author.mention} added {games} {balance_type} MMR games to {member.mention}'s balance"
                    )

            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="remove_balance",
            description="Remove balance from a VIP member's account (Staff Only)"
        )
        @app_commands.describe(
            member="The VIP member to remove balance from (mention)",
            games="Number of games to remove",
            balance_type="Type of MMR multiplier"
        )
        @app_commands.choices(
            balance_type=[
                app_commands.Choice(name="Double MMR (2x)", value="double"),
                app_commands.Choice(name="Triple MMR (3x)", value="triple")
            ]
        )
        async def remove_balance(
            ctx: Context,
            member: discord.Member,
            games: int,
            balance_type: str
        ):
            # Check if user has staff role
            if self.owner_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to remove balance.", ephemeral=True)
                return

            # Get member info
            vip_member = self.premium.get_member_by_discord_id(str(member.id))
            if not vip_member:
                await ctx.send("VIP member not found in the system.", ephemeral=True)
                return

            try:
                # Generate a transaction ID
                transaction_id = f"staff_remove_{ctx.author.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                # Remove the balance (negative amount for removal)
                success, result = self.premium.members[vip_member['member_id']].add_purchased_games(
                    amount=-games,
                    transaction_id=transaction_id,
                    balance_type=balance_type
                )

                if not success:
                    await ctx.send(f"Error removing balance: {result}", ephemeral=True)
                    return

                # Create success embed
                embed = discord.Embed(
                    title="Balance Removed",
                    description=f"Successfully removed balance from {member.mention}",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="Games Removed",
                    value=str(games),
                    inline=True
                )
                
                embed.add_field(
                    name="Type",
                    value=f"{balance_type.title()} MMR",
                    inline=True
                )
                
                embed.add_field(
                    name="Transaction ID",
                    value=transaction_id,
                    inline=False
                )
                
                embed.set_footer(text=f"Removed by {ctx.author.display_name}")
                
                # Send confirmation messages
                await ctx.send(embed=embed)
                log_channel = self.get_channel(self.admin_logs_channel)
                if log_channel:
                    await log_channel.send(
                        f"{ctx.author.mention} removed {games} {balance_type} MMR games from {member.mention}'s balance"
                    )

            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="check_member_balance",
            description="Check a VIP member's balance (Staff Only)"
        )
        @app_commands.describe(
            member="The VIP member to check balance for (mention)"
        )
        async def check_member_balance(
            ctx: Context,
            member: discord.Member
        ):
            # Check if user has staff role
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to check other members' balance.", ephemeral=True)
                return

            # Get member info
            vip_member = self.premium.get_member_by_discord_id(str(member.id))
            if not vip_member:
                await ctx.send("VIP member not found in the system.", ephemeral=True)
                return

            try:
                # Get balance info
                member_obj = self.premium.members[vip_member['member_id']]
                with open(member_obj.balance_file, 'r') as f:
                    data = json.load(f)
                    
                weekly_balance = data['weekly_balance']
                double_balance = data['purchased_balances']['double']
                triple_balance = data['purchased_balances']['triple']
                
                # Parse dates with correct format
                next_refresh = datetime.strptime(data['next_refresh'], '%d/%m/%Y %H:%M:%S')
                subscription_end = datetime.strptime(data['subscription_end'], '%d/%m/%Y %H:%M:%S')
                
                # Debug logging
                self.logger.info(f"Raw next refresh: {data['next_refresh']}")
                self.logger.info(f"Raw subscription end: {data['subscription_end']}")
                self.logger.info(f"Parsed next refresh: {next_refresh}")
                self.logger.info(f"Parsed subscription end: {subscription_end}")
                
                # Create embed
                embed = discord.Embed(
                    title=f"VIP Balance for {member.display_name}",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Weekly Balance", 
                    value=f"**{weekly_balance}** games\nRefreshes <t:{int(next_refresh.timestamp())}:R>",
                    inline=False
                )
                
                embed.add_field(
                    name="Purchased Balance",
                    value=f"Double MMR: **{double_balance}** games\nTriple MMR: **{triple_balance}** games",
                    inline=False
                )
                
                embed.add_field(
                    name="Subscription",
                    value=f"Expires <t:{int(subscription_end.timestamp())}:R>",
                    inline=False
                )
                
                embed.set_footer(text=f"VIP Role: {member_obj.role} | Checked by {ctx.author.display_name}")
                
                await ctx.send(embed=embed, ephemeral=True)

            except Exception as e:
                self.logger.error(f"Error in check_member_balance: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="list_vip_members",
            description="List all VIP members and their details (Staff Only)"
        )
        async def list_vip_members(ctx: Context):
            # Check if user has staff role
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to view VIP members list.", ephemeral=True)
                return

            try:
                # Create main embed
                embed = discord.Embed(
                    title="VIP Members List",
                    description="Current active VIP members and their details",
                    color=discord.Color.blue()
                )

                # Sort members by subscription end date
                sorted_members = sorted(
                    self.premium.members.values(),
                    key=lambda x: x.subscription_end
                )

                for member in sorted_members:
                    # Get balance info
                    with open(member.balance_file, 'r') as f:
                        data = json.load(f)
                    
                    # Format member details
                    member_details = (
                        f"**Balance:**\n"
                        f"• Weekly: {data['weekly_balance']} games\n"
                        f"• Double MMR: {data['purchased_balances']['double']} games\n"
                        f"• Triple MMR: {data['purchased_balances']['triple']} games\n"
                        f"**Subscription:**\n"
                        f"• Ends: <t:{int(member.subscription_end.timestamp())}:R>\n"
                        f"• Role: {member.role}"
                    )

                    # Add field for this member
                    embed.add_field(
                        name=f"{member.discord_name} ({member.server_nickname})",
                        value=member_details,
                        inline=False
                    )

                # Add summary footer
                embed.set_footer(text=f"Total VIP Members: {len(sorted_members)} | Generated by {ctx.author.display_name}")

                # Send embed
                await ctx.send(embed=embed, ephemeral=True)

            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
        
        @self.hybrid_command(
            name="upgrade_vip",
            description="Upgrade a VIP member's role (Staff Only)"
        )
        @app_commands.describe(
            member="The VIP member to upgrade (mention)",
            new_role="New VIP role level"
        )
        @app_commands.choices(
            new_role=[
                app_commands.Choice(name="VIP++", value="VIP++"),
                app_commands.Choice(name="VIP Elite", value="VIPElite")
            ]
        )
        async def upgrade_vip(
            ctx: Context,
            member: discord.Member,
            new_role: str
        ):
            # Check if user has staff role
            if self.owner_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to upgrade VIP members.", ephemeral=True)
                return

            # Get member info
            vip_member = self.premium.get_member_by_discord_id(str(member.id))
            if not vip_member:
                await ctx.send("VIP member not found in the system.", ephemeral=True)
                return

            try:
                success, message = self.premium.upgrade_membership(vip_member['member_id'], new_role)
                if not success:
                    await ctx.send(f"Error upgrading membership: {message}", ephemeral=True)
                    return

                # Create success embed
                embed = discord.Embed(
                    title="VIP Membership Upgraded",
                    description=message,
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Member",
                    value=member.mention,
                    inline=True
                )
                
                embed.add_field(
                    name="New Role",
                    value=new_role,
                    inline=True
                )
                
                embed.set_footer(text=f"Upgraded by {ctx.author.display_name}")
                
                # Send confirmation messages
                await ctx.send(embed=embed)
                log_channel = self.get_channel(self.admin_logs_channel)
                if log_channel:
                    await log_channel.send(
                        f"{ctx.author.mention} upgraded {member.mention} to {new_role}"
                    )

            except Exception as e:
                self.logger.error(f"Error in upgrade_vip: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="renew_vip",
            description="Renew a VIP member's subscription (Staff Only)"
        )
        @app_commands.describe(
            member="The VIP member to renew (mention)",
            days="Number of days to add to subscription"
        )
        async def renew_vip(
            ctx: Context,
            member: discord.Member,
            days: int = 28
        ):
            # Check if user has staff role
            if self.owner_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to renew VIP memberships.", ephemeral=True)
                return

            # Get member info
            vip_member = self.premium.get_member_by_discord_id(str(member.id))
            if not vip_member:
                await ctx.send("VIP member not found in the system.", ephemeral=True)
                return

            try:
                success, message = self.premium.renew_membership(vip_member['member_id'], days)
                if not success:
                    await ctx.send(f"Error renewing membership: {message}", ephemeral=True)
                    return

                # Create success embed
                embed = discord.Embed(
                    title="VIP Membership Renewed",
                    description=f"Successfully renewed membership for {days} days",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Member",
                    value=member.mention,
                    inline=True
                )
                
                embed.add_field(
                    name="Days Added",
                    value=str(days),
                    inline=True
                )
                
                embed.add_field(
                    name="New End Date",
                    value=message,
                    inline=True
                )
                
                embed.set_footer(text=f"Renewed by {ctx.author.display_name}")
                
                # Send confirmation messages
                await ctx.send(embed=embed)
                log_channel = self.get_channel(self.admin_logs_channel)
                if log_channel:
                    await log_channel.send(
                        f"{ctx.author.mention} renewed {member.mention}'s VIP membership for {days} days"
                    )

            except Exception as e:
                self.logger.error(f"Error in renew_vip: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(
            name="active_mmr_games",
            description="Show all active special MMR games"
        )
        async def active_mmr_games(ctx: Context):
            # Check if user has VIP role or staff role
            member_roles = [role.id for role in ctx.author.roles]
            is_vip = any(any(role_id in member_roles for role_id in role_info['ids']) 
                        for role_info in self.config['vip_roles'].values())
            is_staff = self.staff_role in member_roles

            if not (is_vip or is_staff):
                await ctx.send("This command is only available for VIP members and staff.", ephemeral=True)
                return

            try:
                active_games = self.premium.get_active_special_games()
                
                if not active_games:
                    await ctx.send("No active special MMR games at the moment.", ephemeral=True)
                    return

                # Create embed
                embed = discord.Embed(
                    title="Active Special MMR Games",
                    description="Currently running special MMR multipliers",
                    color=discord.Color.blue()
                )

                for channel_id, game_info in active_games.items():
                    channel = self.get_channel(channel_id)
                    if channel:
                        embed.add_field(
                            name=channel.name,
                            value=(
                                f"**Player:** {game_info['member_name']}\n"
                                f"**Type:** {game_info['balance_type'].title()} MMR\n"
                                f"**Games Left:** {game_info['games_remaining']}"
                            ),
                            inline=False
                        )

                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                
                await ctx.send(embed=embed, ephemeral=True)

            except Exception as e:
                self.logger.error(f"Error in active_mmr_games: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)
        
        @self.hybrid_command(
            name="push_special_game", 
            description="Force push a special game to the bot (Staff Only)"
        )
        @app_commands.describe(
            match_id="Match ID",
            voice_channel="Voice Channel where the game was played",
            result="Game result",
            impostors="Comma-separated impostor names (e.g., 'player1, player2')"
        )
        @app_commands.choices(
            result=[
                app_commands.Choice(name="Crewmates Win", value="Crewmates Win"),
                app_commands.Choice(name="Impostors Win", value="Impostors Win"),
                app_commands.Choice(name="Game Cancelled", value="Cancelled")
            ]
        )
        async def push_special_game(
            ctx: Context, 
            match_id: str,
            voice_channel: discord.VoiceChannel,
            result: str,
            impostors: str
        ):
            # Check if user has staff role
            if self.staff_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.", ephemeral=True)
                return

            try:
                channel_id = voice_channel.id
                
                # Check if channel has active special games
                if not self.premium.is_channel_using_special_games(channel_id):
                    await ctx.send("This channel doesn't have any active special MMR games.", ephemeral=True)
                    return

                # Get active game info
                active_games = self.premium.get_active_special_games()
                game_info = active_games[channel_id]
                
                # Create a test match object
                test_match = Match(
                    id=int(match_id),
                    match_start_time=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    result=result,
                    event_file_name=f"{match_id}_events.json",
                    players=[],  # Empty players list for test
                    k=64 if game_info['balance_type'] == 'double' else 96
                )
                
                # Log the special match
                success, completed, msg = self.premium.log_special_match(
                    channel_id=channel_id,
                    match_id=int(match_id),
                    time_of_match=datetime.now()
                )

                if success:
                    # Create game completion embed
                    embed = discord.Embed(
                        title="Special MMR Game Completed (Test)",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(
                        name="Match ID",
                        value=match_id,
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Type",
                        value=f"{game_info['balance_type'].title()} MMR",
                        inline=True
                    )
                    
                    games_left = game_info['games_remaining'] - 1
                    embed.add_field(
                        name="Games Remaining",
                        value=str(games_left),
                        inline=True
                    )

                    # Send messages to text channel
                    text_channel = None
                    for channel in self.channels.values():
                        if channel['voice_channel_id'] == channel_id:
                            text_channel = self.get_channel(channel['text_channel_id'])
                            break

                    if text_channel:
                        await text_channel.send(embed=embed)
                        
                        if completed:
                            complete_embed = discord.Embed(
                                title="Special MMR Session Ended",
                                description=f"All {game_info['balance_type']} MMR games have been completed.",
                                color=discord.Color.red()
                            )
                            await text_channel.send(embed=complete_embed)

                    # Send confirmation to command user
                    await ctx.send(f"Successfully processed test match {match_id}", ephemeral=True)
                    self.logger.info(f"VIP Test Match {match_id} pushed successfully")

                else:
                    await ctx.send(f"Failed to log special match: {msg}", ephemeral=True)
                    self.logger.error(f"Failed to push VIP Match {match_id}: {msg}")

            except Exception as e:
                self.logger.error(f"Error in push_special_game: {str(e)}")
                await ctx.send(f"An error occurred: {str(e)}", ephemeral=True)

        @self.hybrid_command(name="help", description="Display help for using the bot")
        async def help(ctx:Context):
            embed = discord.Embed(title="Among Us Bot Commands", color=discord.Color.gold())
            embed.add_field(name="**stats** [none/player/@mention]", value="Display stats of a player.", inline=False)
            embed.add_field(name="**lb** [none/number]", value="Display the leaderboard for top Players.", inline=False)
            embed.add_field(name="**lb imp** [none/number]", value="Display the leaderboard for top Impostors.", inline=False)
            embed.add_field(name="**lb crew** [none/number]", value="Display the leaderboardfor top Crewmates.", inline=False)
            embed.add_field(name="**graph_mmr** [none/player/@mention]", value="Display MMR Graph of a player.", inline=False)
            embed.add_field(name="**match_info** [match_id]", value="Display match info from the given ID", inline=False)
            embed.add_field(name="**rules**", value="Explains how the bot calculates MMR", inline=False)
            embed.add_field(name="**mmr_change** [player/@mention] [value] [Crew/Imp/None]", value="add or subtract mmr from the player", inline=False)
            embed.add_field(name="**name_change** [old_name]**__,__** [new_name]", value="change a player name(COMMA SEPERATOR , )", inline=False)
            embed.add_field(name="**automute** [on/off]", value="Turn on/off server-side automute.", inline=False)
            embed.add_field(name="**link** [player] [none/@mention]", value="Link a Discord user to a player name.", inline=False)
            embed.add_field(name="**unlink** [player/@mention]", value="Unlink a Discord user from a player name.", inline=False)
            embed.add_field(name="**change_match** [match_id] [cancel/crew/imp]", value="Change match result.", inline=False)
            embed.add_field(name="**m**", value="Mute everyone in your VC.", inline=False)
            embed.add_field(name="**um**", value="Unmute everyone in your VC.", inline=False)
            embed.set_footer(text=f"Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent help command to Channel {ctx.channel}')

        # @self.hybrid_command(name="restart", description="Restart a module (Impostor Server or Discord Bot)")
        # @app_commands.describe(module="Select which module to restart")
        # @app_commands.choices(module=[
        #     app_commands.Choice(name="Impostor Server", value="impostor"),
        #     app_commands.Choice(name="Discord Bot", value="bot")
        # ])
        # async def restart(ctx: Context, module: app_commands.Choice[str]):
        #     # Check if user has staff role
        #     if self.staff_role not in [role.id for role in ctx.author.roles]:
        #         await ctx.send("You don't have permission to restart modules.", ephemeral=True)
        #         return

        #     # Defer the response to avoid interaction timeout
        #     await ctx.defer(ephemeral=True)

        #     # Get the module value from the choice
        #     module_value = module.value
        #     module_name = module.name

        #     # Determine which module to restart
        #     if module_value == "impostor":
        #         command = "sudo systemctl restart impostor.service"
        #     else:  # module_value == "bot"
        #         command = "sudo systemctl restart discordbot.service"

        #     try:
        #         # Log the restart attempt
        #         self.logger.info(f"{ctx.author.display_name} is attempting to restart {module_name}")
                
        #         # Notify admin logs
        #         admin_channel = self.get_channel(self.admin_logs_channel)
        #         if admin_channel:
        #             await admin_channel.send(f"🔄 {ctx.author.mention} is restarting {module_name}")

        #         # Execute the restart command
        #         process = await asyncio.create_subprocess_shell(
        #             command,
        #             stdout=asyncio.subprocess.PIPE,
        #             stderr=asyncio.subprocess.PIPE
        #         )
        #         stdout, stderr = await process.communicate()

        #         if process.returncode == 0:
        #             success_msg = f"✅ Successfully restarted {module_name}."
        #             await ctx.send(success_msg, ephemeral=True)
        #             if admin_channel:
        #                 await admin_channel.send(success_msg)
        #             self.logger.info(f"{ctx.author.display_name} successfully restarted {module_name}")
        #         else:
        #             error_message = stderr.decode().strip()
        #             error_msg = f"❌ Failed to restart {module_name}: {error_message}"
        #             await ctx.send(error_msg, ephemeral=True)
        #             if admin_channel:
        #                 await admin_channel.send(error_msg)
        #             self.logger.error(f"Failed to restart {module_name}: {error_message}")

        #     except Exception as e:
        #         error_msg = f"❌ An error occurred while restarting {module_name}: {str(e)}"
        #         await ctx.send(error_msg, ephemeral=True)
        #         if admin_channel:
        #             await admin_channel.send(error_msg)
        #         self.logger.error(f"Error in restart command: {str(e)}")

        @self.hybrid_command(name="season_stats", description="Show season-wide stats, optionally for a time frame (e.g., 7d, 30d, all)")
        @app_commands.describe(timeframe="Time frame to look back (e.g., 7d for last 7 days, 30d for last 30 days, all for everything)")
        async def season_stats(ctx: Context, timeframe: Optional[str] = None):
            import pandas as pd
            from datetime import datetime, timedelta
            import os

            # --- Load Data ---
            events_path = self.file_handler.events_leaderboard.csv_file
            leaderboard_path = self.file_handler.leaderboard.csv_file
            if not os.path.exists(events_path):
                await ctx.send("No events file found.")
                return
            if not os.path.exists(leaderboard_path):
                await ctx.send("No leaderboard file found.")
                return
            df = pd.read_csv(events_path)
            lb = pd.read_csv(leaderboard_path)

            # --- Timeframe Filtering ---
            now = datetime.now()
            if timeframe is None or timeframe.lower() == 'all':
                filtered_df = df.copy()
                timeframe_str = "All Time"
            else:
                try:
                    if timeframe.lower().endswith('d'):
                        days = int(timeframe[:-1])
                        cutoff = now - timedelta(days=days)
                    elif timeframe.lower().endswith('h'):
                        hours = int(timeframe[:-1])
                        cutoff = now - timedelta(hours=hours)
                    else:
                        await ctx.send("Invalid timeframe format. Use e.g. '7d' for 7 days, '30d' for 30 days, or 'all'.")
                        return
                    df['Match Start Time'] = pd.to_datetime(df['Match Start Time'], errors='coerce', dayfirst=True)
                    filtered_df = df[df['Match Start Time'] >= cutoff]
                    timeframe_str = f"Last {timeframe}"
                except Exception as e:
                    await ctx.send(f"Error parsing timeframe: {e}")
                    return

            # --- Filter for valid matches only ---
            filtered_df = filtered_df[filtered_df['Match Result'].isin(['Crewmates Win', 'Impostors Win'])]
            if filtered_df.empty:
                await ctx.send(f"No valid matches found for {timeframe_str}.")
                return

            # --- Stats from events file ---
            # Win rates
            match_groups = filtered_df.groupby(['Match ID', 'Match Result']).size().reset_index()
            total_matches = match_groups['Match ID'].nunique()
            crewmate_wins = match_groups[match_groups['Match Result'] == 'Crewmates Win']['Match ID'].nunique()
            impostor_wins = match_groups[match_groups['Match Result'] == 'Impostors Win']['Match ID'].nunique()
            crewmate_winrate = (crewmate_wins / total_matches * 100) if total_matches > 0 else 0
            impostor_winrate = (impostor_wins / total_matches * 100) if total_matches > 0 else 0

            # Throwing stats
            crit_wrong = filtered_df.groupby('Player Name')['Voted Wrong on Crit'].sum()
            worst_thrower = crit_wrong.idxmax() if not crit_wrong.empty else 'N/A'
            worst_thrower_count = int(crit_wrong.max()) if not crit_wrong.empty else 0

            crit_right_lost = filtered_df.groupby('Player Name')['Voted Right on Crit but Lost'].sum()
            best_right_lost = crit_right_lost.idxmax() if not crit_right_lost.empty else 'N/A'
            best_right_lost_count = int(crit_right_lost.max()) if not crit_right_lost.empty else 0

            # Impostor stats
            kills = filtered_df.groupby('Player Name')['Number of Kills'].sum()
            top_killer = kills.idxmax() if not kills.empty else 'N/A'
            top_kills = int(kills.max()) if not kills.empty else 0

            imp_df = filtered_df[filtered_df['Player Team'] == 'impostor']
            total_imp_kills = imp_df['Number of Kills'].sum()
            total_imp_games = imp_df.groupby(['Match ID', 'Player Name']).ngroups
            kills_per_game = (total_imp_kills / total_imp_games) if total_imp_games > 0 else 0
            imp_games_per_player = imp_df.groupby('Player Name').size()
            imp_kills_per_player = imp_df.groupby('Player Name')['Number of Kills'].sum()
            kpg_per_player = (imp_kills_per_player / imp_games_per_player).replace([float('inf'), float('nan')], 0)
            eligible_kpg = kpg_per_player[imp_games_per_player >= 5]
            if not eligible_kpg.empty:
                top_kpg_player = eligible_kpg.idxmax()
                top_kpg = eligible_kpg.max()
            else:
                top_kpg_player = 'N/A'
                top_kpg = 0

            solo_imp_df = filtered_df[filtered_df['Solo Imp'] == True]
            if not solo_imp_df.empty:
                won_solo_imp_counts = solo_imp_df[solo_imp_df['Won as Solo Imp'] == True].groupby('Player Name').size()
                if not won_solo_imp_counts.empty:
                    best_solo_imp_player = won_solo_imp_counts.idxmax()
                    best_solo_imp_wins = int(won_solo_imp_counts.max())
                else:
                    best_solo_imp_player = 'N/A'
                    best_solo_imp_wins = 0
            else:
                best_solo_imp_player = 'N/A'
                best_solo_imp_wins = 0

            # Most kills in a single game (all tied)
            kills_per_game = filtered_df.groupby(['Match ID', 'Player Name'])['Number of Kills'].sum().reset_index()
            max_kills = kills_per_game['Number of Kills'].max() if not kills_per_game.empty else 0
            top_kill_players = kills_per_game[kills_per_game['Number of Kills'] == max_kills]['Player Name'].unique() if max_kills > 0 else []
            top_kill_players_str = ', '.join(top_kill_players) if len(top_kill_players) > 0 else 'N/A'

            # --- Stats from leaderboard (min 10 games) ---
            lb_eligible = lb[lb['Total Number Of Games Played'] >= 10]

            # Always define these before use to avoid NameError
            best_imp_str = 'N/A'
            best_crew_str = 'N/A'
            best_imp_rate = 0
            best_crew_rate = 0
            best_imp_player = 'N/A'
            best_crew_player = 'N/A'
            highest_voting_acc_str = 'N/A'
            lowest_voting_acc_str = 'N/A'
            highest_imp_surv_str = 'N/A'
            lowest_imp_surv_str = 'N/A'
            highest_crew_surv_str = 'N/A'
            lowest_crew_surv_str = 'N/A'

            # Most games played
            if not lb_eligible.empty:
                top_games_player = lb_eligible.loc[lb_eligible['Total Number Of Games Played'].idxmax()]['Player Name']
                top_games_total = int(lb_eligible['Total Number Of Games Played'].max())
                top_games_imp = int(lb_eligible.loc[lb_eligible['Total Number Of Games Played'].idxmax()]['Number Of Impostor Games Played'])
                top_games_crew = int(lb_eligible.loc[lb_eligible['Total Number Of Games Played'].idxmax()]['Number Of Crewmate Games Played'])
            else:
                top_games_player = 'N/A'
                top_games_total = top_games_imp = top_games_crew = 0
            # Voting accuracy
            if not lb_eligible.empty:
                highest_voting_acc = lb_eligible.loc[lb_eligible['Voting Accuracy (Crewmate games)'].idxmax()]
                lowest_voting_acc = lb_eligible.loc[lb_eligible['Voting Accuracy (Crewmate games)'].idxmin()]
                highest_voting_acc_str = f"{highest_voting_acc['Player Name']} ({highest_voting_acc['Voting Accuracy (Crewmate games)']*100:.1f}%)"
                lowest_voting_acc_str = f"{lowest_voting_acc['Player Name']} ({lowest_voting_acc['Voting Accuracy (Crewmate games)']*100:.1f}%)"
            else:
                highest_voting_acc_str = lowest_voting_acc_str = 'N/A'
            # Survivability
            if not lb_eligible.empty:
                imp_surv = lb_eligible[lb_eligible['Survivability (Impostor)'] > 0][['Player Name', 'Survivability (Impostor)']]
                crew_surv = lb_eligible[lb_eligible['Survivability (Crewmate)'] > 0][['Player Name', 'Survivability (Crewmate)']]
                if not imp_surv.empty:
                    highest_imp_surv = imp_surv.loc[imp_surv['Survivability (Impostor)'].idxmax()]
                    lowest_imp_surv = imp_surv.loc[imp_surv['Survivability (Impostor)'].idxmin()]
                    highest_imp_surv_str = f"{highest_imp_surv['Player Name']} ({highest_imp_surv['Survivability (Impostor)']*100:.1f}%)"
                    lowest_imp_surv_str = f"{lowest_imp_surv['Player Name']} ({lowest_imp_surv['Survivability (Impostor)']*100:.1f}%)"
                else:
                    highest_imp_surv_str = lowest_imp_surv_str = 'N/A'
                if not crew_surv.empty:
                    highest_crew_surv = crew_surv.loc[crew_surv['Survivability (Crewmate)'].idxmax()]
                    lowest_crew_surv = crew_surv.loc[crew_surv['Survivability (Crewmate)'].idxmin()]
                    highest_crew_surv_str = f"{highest_crew_surv['Player Name']} ({highest_crew_surv['Survivability (Crewmate)']*100:.1f}%)"
                    lowest_crew_surv_str = f"{lowest_crew_surv['Player Name']} ({lowest_crew_surv['Survivability (Crewmate)']*100:.1f}%)"
                else:
                    highest_crew_surv_str = lowest_crew_surv_str = 'N/A'
            else:
                highest_imp_surv_str = lowest_imp_surv_str = highest_crew_surv_str = lowest_crew_surv_str = 'N/A'
            # Best imp/crew win rate (ensure always defined)
            if not lb_eligible.empty:
                imp_win_eligible = lb_eligible[lb_eligible['Number Of Impostor Games Played'] >= 5]
                crew_win_eligible = lb_eligible[lb_eligible['Number Of Crewmate Games Played'] >= 10]
                if not imp_win_eligible.empty:
                    imp_win_rate = (imp_win_eligible['Number Of Impostor Games Won'] / imp_win_eligible['Number Of Impostor Games Played']).fillna(0)
                    best_imp_idx = imp_win_rate.idxmax()
                    best_imp_player = imp_win_eligible.loc[best_imp_idx]['Player Name']
                    best_imp_rate = imp_win_rate.max() * 100
                    best_imp_str = f"{best_imp_player} ({best_imp_rate:.1f}%)"
                if not crew_win_eligible.empty:
                    crew_win_rate = (crew_win_eligible['Number Of Crewmate Games Won'] / crew_win_eligible['Number Of Crewmate Games Played']).fillna(0)
                    best_crew_idx = crew_win_rate.idxmax()
                    best_crew_player = crew_win_eligible.loc[best_crew_idx]['Player Name']
                    best_crew_rate = crew_win_rate.max() * 100
                    best_crew_str = f"{best_crew_player} ({best_crew_rate:.1f}%)"

            # Most likely to be impostor (ratio of impostor games to total games, min 20 games)
            lb_imp_eligible = lb[lb['Total Number Of Games Played'] >= 20]
            if not lb_imp_eligible.empty:
                imp_ratio = (lb_imp_eligible['Number Of Impostor Games Played'] / lb_imp_eligible['Total Number Of Games Played']).fillna(0)
                most_likely_imp_idx = imp_ratio.idxmax()
                most_likely_imp_player = lb_imp_eligible.loc[most_likely_imp_idx]['Player Name']
                most_likely_imp_ratio = imp_ratio.max() * 100
            else:
                most_likely_imp_player = 'N/A'
                most_likely_imp_ratio = 0

            # --- Build Embed ---
            embed = discord.Embed(title=f"Season Stats ({timeframe_str})", color=discord.Color.purple())
            embed.set_thumbnail(url=self.guild.icon.url)
            embed.set_image(url=emojis['game_start_link'])
            embed.add_field(name=f"{emojis['emergency_emoji']}__**General Stats**__{emojis['emergency_emoji']}", value=(
                f"- Crewmate Win Rate: {crewmate_winrate:.2f}% ({crewmate_wins}/{total_matches})\n"
                f"- Impostor Win Rate: {impostor_winrate:.2f}% ({impostor_wins}/{total_matches})\n"
                f"- Most Games: {'**'+str(top_games_player)+'**' if top_games_player != 'N/A' else 'N/A'} ({top_games_total}, Imp: {top_games_imp}, Crew: {top_games_crew})\n"
                f"- Most Likely to be Impostor: {'**'+str(most_likely_imp_player)+'**' if most_likely_imp_player != 'N/A' else 'N/A'} ({most_likely_imp_ratio:.1f}%)\n"
            ), inline=False)
            embed.add_field(name=f"{emojis['kill_emoji']}__**Impostor Stats**__{emojis['kill_emoji']}", value=(
                f"- Top Killer: {'**'+str(top_killer)+'**' if top_killer != 'N/A' else 'N/A'} ({top_kills} kills)\n"
                f"- Highest Kills Per Game: {'**'+str(top_kpg_player)+'**' if top_kpg_player != 'N/A' else 'N/A'} ({top_kpg:.2f} KPG)\n"
                f"- Best Solo Imp: {'**'+str(best_solo_imp_player)+'**' if best_solo_imp_player != 'N/A' else 'N/A'} ({best_solo_imp_wins} Solo Imp wins)\n"
                f"- Most Kills in a Single Game: {'**'+top_kill_players_str+'**' if top_kill_players_str != 'N/A' else 'N/A'} ({max_kills} kills)\n"
                f"- Highest Impostor Survivability: {highest_imp_surv_str}\n"
                f"- Lowest Impostor Survivability: {lowest_imp_surv_str}\n"
                f"- Best Impostor Win Rate: {'**'+best_imp_player+'**' if best_imp_str != 'N/A' else 'N/A'} ({best_imp_rate:.1f}%)\n"
            ), inline=False)
            embed.add_field(name=f"{emojis['report_emoji']}__**Crewmate Stats**__{emojis['report_emoji']}", value=(
                f"- Highest Voting Accuracy: {highest_voting_acc_str}\n"
                f"- Lowest Voting Accuracy: {lowest_voting_acc_str}\n"
                f"- Highest Crewmate Survivability: {highest_crew_surv_str}\n"
                f"- Lowest Crewmate Survivability: {lowest_crew_surv_str}\n"
                f"- Best Crewmate Win Rate: {'**'+best_crew_player+'**' if best_crew_str != 'N/A' else 'N/A'} ({best_crew_rate:.1f}%)"
            ), inline=False)
            embed.add_field(name=f"{emojis['voted_emoji']}__**Critical Stats**__{emojis['voted_emoji']}", value=(
                f"- Worst Thrower on Crit :x:: {'**'+str(worst_thrower)+'**' if worst_thrower != 'N/A' else 'N/A'} ({worst_thrower_count} times)\n"
                f"- Most Voted :white_check_mark: but Lost: {'**'+str(best_right_lost)+'**' if best_right_lost != 'N/A' else 'N/A'} ({best_right_lost_count} times)\n"
            ), inline=False)
            embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)

    def add_events(self):
        @self.event
        async def on_ready():
            self.logger.info(f'{self.user} has connected to Discord!')
            self.guild = self.get_guild(self.guild_id)
            if not self.guild:
                self.logger.error(f"Could not find guild with ID {self.guild_id}")
                return
                
            self.logger.info(f"Connected to guild: {self.guild.name}")
            
            # Wait a moment for channels to be fully cached
            await asyncio.sleep(1)
            # await self.queue_manager.initialize_queue_embed()
            await self.get_members_in_channel()
            await self.update_leaderboard_discords()
            await self.download_player_icons()
            
            try:
                synced = await self.tree.sync()
                self.logger.info(f'Synced {len(synced)} commands to the guild.')
            except Exception as e:
                self.logger.error(f'Failed to sync commands: {e}')
                
            self.check_unblocks.start()
            if not self.check_vip_balances.is_running():
                self.check_vip_balances.start()
            self.logger.info(f'Ranked Among Us Bot has started!')

        @self.event
        async def on_voice_state_update(member:discord.Member, before:discord.VoiceState, after:discord.VoiceState):
            # await self.queue_manager.handle_voice_state_update(member, before, after)
            voice_channel_ids = [channel['voice_channel_id'] for channel in self.channels.values()]
            if (before.channel != after.channel) and \
                    ((before.channel and before.channel.id in voice_channel_ids) or (after.channel and after.channel.id in voice_channel_ids)):
                for channel in self.channels.values():
                    if before.channel and before.channel.id == channel['voice_channel_id']:
                        if member in channel['members']:
                            channel['members'].remove(member)
                            self.logger.debug(f'{member.display_name} left {before.channel.name}')
                    elif after.channel and after.channel.id == channel['voice_channel_id']:
                        if member not in channel['members']:
                            channel['members'].append(member)
                            self.logger.debug(f'{member.display_name} joined {after.channel.name}')

    @tasks.loop(minutes=10)
    async def check_vip_balances(self):
        """Periodically check and refresh VIP member balances"""
        try:
            #self.logger.info("Checking VIP member balances...")
            for member_id, member in self.premium.members.items():
                success, message = member.check_and_refresh_balance()
                if not success:
                    self.logger.error(f"Failed to check balance for member {member_id}: {message}")
                elif message:  # Balance was refreshed
                    self.logger.info(f"Balance refreshed for member {member_id}: {message}")
                    
            # Process any notifications that were generated
            await self.process_premium_notifications()
            
        except Exception as e:
            self.logger.error(f"Error in check_vip_balances task: {str(e)}")
    
    @tasks.loop(minutes=1)
    async def check_unblocks(self):
        df = pd.read_csv('rank_blocks.csv')
        now = datetime.now()
        for index, row in df.iterrows():
            unblock_time = datetime.strptime(row['Unblock Time'], "%Y-%m-%d %H:%M:%S")
            if now >= unblock_time:
                member = self.guild.get_member(int(row['Player ID']))
                if member:
                    blocked_role = self.guild.get_role(self.blocked_role_id)
                    normal_role = self.guild.get_role(self.ranked_access_role_id)
                    await member.remove_roles(blocked_role, reason="Unblocking - Time Expired")
                    await member.add_roles(normal_role, reason="Unblocking - Time Expired")
                df = df.drop(index)
        df.to_csv('rank_blocks.csv', index=False)

    def cog_unload(self):
        self.check_vip_balances.cancel()

    async def download_player_icons(self):
        icons_dir = 'player_icons'
        os.makedirs(icons_dir, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for _, row in self.leaderboard.leaderboard.iterrows():
                discord_id = row.get('Player Discord')
                if discord_id and discord_id != 0:
                    member = self.guild.get_member(int(discord_id))
                    if member and member.avatar:
                        icon_url = member.avatar.replace(size=64).url  # Small size for leaderboard
                        filename = os.path.join(icons_dir, f"{discord_id}.png")
                        tasks.append(self.download_icon(session, icon_url, filename))
            await asyncio.gather(*tasks)
        self.logger.info(f"Downloaded icons for {len(tasks)} players")

    async def download_icon(self, session, url, filename):
        async with session.get(url) as response:
            if response.status == 200:
                with open(filename, 'wb') as f:
                    f.write(await response.read())
                self.logger.debug(f"Downloaded icon: {filename}")
            else:
                self.logger.warning(f"Failed to download icon from {url}")

    async def get_members_in_channel(self):
        for channel in self.channels.values():
            voice_channel = self.get_channel(channel['voice_channel_id'])
            if voice_channel:
                members = voice_channel.members
                channel['members'] = [member for member in members]

    async def update_leaderboard_discords(self):
        # await self.validate_and_update_existing_discords()
        await self.add_missing_discords()
        await self.match_and_add_discords()
        self.leaderboard.save()

    async def validate_and_update_existing_discords(self):
        valid_ids = {member.id for member in self.guild.members}
        mask = self.leaderboard.leaderboard['Player Discord'].notnull()
        discord_ids = self.leaderboard.leaderboard.loc[mask, 'Player Discord'].astype(int)

        invalid_discords = discord_ids[~discord_ids.isin(valid_ids) & (discord_ids != 0)]
        if not invalid_discords.empty:
            self.leaderboard.leaderboard.drop(invalid_discords.index, inplace=True)
            # Convert index to string before joining
            invalid_ids_str = ', '.join(map(str, invalid_discords.index))
            self.logger.info(f"Removed Discord IDs for players not found in the guild: {invalid_ids_str}")
        else:
            self.logger.info("All Discord IDs in the leaderboard are valid.")

    async def add_missing_discords(self):
        member_dict = {member.display_name: member.id for member in self.guild.members}
        missing_discords = self.leaderboard.leaderboard[self.leaderboard.leaderboard['Player Discord'].isnull()]
        for player_name in missing_discords['Player Name']:
            if player_name in member_dict:
                self.leaderboard.add_player_discord(player_name, member_dict[player_name])
                self.logger.info(f"Added {player_name} to leaderboard with Discord ID from guild.")

    async def match_and_add_discords(self):
        players_with_empty_discord = self.leaderboard.players_with_empty_discord()
        if players_with_empty_discord is None:
            return

        for index, row in players_with_empty_discord.iterrows():
            player_name = row['Player Name']  
            if isinstance(player_name, int):
                self.logger.error(f"Player name is an integer: {player_name}, which is unexpected.")
                continue  

            player_name_normalized = player_name.lower().replace(" ", "")
            best_match = None
            best_score = 0
            for member in self.guild.members:
                member_display_name = member.display_name.lower().replace(" ", "")
                match_score = fuzz.token_sort_ratio(player_name_normalized, member_display_name)
                if match_score > best_score and match_score >= 80:
                    best_match = member
                    best_score = match_score

            if best_match:
                self.leaderboard.add_player_discord(player_name, best_match.id)
                self.logger.info(f"Added {best_match.display_name} to {player_name} in leaderboard")
            else:
                self.logger.warning(f"Can't find a discord match for player {player_name} in {self.guild.name}")

    def start_game_embed(self, json_data) -> discord.Embed:
        players = json_data.get("Players", [])
        player_colors = json_data.get("PlayerColors", [])
        match_id = json_data.get("MatchID", "")
        game_code = json_data["GameCode"] 
        self.logger.info(f'Creating an embed for game start MatchId={match_id}')
        
        embed = discord.Embed(title=f"Ranked Match Started", description=f"Match ID: {match_id} - Code: {game_code}\n Players:", color=discord.Color.dark_purple())

        for player_name, player_color in zip(players, player_colors): 
            player_row = self.leaderboard.get_player_row(player_name)
            player_discord_id = self.leaderboard.get_player_discord(player_row)
            color_emoji = emojis['default_color_emojis'].get(player_color, ":question:")
            value = color_emoji
            try:
                player_discord = self.guild.get_member(int(player_discord_id))
                value += f" {player_discord.mention}"
            except:
                value += f" @{player_name}"
            player_mmr = self.leaderboard.get_player_mmr(player_row)
            value += "\nMMR: " + f" {player_mmr if player_mmr else 'New Player'}"
            embed.add_field(name=player_name, value=value, inline=True)
        
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
        embed.set_image(url=emojis['game_start_link'])
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match Started: {current_time} - Bot Programmed by Aiden", icon_url=self.guild.icon.url)
        return embed

    def end_game_embed(self, match: Match, json_data=None) -> discord.Embed:
        player:PlayerInMatch
        if json_data is None:
            json_data = json.loads('{"GameCode":"NA","PlayerColors":[1,2,3,4,5,6,7,8,9,10]}')

        player_colors = json_data.get("PlayerColors", [])
        game_code = json_data["GameCode"]
        match.set_player_colors_in_match(player_colors)
        self.logger.info(f'Creating an embed for game End MatchId={match.id}')


        if match.result.lower() == "impostors win":
            embed_color = discord.Color.red()
        elif match.result.lower() == "crewmates win":
            embed_color = discord.Color.green()
        else:
            embed_color = discord.Color.orange()

        embed = discord.Embed(title=f"Ranked Match Ended - {match.result}", 
                      description=f"Match ID: {match.id} Code: {game_code}\nPlayers:", color=embed_color)

        members_discord = [(member.display_name.lower().strip()[:10], member) for member in self.guild.members]
        name_to_member = {name: member for name, member in members_discord}

        for player in match.players:
            if player.discord == 0:
                try:
                    results = process.extractOne(player.name.lower().strip(), list(name_to_member.keys()))
                    if results:  
                        best_match, score = results  
                        if score > 80: 
                            matching_member = name_to_member.get(best_match)
                            if matching_member:
                                player.discord = matching_member  #
                except ValueError as e:
                    self.logger.error(f"Error processing player {player.name}: {e}")

        for player in match.get_players_by_team("impostor"):
            self.logger.debug(f"processing impostor:{player.name}")
            value = "" 
            color_emoji = emojis['default_color_emojis'].get(player.color, ":question:")
            
            value = color_emoji
            try:
                player_in_discord = self.guild.get_member(int(player.discord))
                value += f" {player_in_discord.mention}"
            except:
                self.logger.error(f"Can't find discord for player {player.name}, please link")
            value += "\nMMR: " + f" {round(player.current_mmr, 1) if player.current_mmr else 'New Player'}"
            value += f"\nImp MMR: {'+' if player.impostor_mmr_gain >= 0 else ''}{round(player.impostor_mmr_gain, 1)}"
            embed.add_field(name=f"{player.name} __**(Imp)**__", value=value, inline=True)

        embed.add_field(name=f"Imp Win rate: {round(match.imp_winning_percentage*100,2)}%\nCrew Win Rate: {round(match.crew_winning_percentage*100,2)}%", value=" ", inline=True) 

        for player in match.get_players_by_team("crewmate"):
            value = "" 
            self.logger.debug(f"processing crewmate:{player.name}")
            color_emoji = emojis['default_color_emojis'].get(player.color, ":question:")
            value = color_emoji
            try:
                player_in_discord = self.guild.get_member(int(player.discord))
                value += f" {player_in_discord.mention}"
            except:
                self.logger.error(f"Can't find discord for player {player.name}, please link")
            value += "\nMMR: " + f" {round(player.current_mmr, 1) if player.current_mmr else 'New Player'}"
            value += f"\nCrew MMR: {'+' if player.crewmate_mmr_gain >= 0 else ''}{round(player.crewmate_mmr_gain, 1)}"
            value += f"\nTasks: {player.tasks_complete}/10"
            embed.add_field(name=f"{player.name}", value=value, inline=True)

        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
        datetime.now().timestamp
        if match.result == "Impostors Win":
            embed.set_image(url=emojis['imp_win_link'])
        elif match.result in ["Crewmates Win", "HumansByVote"]:
            embed.set_image(url=emojis['crew_win_link'])
        else:
            embed.set_image(url=emojis['cancel_link'])
            
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match Started: {current_time} - Bot Programmed by Aiden", icon_url=self.guild.icon.url)
        return embed  

    def events_embed(self, match:Match) -> discord.Embed:
        player:PlayerInMatch
        for player in match.players:
            player.tasks_complete = 0
            if player.team == "impostor": 
                player.color +=100
        votes_embed = discord.Embed(title=f"Match ID: {match.id} - Events", description="")
        events_df = pd.read_json(os.path.join(self.matches_path, match.event_file_name), typ='series')
        
        meeting_count = 0
        meeting_end = False
        meeting_start = False

        events_embed = f"__**Round {meeting_count+1} Actions**__\n"
        for event in events_df:
            event_type = event.get('Event')
            for key in ['Name', 'Player', 'Target', 'Killer']:
                if key in event:
                    if event[key].endswith(" |"):
                        event[key] = event[key][:-2] 
                
            if event_type == "Task":
                player = match.get_player_by_name(event.get('Name'))
                player.finished_task()
                if player.tasks_complete == 10:
                    color_emoji = emojis['default_color_emojis'].get(player.color, "?")
                    events_embed += f"{color_emoji} Tasks {emojis['done_emoji']} {'Alive' if player.alive else 'Dead'}\n"

            elif event_type == "PlayerVote":
                player = match.get_player_by_name(event.get('Player'))
                target = match.get_player_by_name(event.get('Target'))
                player_emoji = emojis['default_color_emojis'].get(player.color, "?")
                if target == None:
                    events_embed += f" {player_emoji} Skipped\n"
                else:
                    target_emoji = emojis['default_color_emojis'].get(target.color, "?")
                    events_embed += f" {player_emoji} voted {target_emoji}\n"
                    
            elif event_type == "Death":
                player = match.get_player_by_name(event.get('Name'))
                killer = match.get_player_by_name(event.get('Killer'))
                player_emoji = emojis['default_color_emojis'].get(player.color+200, "?")
                killer_emoji = emojis['default_color_emojis'].get(killer.color, "?")
                events_embed += f" {killer_emoji} {emojis['kill_emoji']} {player_emoji}\n"
                
            elif event_type == "BodyReport":
                player = match.get_player_by_name(event.get('Player'))
                dead_player = match.get_player_by_name(event.get('DeadPlayer'))
                player_emoji = emojis['default_color_emojis'].get(player.color, "?")
                dead_emoji = emojis['default_color_emojis'].get(dead_player.color+200, "?")
                events_embed += f" {player_emoji} {emojis['report_emoji']} {dead_emoji}\n"
                meeting_start = True
                meeting_count+=1
                
            elif event_type == "MeetingStart":
                player = match.get_player_by_name(event.get('Player'))
                player_emoji = emojis['default_color_emojis'].get(player.color, "?")
                events_embed += f" {player_emoji} {emojis['emergency_emoji']} Meeting\n"
                meeting_start = True
                meeting_count+=1
                
            elif event_type == "Exiled":
                ejected_player = match.get_player_by_name(event.get('Player'))
                ejected_emoji = emojis['default_color_emojis'].get(ejected_player.color, "?")
                events_embed += f"{ejected_emoji} __was **Ejected**__\n"
                meeting_end = True
                events_embed += f"Meeting End\n"
            
            elif event_type == "GameCancel":
                events_embed += f"__**Game {match.id} Canceled**__\n"
                
          
            elif event_type == "ManualGameEnd":
                events_embed += f"__**Manual End**__\n"
                break

            elif event_type == "Disconnect":
                disconnected_player = match.get_player_by_name(event.get('Name'))
                disconnected_emoji = emojis['default_color_emojis'].get(disconnected_player.color, "?")
                events_embed += f"{disconnected_emoji}{'__** Disconnected Alive**__' if disconnected_player.alive else 'Disconnected Dead'}\n"
                
            elif event_type == "MeetingEnd":
                if (event.get("Result") == "Exiled"):
                    continue

                elif (event.get("Result") == "Tie"):
                    events_embed += f"__**Votes Tied**__\n"
                else:
                    events_embed += f"__**Skipped**__\n"
                meeting_end = True
                events_embed += f"Meeting End\n"

            if meeting_end == True:
                if len(events_embed) >= 1023:
                    self.logger.error(events_embed)
                votes_embed.add_field(name = "", value=events_embed, inline=True)
                events_embed = ""
                events_embed += f"__**Round {meeting_count+1} Actions**__\n"
                meeting_end = False 

            elif meeting_start == True:
                events_embed += f"__Meeting #{meeting_count}__\n"
                meeting_start = False

        
        events_embed += f"**Match {match.id} Ended**\n"
        events_embed += f"**{match.result}**"
        votes_embed.add_field(name = "", value=events_embed, inline=True)
        votes_embed.set_footer(text=f"Bot Programmed by Aiden | Version: {self.version}", icon_url=self.guild.icon.url)
        return votes_embed

    def find_most_matched_channel(self, json_data):
        players = json_data.get("Players", [])
        max_matches = 0
        most_matched_channel_name = None
        players = {player.lower().strip() for player in players} #normalize
        
        for channel_name, channel_data in self.channels.items():
            channel_members = channel_data['members']
            matches = 0
            for player in players:
                for member in channel_members:
                    # Compare cropped strings of player name and member display name
                    cropped_player_name = player[:min(len(player), len(member.display_name))]
                    cropped_member_name = member.display_name.lower().strip()[:min(len(player), len(member.display_name))]
                    similarity_ratio = fuzz.ratio(cropped_player_name, cropped_member_name)
                    if similarity_ratio >= self.ratio:  # Adjust threshold as needed
                        matches += 1
                        break  # Exit inner loop once a match is found
            if matches > max_matches:
                max_matches = matches
                most_matched_channel_name = channel_name
            if matches >= 4:
                return self.channels.get(most_matched_channel_name)
        return self.channels.get(most_matched_channel_name)

    async def add_players_discords(self, json_data, game_channel):
        players = json_data.get("Players", [])
        match_id = json_data.get("MatchID", "")
        self.logger.info(f'Adding discords from match={match_id} to the leaderboard if missing and creating new players')
        members_started_the_game = game_channel['members_in_match']

        for member in members_started_the_game:
            best_match = None
            best_similarity_ratio = 0
            for player in players:
                cropped_player_name = player.lower().strip()[:min(len(player), len(member.display_name.strip()))]
                cropped_member_name = member.display_name.lower().strip()[:min(len(player), len(member.display_name.strip()))]
                similarity_ratio = fuzz.ratio(cropped_player_name, cropped_member_name)
                if similarity_ratio >= self.ratio and similarity_ratio > best_similarity_ratio:
                    best_similarity_ratio = similarity_ratio
                    best_match = (player, member)
            if best_match is not None:
                self.logger.debug(f"found {best_match[1].display_name}")
                player_name, member = best_match
                player_row = self.leaderboard.get_player_row(player_name)

                if player_row is None:
                    self.logger.info(f"Player {player_name} was not found in the leaderboard, creating a new player")
                    self.leaderboard.new_player(player_name)
                    self.leaderboard.add_player_discord(player_name, member.id)
                    self.leaderboard.save()

                if self.leaderboard.get_player_discord(player_row) is None:
                    self.logger.info(f"Player {player_name} has no discord in the leaderboard, adding discord {member.id}")
                    self.leaderboard.add_player_discord(player_name, member.id)
                    self.leaderboard.save()
            else:
                self.logger.error(f"Can't find a match a player for member {member.display_name}")

    async def handle_game_start(self, json_data):
        match_id = json_data.get("MatchID", "")
        game_code = json_data.get("GameCode", "")
        players = set(json_data.get("Players", []))
        impostors = set(json_data.get("Impostors", []))
        game_channel = self.find_most_matched_channel(json_data)
        
        # for game in self.games_in_progress:
        #     if game["GameVoiceChannelID"] == game_channel['voice_channel_id'] and game_code != game['GameCode']:
        #         logging.warning(f"Lobby {game_code} is not the real lobby, there's a game with similar players running already")
        #         return

        game = {"GameCode":game_code, "MatchID": match_id, "Players": players, "Impostors": impostors, "GameVoiceChannelID": game_channel['voice_channel_id']}
        self.games_in_progress.append(game)
        self.logger.info(f"Code:{game_code}, ID:{match_id}, Players:{players}, VC ID: {game_channel['voice_channel_id']} added to games in progress.")

        if game_channel:
            game_channel['members_in_match'] = game_channel.get('members')
            if self.auto_mute:
                await self.game_start_automute(game_channel)
            text_channel_id = game_channel['text_channel_id']
            await self.add_players_discords(json_data, game_channel)
            embed = self.start_game_embed(json_data)
            text_channel = self.get_channel(text_channel_id)
            if text_channel:
                await text_channel.send(embed=embed)
            else:
                self.logger.error(f"Text channel with ID {text_channel_id} not found.")
            # await self.queue_manager.handle_game_started(game_channel, game_code, match_id)
        else:
            self.logger.error(f"Could not find a matching game channel to the game not found.")

    async def game_start_automute(self, game_channel):
        voice_channel_id = game_channel['voice_channel_id']
        voice_channel = self.get_channel(voice_channel_id)
        if voice_channel is not None:
            tasks = []
            for member in voice_channel.members:
                tasks.append(member.edit(mute=True, deafen=True))
                self.logger.debug(f"Deafened and Muted {member.display_name}")
            try:
                await asyncio.gather(*tasks)  # undeafen all players concurrently
            except:
                self.logger.warning("Some players left the VC on Game Start")
        else:
            self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")

    async def handle_meeting_start(self, json_data):
        players = set(json_data.get("Players", []))
        game_code = json_data.get("GameCode", "")
        dead_players = set(json_data.get("DeadPlayers", []))
        alive_players = players - dead_players
        dead_players_normalized = {player.lower().replace(" ", "") for player in dead_players}
        alive_players_normalized = {player.lower().replace(" ", "") for player in alive_players}
        tasks = []
            
        game_channel = self.find_most_matched_channel(json_data)
        # for game in self.games_in_progress:
        #     if game["GameVoiceChannelID"] == game_channel['voice_channel_id'] and game_code != game['GameCode']:
        #         logging.warning(f"Lobby {game_code} is not the real lobby, there's a game with similar players running already")
        #         return
            
        if game_channel:
            voice_channel_id = game_channel.get('voice_channel_id')
            text_channel_id = game_channel.get('text_channel_id')
            voice_channel = self.get_channel(voice_channel_id)
            text_channel = self.get_channel(text_channel_id)

            if voice_channel is not None:
                members_in_vc = {(member_in_vc.display_name.lower().replace(" ", ""), member_in_vc) for member_in_vc in voice_channel.members}
                remaining_members = []
                for element in members_in_vc:
                    match_found = False
                    display_name, member = element

                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and muted {member.display_name}")
                        match_found = True 
                        continue

                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and unmuted {member.display_name}")
                        match_found = True 

                    if not match_found:
                        remaining_members.append(element)

                remaining_members_final = []
                for element in remaining_members:
                    display_name, member = element
                    match_found = False

                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        self.logger.debug(f"deafened and unmuted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and unmuted {member.display_name}")
                        match_found = True

                    if not match_found:
                        remaining_members_final.append(element)

                for element in remaining_members_final:
                    display_name, member = element
                    match_found = False
                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and muted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and unmuted {member.display_name}")
                        match_found = True

                    if not match_found:
                        self.logger.error(f"Could not perform automute on {member.display_name}")
                        await text_channel.send(f"Could not perform automute on {member.display_name}")
                try: 
                    await asyncio.gather(*tasks)
                except:
                    self.logger.warning("Some players left the VC on Meeting Start")
            else:
                self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")
        else:
            self.logger.error("No suitable game channel found for the players.")

    async def handle_meeting_end(self, json_data):
        players = set(json_data.get("Players", []))
        impostors = set(json_data.get("Impostors", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        game_code = json_data.get("GameCode", "")
        alive_players = players - dead_players
        dead_players_normalized = {player.lower().replace(" ", "") for player in dead_players}
        alive_players_normalized = {player.lower().replace(" ", "") for player in alive_players}
        game_channel = self.find_most_matched_channel(json_data)

        if game_channel is None:
            self.logger.info(f"a null game channel was found in meeting end automute, ignoring")
            return

        # for game in self.games_in_progress:
        #     if game["GameVoiceChannelID"] == game_channel['voice_channel_id'] and game_code != game['GameCode']:
        #         logging.warning(f"Lobby {game_code} is not the real lobby, there's a game with similar players running already")
        #         return
            
        game_ended = impostors.issubset(dead_players)
        if game_ended:
            self.logger.info(f"Skipping MeetingEnd Automute because all impostors are dead.")
            return
        
        if game_channel:
            voice_channel_id = game_channel.get('voice_channel_id')
            text_channel_id = game_channel.get('text_channel_id')
            voice_channel = self.get_channel(voice_channel_id)
            text_channel = self.get_channel(text_channel_id)

            if voice_channel is not None:
                members_in_vc = {(member_in_vc.display_name.lower().replace(" ", ""), member_in_vc) for member_in_vc in voice_channel.members}
                remaining_members = []
                tasks = []
                for element in members_in_vc:
                    match_found = False
                    display_name, member = element

                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        self.logger.debug(f"undeafened and unmuted {member.display_name}")
                        tasks.append(member.edit(mute=False, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        match_found = True

                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"deafened and muted {member.display_name}")
                        match_found = True

                    if not match_found:
                        remaining_members.append(element)

                remaining_members_final = []
                for element in remaining_members:
                    display_name, member = element
                    match_found = False

                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and unmuted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"deafened and muted {member.display_name}")
                        match_found = True

                    if not match_found:
                        remaining_members_final.append(element)
                        
                for element in remaining_members_final:
                    display_name, member = element
                    match_found = False
                    best_match = difflib.get_close_matches(display_name, dead_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        self.logger.debug(f"undeafened and muted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.debug(f"deafened and muted {member.display_name}")
                        match_found = True

                    if not match_found:
                        self.logger.error(f"Could not perform automute on {member.display_name}")
                        await text_channel.send(f"Could not perform automute on {member.display_name}")

                await asyncio.sleep(6) 
                try:
                    await asyncio.gather(*tasks)
                except:
                    self.logger.warning("Some players left the VC on Meeting End")
            else:
                self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")
        else:
            self.logger.error(f"Could not find a matching game channel to the game not found.")

    async def game_end_automute(self, voice_channel, voice_channel_id):
        if voice_channel is not None:
            tasks = []
            for member in voice_channel.members:
                tasks.append(member.edit(mute=False, deafen=False))
            try:
                await asyncio.gather(*tasks)  # undeafen all players concurrently
            except:
                self.logger.warning("Some players left the VC on Game End")
        else:
            self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")

    async def change_player_roles(self, members: list[discord.Member]):
        ranked_roles = [role for role in self.guild.roles if role.name.startswith("Ranked |")]
        special_roles = {
            "Ace": (self.leaderboard.is_player_ace, "https://i.ibb.co/syZmBKq/ACEGIF.gif"),
            "Sherlock": (self.leaderboard.is_player_sherlock, "https://i.ibb.co/XCg5Q46/SHERLOCKGIF.gif"),
            "Jack the Ripper": (self.leaderboard.is_player_jack_the_ripper, "https://i.ibb.co/3MvjnDc/JackGIF.gif")
        }
        role_ranges = {
            "Iron": (None, 850),
            "Bronze": (851, 950),
            "Silver": (951, 1050),
            "Gold": (1051, 1150),
            "Platinum": (1151, 1250),
            "Diamond": (1251, 1350),
            "Master": (1351, 1450),
            "Warrior": (1451, None)
        }

        # Handle special roles across all members who currently hold those roles
        for role_name, (check_function, image_url) in special_roles.items():
            special_role = discord.utils.get(self.guild.roles, name=role_name)
            if special_role:
                current_holders = special_role.members
                for member in current_holders:
                    player_row = self.leaderboard.get_player_by_discord(member.id)
                    if player_row is not None:
                        has_role = check_function(player_row['Player Name'])
                        if not has_role:
                            await member.remove_roles(special_role)
                            self.logger.info(f"Removed {special_role.name} from {member.display_name}")

                # Check if any member in the members list now qualifies for the special roles
                for member in members:
                    player_row = self.leaderboard.get_player_by_discord(member.id)
                    qualifies_for_role = check_function(player_row['Player Name'])
                    if qualifies_for_role and special_role not in member.roles:
                        await member.add_roles(special_role)
                        self.logger.info(f"Added {special_role.name} to {member.display_name}")
                        embed = discord.Embed(
                            title=f"Congratulations {member.display_name}!",
                            description=f"{member.mention} You have been awarded the **{special_role.name}** role!",
                            color=discord.Color.green()
                        )
                        embed.set_image(url=image_url)
                        channel = self.guild.get_channel(self.ranked_chat_channel)
                        await channel.send(embed=embed)


        # Then, handle ranked roles for the provided members
        for member in members:
            player_row = self.leaderboard.get_player_by_discord(member.id)
            if player_row is not None:
                player_mmr = player_row['MMR']
                current_ranked_roles = [role for role in member.roles if role.name.startswith("Ranked |")]
                desired_role_name = None
                for rank, (lower, upper) in role_ranges.items():
                    if lower is None and player_mmr <= upper:
                        desired_role_name = f"Ranked | {rank}"
                        break
                    elif upper is None and player_mmr >= lower:
                        desired_role_name = f"Ranked | {rank}"
                        break
                    elif lower is not None and upper is not None and lower <= player_mmr <= upper:
                        desired_role_name = f"Ranked | {rank}"
                        break

                if desired_role_name:
                    desired_role = discord.utils.get(ranked_roles, name=desired_role_name)
                    if desired_role:
                        if desired_role not in current_ranked_roles:
                            await member.remove_roles(*current_ranked_roles)
                            self.logger.info(f"Removed {current_ranked_roles} from {member.display_name}")
                            await member.add_roles(desired_role)
                            self.logger.info(f"Added {desired_role} to {member.display_name}")

    async def handle_game_end(self, json_data):
        match_id = json_data.get("MatchID", "")
        game_code = json_data.get("GameCode", "")
        game_channel = self.find_most_matched_channel(json_data)
        if game_channel is None:
            self.logger.error(f"No game channel found for match {match_id}")
            await self.get_channel(self.admin_logs_channel).send(f"MatchID:{match_id}, Code:{game_code} ended but no game channel was found")
            return
        voice_channel_id = game_channel['voice_channel_id']
        text_channel_id = game_channel['text_channel_id']
        voice_channel = self.get_channel(voice_channel_id)

        ## Check for existing games
        for game in self.games_in_progress:
        #     if game["GameVoiceChannelID"] == game_channel['voice_channel_id'] and game_code != game['GameCode']:
        #         logging.warning(f"Lobby {game_code} is not the real lobby, a game with similar players is running already")
        #         return
            if game.get("GameCode") == game_code:
                match_id = game.get("MatchID")
                self.logger.info(f"Game {game} removed from games in progress.")
                self.games_in_progress.remove(game)

        if self.auto_mute:
            await self.game_end_automute(voice_channel, voice_channel_id)
        
        # Check if this is a VIP multiplier match
        k_value = 32  # default K value
        if self.premium.is_channel_using_special_games(voice_channel_id):
            active_games = self.premium.get_active_special_games()
            game_info = active_games[voice_channel_id]
            k_value = 64 if game_info['balance_type'] == 'double' else 96
            
            # Log the special match
            success, completed, msg = self.premium.log_special_match(
                channel_id=voice_channel_id,
                match_id=match_id,
                time_of_match=datetime.now()
            )
            if success:
                self.logger.info(f"VIP Match {match_id} logged: {msg}")
            else:
                self.logger.error(f"Failed to log VIP Match {match_id}: {msg}")
        
        # Process match with appropriate K value
        last_match = self.file_handler.process_match_by_id(match_id, k=k_value)
        if last_match.crewmates_count != 8:
            return
        
        for i in range(10):
            if last_match.result == "Unknown":
                await asyncio.sleep(1)
                last_match = self.file_handler.process_match_by_id(match_id, k=k_value)
                if i == 9:
                    self.logger.warning(f"Match {match_id} was not loaded correctly")
            else:
                break

        end_embed = self.end_game_embed(last_match, json_data)
        events_embed = self.events_embed(last_match)
        view = VotesView(embed=events_embed)

        await self.get_channel(text_channel_id).send(embed=end_embed, view=view)
        await self.get_channel(self.match_logs).send(embed=end_embed, view=view)

        await self.change_player_roles(game_channel['members_in_match'])

        game_channel['members_in_match'] = []
        
    async def send_special_mmr_completion_embed(self, channel_id: int, match_id: int, text_channel_id: int):
        """Send special MMR completion status after a game ends"""
        if not self.premium.is_channel_using_special_games(channel_id):
            return

        active_games = self.premium.get_active_special_games()
        game_info = active_games[channel_id]
        
        embed = discord.Embed(
            title="Special MMR Game Complete",
            color=discord.Color.blue()
        )
        
        # Get host's mention
        host_member = self.guild.get_member(int(game_info['member_id']))
        host_mention = host_member.mention if host_member else game_info['member_name']
        
        embed.add_field(
            name="Match ID",
            value=str(match_id),
            inline=True
        )
        
        embed.add_field(
            name="Type",
            value=f"{game_info['balance_type'].title()} MMR",
            inline=True
        )
        
        embed.add_field(
            name="Host",
            value=host_mention,
            inline=True
        )
        
        games_left = game_info['games_remaining'] - 1  # Subtract current game
        embed.add_field(
            name="Games Remaining",
            value=str(games_left),
            inline=True
        )

        # Send to text channel
        text_channel = self.get_channel(text_channel_id)
        if text_channel:
            await text_channel.send(embed=embed)
            
            # If this was the last game, send completion message
            if games_left <= 0:
                complete_embed = discord.Embed(
                    title="Special MMR Session Ended",
                    description=f"All {game_info['balance_type']} MMR games have been completed.",
                    color=discord.Color.red()
                )
                complete_embed.add_field(
                    name="Host",
                    value=host_mention,
                    inline=True
                )
                await text_channel.send(embed=complete_embed)

    async def process_premium_notifications(self):
        """Process any pending notifications from the premium system"""
        try:
            while self.premium.notifications:
                notification = self.premium.notifications.pop(0)
                
                if notification['type'] == 'balance_refresh':
                    channel = self.get_channel(self.admin_logs_channel)
                    if channel:
                        await channel.send(notification['message'])
                        
        except Exception as e:
            self.logger.error(f"Error processing premium notifications: {str(e)}")

    async def handle_client(self, reader, writer):
        data = await reader.read(1024)
        message = data.decode('utf-8')
        self.logger.info(f"Received: {message}") 

        try:
            json_data = json.loads(message)
            event_name = json_data.get("EventName")
            match_id = json_data.get("MatchID", "")
            game_code = json_data["GameCode"]

            if event_name == "GameStart":
                self.logger.info(f"Game ID:{match_id} Started. - Code({game_code})")
                await self.handle_game_start(json_data)

            elif event_name == "MeetingStart":
                self.logger.info(f"Game Code:{game_code} Meeting Started.")
                if self.auto_mute:
                    await self.handle_meeting_start(json_data) #this is automute

            elif event_name == "MeetingEnd":
                self.logger.info(f"Game Code:{game_code} Meeting Endded.")
                if self.auto_mute:
                    await self.handle_meeting_end(json_data) #this is automute

            elif event_name == "GameEnd":
                self.logger.info(f"Game ID:{match_id} Endded. - Code({game_code})")
                await self.handle_game_end(json_data)
                
            else:
                self.logger.info("Unsupported event:", event_name)

        except json.JSONDecodeError as e:
            self.logger.error("Error decoding JSON:", e)
        except Exception as e:
            self.logger.error(f"Error processing event: {str(e)}") 
    
    async def start_server(self):
        server = await asyncio.start_server(self.handle_client, '0.0.0.0', 5000)
        async with server:
            self.logger.info("Socket server is listening on localhost:5000...")
            await server.serve_forever()

    async def start_bot(self):
        await asyncio.gather(
            self.start_server(),
            super().start(self.token)
        )

    def log_mmr_change(self, player_name: str, mmr_value: float, change_type: str, moderator: str, reason: str = None):
        """Log MMR changes to a CSV file for persistence"""
        try:
            mmr_changes_file = 'mmr_changes.csv'
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Create the data row
            data = {
                'Timestamp': [current_time],
                'Player Name': [player_name],
                'MMR Value': [mmr_value],
                'Change Type': [change_type],  # 'total', 'crew', or 'imp'
                'Moderator': [moderator],
                'Reason': [reason if reason else '']
            }
            
            df = pd.DataFrame(data)
            
            # Append to CSV file (create if doesn't exist)
            if os.path.exists(mmr_changes_file):
                df.to_csv(mmr_changes_file, mode='a', header=False, index=False)
            else:
                df.to_csv(mmr_changes_file, index=False)
                
            self.logger.info(f"Logged MMR change: {player_name} {mmr_value:+} ({change_type}) by {moderator}")
            
        except Exception as e:
            self.logger.error(f"Error logging MMR change: {str(e)}")

    def apply_stored_mmr_changes(self):
        """Apply all stored MMR changes from the CSV file"""
        try:
            mmr_changes_file = 'mmr_changes.csv'
            if not os.path.exists(mmr_changes_file):
                self.logger.info("No MMR changes file found, skipping stored changes")
                return
                
            df = pd.read_csv(mmr_changes_file)
            if df.empty:
                self.logger.info("MMR changes file is empty, skipping stored changes")
                return
                
            self.logger.info(f"Applying {len(df)} stored MMR changes...")
            
            for index, row in df.iterrows():
                try:
                    player_name = row['Player Name']
                    mmr_value = float(row['MMR Value'])
                    change_type = row['Change Type']
                    moderator = row['Moderator']
                    reason = row.get('Reason', '')
                    
                    # Get player row
                    player_row = self.leaderboard.get_player_row(player_name)
                    if player_row is None:
                        self.logger.warning(f"Player {player_name} not found in leaderboard, skipping MMR change")
                        continue
                    
                    # Apply the MMR change based on type
                    if change_type == 'crew':
                        self.leaderboard.mmr_change_crew(player_row, mmr_value)
                        change_text = "Crew"
                    elif change_type == 'imp':
                        self.leaderboard.mmr_change_imp(player_row, mmr_value)
                        change_text = "Impostor"
                    else:  # total
                        self.leaderboard.mmr_change(player_row, mmr_value)
                        change_text = "Total"
                    
                    self.logger.info(f"Applied stored MMR change: {player_name} {mmr_value:+} ({change_text}) by {moderator}")
                    
                except Exception as e:
                    self.logger.error(f"Error applying stored MMR change at row {index}: {str(e)}")
                    continue
            
            self.logger.info("Finished applying stored MMR changes")
            
        except Exception as e:
            self.logger.error(f"Error applying stored MMR changes: {str(e)}")


if __name__ == "__main__":
    # Usage: python discord_bot.py [main|test]
    bot = DiscordBot(token=config['token'], variables=config)
    import asyncio
    asyncio.run(bot.start_bot())