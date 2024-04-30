import difflib
import discord
from discord import Button, ButtonStyle
from discord.ext import commands
from discord.ext.commands import Context
import asyncio
import json
from datetime import datetime
import discord.ext
import discord.ext.commands
from file_processing import FileHandler
from match_class import Match
import logging
from rapidfuzz import fuzz
from rapidfuzz import process
import pandas as pd
import time
import os

default_color_emojis = {
    0 : "<:Red_crewmate:1228193212716421130>",
    1 : "<:Blue_crewmate:1228163812054532166>",
    2 : "<:Green_crewmate:1228193210032193556>",
    3 : "<:Pink_crewmate:1228193211437023332>",
    4 : "<:Orange_crewmate:1228163815301054564>",
    5 : "<:Yellow_crewmate:1228193217456115722>",
    6 : "<:Black_crewmate:1228163811085647953>",
    7 : "<:White_crewmate:1228193257339486338>",
    8 : "<:Purple_crewmate:1228175468428005446>",
    9 : "<:Brown_crewmate:1228163812717236225>",
    10 : "<:Cyan_crewmate:1228193206244606035>",
    11 : "<:Lime_crewmate:1228175470290538506>",
    12 : "<:Maroon_crewmate:1228163814009077890>",
    13 : "<:Rose_crewmate:1228193213815197717>",
    14 : "<:Banana_crewmate:1228163809999323236>",
    15 : "<:Gray_crewmate:1228193208060870726>",
    16 : "<:Tan_crewmate:1228193214826020905>",
    17 : "<:Coral_crewmate:1228193205397360670>"
    # Add more default colors and URLs here...
}
top_emojis = ["🥇", "🥈", "🥉"]
extra_emojis = ["👑", "💎", "🎖️", "🏆", "🏅"]
class DiscordBot(commands.Bot):
    def __init__(self, command_prefix='!', token = None, variables = None, **options):
        # init loggers
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("websockets").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)
        logging.basicConfig(level=logging.DEBUG, encoding='utf-8', format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler("DiscordBot.log", encoding='utf-8'),logging.StreamHandler()])
        self.logger = logging.getLogger('Discord_Bot')

        # init guild variables
        self.matches_path = variables['matches_path']
        self.database_location = variables['database_location']
        self.channels = variables['ranked_channels']
        self.guild_id = variables['guild_id']
        self.match_logs = variables['match_logs_channel']
        self.management_role = variables['moderator_role_id']
        self.cancels_channel = variables['cancels_channel']
        self.season_name = variables['season_name']

        #init local variables
        self.ratio = 80
        self.fuzz_rapid = False
        self.auto_mute = True
        self.games_in_progress = []
        self.version = "v1.1"

        #init subclasses
        self.file_handler = FileHandler(self.matches_path, self.database_location)
        self.leaderboard = self.file_handler.leaderboard

        #check for unprocessed matches
        self.logger.info(f"Loading all match files from{self.matches_path}")
        match = self.file_handler.process_unprocessed_matches()
        if match:
            self.logger.info("Leaderboard has been updated")
            self.leaderboard.load_leaderboard()
        else:
            self.logger.info("Leaderboard is already up to date")

        #init bot
        self.token = token
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None, **options)
        self.guild : discord.Guild
        self.add_commands()
        self.add_events()

        self.logger.info(f'Imported match files from {self.matches_path}, and Database location from {self.database_location}')
        self.logger.info(f'Imported Database location from {self.database_location}')
        self.logger.info(f'Guild ID is {self.guild_id}')


    def add_commands(self):

        @self.command()
        async def stats(ctx, arg=None):
            member = None
            player_name = None 
            player_row = None
            thumbnail = ctx.guild.icon.url

            if arg is None:  # If no argument is provided
                member = ctx.author
                discord_id = ctx.author.id
                player_name = ctx.author.display_name
                thumbnail = ctx.author.avatar.url
                player_row = self.leaderboard.get_player_by_discord(discord_id)
                
            elif arg.startswith('<@'):  # If a mention is provided
                try:
                    mentioned_id = int(arg[2:-1])
                    member = ctx.guild.get_member(mentioned_id)
                    player_name = member.display_name
                    thumbnail = member.avatar.url
                    player_row = self.leaderboard.get_player_by_discord(mentioned_id)
                    
                except Exception as e:
                    self.logger.error(e, mentioned_id)
                    await ctx.send(f"Invalid mention provided: {arg}")
                    return
                
            else:  # If a display name is provided
                player_name = arg.strip()
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                            await ctx.channel.send(f"Player {player_name} not found.")
                            return
                discord_id = self.leaderboard.get_player_discord(player_row)
                if discord_id is not None:
                    try:
                        member = await ctx.guild.get_member(int(discord_id))
                        thumbnail = member.avatar.url
                    except Exception as e:
                        thumbnail = ctx.guild.icon.url
                else:
                    thumbnail = ctx.guild.icon.url
                    
            if player_row is None:
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                        await ctx.channel.send(f"Player {player_name} not found.")
                        return

            player_name = player_row['Player Name']
            player_stats = {
                'Rank': self.leaderboard.get_player_ranking(player_row),
                'Player Name': member.mention if member else player_row['Player Name'],
                'MMR': self.leaderboard.get_player_mmr(player_row),
                'Win Rate': str(round(self.leaderboard.get_player_win_rate(player_row), 1)) + "%",
                'Crewmate MMR': self.leaderboard.get_player_crew_mmr(player_row),
                'Crewmate Win Rate': str(round(self.leaderboard.get_player_crew_win_rate(player_row), 1)) + "%",
                'Impostor MMR': self.leaderboard.get_player_imp_mmr(player_row),
                'Impostor Win Rate': str(round(self.leaderboard.get_player_imp_win_rate(player_row), 1)) + "%",
                'Voting Accuracy': str(round(self.leaderboard.get_player_voting_accuracy(player_row)*100, 1)) + "%"
            }

            embed = discord.Embed(title=f'{player_name} Player Stats', color=discord.Color.purple())
            for stat_name, stat_value in player_stats.items():
                embed.add_field(name=stat_name, value=stat_value, inline=False)
            embed.set_thumbnail(url=thumbnail)
            embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden", icon_url=ctx.guild.icon.url)
            player_mmr = self.leaderboard.get_player_mmr(player_row)
            
            bronze_url = "https://i.ibb.co/dc4QjkX/Bronze.jpg"
            silver_url = "https://i.ibb.co/WxtrhwJ/Silver.jpg"
            gold_url = "https://i.ibb.co/jHtsj2h/Gold.jpg"
            diamond_url = "https://i.ibb.co/0s1xM4v/Diamond.jpg"
            sherlock_url = "https://static.wikia.nocookie.net/deathnote/images/8/83/Lawliet-L-Cole.png/revision/latest?cb=20170907105910"
            jack_url = "https://static.wikia.nocookie.net/9a57a21c-6c64-4876-aade-d64dfddaf740/scale-to-width-down/800"

            if player_mmr < 900:
                embed_url = bronze_url
            elif player_mmr < 1050:
                embed_url = silver_url
            elif player_mmr < 1200:
                embed_url = gold_url
            elif player_mmr >= 1200:
                embed_url = diamond_url

            if self.leaderboard.is_player_sherlock(player_row['Player Name']):
                embed.title = "Stats of **Sherlock Crewmate**"
                embed_url = sherlock_url

            elif self.leaderboard.is_player_jack_the_ripper(player_row['Player Name']):
                embed.title = "Stats of **Jack The Ripper Impostor**"
                embed_url = jack_url

            embed.set_image(url=embed_url)
            embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.channel.send(embed=embed)
            self.logger.info(f'Sent stats of {player_row["Player Name"]} to Channel {ctx.channel.name}')


        @self.command()
        async def lb(ctx:Context, *args):
            if args:
                if args[0].startswith('imp'):
                    top = int(args[1]) if len(args) > 1 else 10
                    top_players = self.leaderboard.top_players_by_impostor_mmr(top)  
                    title = f"{args[1] if len(args) > 1 else 10} Top Impostors"
                    color = discord.Color.red()

                elif args[0].startswith('crew'):
                    top = int(args[1]) if len(args) > 1 else 10
                    top_players = self.leaderboard.top_players_by_crewmate_mmr(top)
                    title = f"{args[1] if len(args) > 1 else top} Top Crewmates"
                    color = discord.Color.green()

                else:
                    top = int(args[0])
                    top_players = self.leaderboard.top_players_by_mmr(top)
                    title = f"{args[0]} Top Players Overall"
                    color = discord.Color.blue()
            else:
                top = 10
                top_players = self.leaderboard.top_players_by_mmr(top)
                title = f"{top} Top Players Overall"
                color = discord.Color.blue()


            embed = discord.Embed(title=title, color=color)
            leaderboard_text = ""
            for index, row in top_players.iterrows():
                rank = top_emojis[index] if index < len(top_emojis) else f"**{index+1}.**"
                leaderboard_text += f"{rank} **{row['Player Name']}**\n"
                leaderboard_text += f"MMR: {row.iloc[1]}\n"

            embed.add_field(name="Leaderboard", value=leaderboard_text)
            embed.set_thumbnail(url=self.guild.icon.url)
            embed.set_footer(text=f"{self.season_name} Data - Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent stats of {top} {title} to Channel {ctx.channel.name}')


        @self.command()
        async def link(ctx:Context, *args):

            if len(args) < 1:
                await ctx.send("Please provide a player name.")
                return
            player_name = args[0]
            discord_mention = None
            if len(args) > 1 and args[1].startswith('<@'):
                discord_mention = args[1]

            if discord_mention:
                try:
                    discord_id = int(discord_mention[2:-1])
                except ValueError:
                    await ctx.send("Invalid mention provided.")
                    return
            else:
                discord_id = ctx.author.id
            player_row = self.leaderboard.get_player_row(player_name)
            player_discord = self.leaderboard.get_player_discord(player_row)
            if player_discord is not None:
                await ctx.send(f"{player_name} is already linked to <@{int(player_discord)}>.")
                return

            if player_row is None:
                await ctx.send(f"Player {player_name} not found in the database.")
                return

            if self.leaderboard.add_player_discord(player_name, discord_id):
                await ctx.send(f"Linked {player_name} to <@{discord_id}> in the leaderboard.")
            else:
                await ctx.send("Failed to link the player. Please try again later.")


        @self.command()
        async def unlink(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.channel.send("You don't have permission to unlink players.")
                return

            if arg.startswith('<@'): # unlinking a mention
                discord_id = int(arg[2:-1])
                player_row = self.leaderboard.get_player_by_discord(discord_id)
                if player_row is not None:
                    self.leaderboard.delete_player_discord(player_row['Player Name'])
                    await ctx.send(f"Unlinked {player_row['Player Name']} from <@{discord_id}>")
                    return
                await ctx.send(f"<@{discord_id}> is not linked to any account")
            
            else: # unlinking a player name
                player_name = arg
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is not None:
                    discord_id = self.leaderboard.get_player_discord(player_row)
                    if discord_id is not None:
                        self.leaderboard.delete_player_discord(player_row['Player Name'])
                        await ctx.send(f"Unlinked {player_row['Player Name']} from <@{discord_id}>")
                    else:
                        await ctx.send(f"Player {player_name} is not linked to any account")
                    return
                await ctx.send(f"Player {player_name} not found in the database.")
        

        @self.command()
        async def change_to_cancel(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to cancel matches.")
                return

            if arg is None or not arg.isnumeric():
                await ctx.channel.send("Please specify a match ID.")
                return
            try:
                match_id = int(arg)
            except ValueError:
                await ctx.channel.send("Invalid match ID. Please provide a valid match ID.")
                return

            if self.file_handler.match_info_by_id(match_id) is not None:
                match = self.file_handler.change_result_to_cancelled(match_id)
                if match:
                    mentions = ""
                    for player in match.players.players:
                        try:
                            member = self.guild.get_member(int(player.discord))
                            mentions += f"{member.mention}"
                        except:
                            self.logger.warning(f"Player {player.name} has a wrong discord ID {player.discord}")

                    await ctx.channel.send(f"Cancelled Match: {match_id} {mentions}")
                    await self.get_channel(self.cancels_channel).send(f"Member {ctx.author.display_name} Cancelled Match: {match_id}")
                else:
                    await ctx.channel.send(f"Match: {match_id} is already a Cancel")
            else:
                await ctx.channel.send(f"Can't find Match: {match_id}")


        @self.command()
        async def change_to_crew_win(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.")
                return

            if arg is None or not arg.isnumeric():
                await ctx.channel.send("Please specify a match ID.")
                return

            try:
                match_id = int(arg)
            except ValueError:
                await ctx.send("Invalid match ID. Please provide a valid match ID.")
                return

            if self.file_handler.match_info_by_id(match_id) is not None:
                match = self.file_handler.change_result_to_crew_win(match_id)
                if match:
                    mentions = ""
                    for player in match.players.players:
                        try:
                            member = self.guild.get_member(int(player.discord))
                            mentions += f"{member.mention}"
                        except:
                            self.logger.warning(f"Player {player.name} has a wrong discord ID {player.discord}")

                    await ctx.send(f"Changed Match: {match_id} to a Crewmates Win! {mentions}")
                    await self.get_channel(self.cancels_channel).send(f"Member {ctx.author.display_name} Changed Match: {match_id} to a Crewmates Win!")
                else: 
                    await ctx.channel.send(f"Match: {match_id} is already a Crewmates Win")
            else:
                await ctx.send(f"Can't find Match: {match_id}")


        @self.command()
        async def change_to_imp_win(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.")
                return

            if arg is None or not arg.isnumeric():
                await ctx.send("Please specify a match ID.")
                return
            try:
                match_id = int(arg)
            except ValueError:
                await ctx.send("Invalid match ID. Please provide a valid match ID.")
                return
            
            if self.file_handler.match_info_by_id(match_id):
                match = self.file_handler.change_result_to_imp_win(match_id)
                if match:
                    mentions = ""
                    for player in match.players.players:
                        try:
                            member = self.guild.get_member(int(player.discord))
                            mentions += f"{member.mention}"
                        except:
                            self.logger.warning(f"Player {player.name} has a wrong discord ID {player.discord}")
                    await ctx.send(f"Match: {match_id} changed to an Impostors Win!")
                    await self.get_channel(self.cancels_channel).send(f"Member {ctx.author.display_name} Changed Match: {match_id} to an Impostors Win!")
                else: 
                    await ctx.channel.send(f"Match: {match_id} is already an Impostors Win")
            else:
                await ctx.send(f"Can't find Match: {match_id}")


        @self.command()
        async def m(ctx:Context):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.")
                return
            member = ctx.author
            voice_state = member.voice  # Get the voice state of the member
            if voice_state is not None and voice_state.channel is not None:
                channel = voice_state.channel
                tasks = []
                for vc_member in channel.members:
                    if vc_member != member:
                        tasks.append(vc_member.edit(mute=True, deafen=False))
                await asyncio.gather(*tasks)


        @self.command()
        async def um(ctx:Context):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.send("You don't have permission to use this command.")
                return
            member = ctx.author
            voice_state = member.voice  # Get the voice state of the member
            if voice_state is not None and voice_state.channel is not None:
                channel = voice_state.channel
                tasks = []
                for vc_member in channel.members:
                    tasks.append(vc_member.edit(mute=False, deafen=False))
                await asyncio.gather(*tasks)


        @self.command()
        async def automute_off(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.channel.send("You don't have permission to turn off automute.")
                return
            await ctx.channel.send("Automute is turned OFF from the server side!")
            self.logger.info("Automute has been turned OFF")
            self
            self.auto_mute = False
        

        @self.command()
        async def automute_on(ctx:Context, arg=None):
            if self.management_role not in [role.id for role in ctx.author.roles]:
                await ctx.channel.send("You don't have permission to turn on automute.")
                return
            await ctx.channel.send("Automute is turned ON from the server side!")
            self.logger.info("Automute has been turned ON")
            self.auto_mute = True


        @self.command()
        async def help(ctx:Context):
            embed = discord.Embed(title="Among Us Bot Commands", color=discord.Color.gold())
            embed.add_field(name="!stats [none/player/@mention]", value="Display stats of a player.", inline=False)
            embed.add_field(name="!lb [none/number]", value="Display the leaderboard for top Players.", inline=False)
            embed.add_field(name="!lb imp [none/number]", value="Display the leaderboard for top Impostors.", inline=False)
            embed.add_field(name="!lb crew [none/number]", value="Display the leaderboardfor top Crewmates.", inline=False)
            embed.add_field(name="!match_info [match_id]", value="Display match info from the given ID", inline=False)
            embed.add_field(name="!game_info", value="Explains how the bot calculates MMR", inline=False)
            embed.add_field(name="!mmr_change [player/@mention] [value]", value="add or subtract mmr from the player", inline=False)
            embed.add_field(name="!automute_on", value="Turn on server-side automute.", inline=False)
            embed.add_field(name="!automute_off", value="Turn off server-side automute.", inline=False)
            embed.add_field(name="!link [player] [none/@mention]", value="Link a Discord user to a player name.", inline=False)
            embed.add_field(name="!unlink [player/@mention]", value="Unlink a Discord user from a player name.", inline=False)
            embed.add_field(name="!change_to_cancel [match_id]", value="Change match result to canceled.", inline=False)
            embed.add_field(name="!change_to_crew_win [match_id]", value="Change match result to Crewmates win.", inline=False)
            embed.add_field(name="!change_to_imp_win [match_id]", value="Change match result to Impostors win.", inline=False)
            embed.add_field(name="!m", value="Mute everyone in your VC.", inline=False)
            embed.add_field(name="!um", value="Unmute everyone in your VC.", inline=False)
            embed.set_footer(text=f"Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent help command to Channel {ctx.channel}')


        @self.command()
        async def game_info(ctx:Context):
            embed = discord.Embed(title="Among Us Game Info", color=discord.Color.blurple())
            embed.add_field(name="Impostors", value="""
        If the impostor is **ejected** on **8, 9, 10** __THEN__ they will **lose 15%** performance.
        The other impostor who is a **solo** impostor will **gain 15%** performance.
        If an impostor got a crewmate __voted out__ in a meeting they will **gain 5%** for every crewmate voted out.
        For every kill you do as a **solo** impostor, you will **gain 5%** performance.
        If you win as a solo Impostor, you will **gain 20%** performance.
        """, inline=False)
            embed.add_field(name="Crewmates", value="""
        If the crewmate voted wrong on **__crit__(3, 4) players alive** or **(5, 6, 7) players alive with 2 imps** __THEN__ they will **LOSE 30%** performance.
        If the crewmate votes out an impostor they will **gain 20%** performance.
        If the crewmate votes correct on crit but loses then they will **gain 20%** performance.
        """, inline=False)
            embed.add_field(name="Winning Percentage", value="The percentage of winning is calculated by a linear regression machine learning module trained on pre-season data.",inline=False)
            embed.add_field(name="MMR Gained", value="Your MMR gain will be your team's winning percentage * your performance * K(32)",inline=False)
            embed.set_footer(text=f"Bot Programmed by Aiden | Version: {self.version}", icon_url=self.user.avatar.url)
            await ctx.send(embed=embed)
            self.logger.info(f'Sent game info to Channel {ctx.channel}')


        @self.command()
        async def match_info(ctx:Context, arg=None):
            if arg == None: 
                return
            match_file = self.file_handler.find_matchfile_by_id(int(arg))
            match = self.file_handler.match_from_file(match_file)
            if not (match.result == "Canceled" or match.result == "Unknown"):
                self.file_handler.calculate_mmr_gain_loss(match)
            await ctx.send(f"`{match.match_details()}`")
            self.logger.info(f"{ctx.author.display_name} Recieved Match {int(arg)} Info")


        @self.command()
        async def mmr_change(ctx:Context, *args):
            if len(args) < 2:  # If no argument is provided or only one
                await ctx.send("Please input a player name or mention with the MMR change amount")
                
            elif args[0].startswith('<@'):  # If a mention is provided
                try:
                    mentioned_id = int(args[0][2:-1])
                    member = ctx.guild.get_member(mentioned_id)
                    player_name = member.display_name
                    player_row = self.leaderboard.get_player_by_discord(mentioned_id)
                    
                except Exception as e:
                    self.logger.error(e, mentioned_id)
                    await ctx.send(f"Invalid mention provided: {args[0]}")
                    return
                
            else:  # If a display name is provided
                player_name = args[0]
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                            await ctx.channel.send(f"Player {player_name} not found.")
                            return
                    
            if player_row is None:
                player_row = self.leaderboard.get_player_row(player_name)
                if player_row is None:
                    player_row = self.leaderboard.get_player_row_lookslike(player_name)
                    if player_row is None:
                        await ctx.channel.send(f"Player {player_name} not found.")
                        return
            if str(args[1]).isnumeric():
                self.file_handler.leaderboard.mmr_change(player_row, args[1])
                if int(args[1])>0:
                    await ctx.channel.send(f"Added {args[1]} MMR to Player {player_name}")
                else:
                    await ctx.channel.send(f"Subtracted {args[1]} MMR from Player {player_name}")
            else:
                await ctx.send("Please input a correct MMR change value")
            

        # @self.command()
        # async def test(ctx):
        #     json_end = '{"EventName":"GameEnd","MatchID":1780,"GameCode":"ZBQSDY","Players":["Aiden","zurg","real matt","Mantis","Sai","MaxKayn","Irish","Trav","xer","Nutty"],"PlayerColors":[6,14,0,15,12,10,7,2,4,9],"DeadPlayers":["Aiden","zurg","Mantis","Sai","MaxKayn","Irish","Trav","xer"],"Impostors":["zurg","real matt"],"Crewmates":["Aiden","Mantis","Sai","MaxKayn","Irish","Trav","xer","Nutty"],"Result":3}'
        #     json_data = json.loads(json_end)
        #     match = self.file_handler.match_from_file("OXwRTucN96BuY5z3_match.json")
        #     for player in match.players.players:
        #         player.tasks = 0
        #     self.file_handler.calculate_mmr_gain_loss(match)
        #     # embed = self.end_game_embed(json_data, match)
        #     votes_embed = discord.Embed(title="Match ID: (matchID) - Ejection Votes", description="")
        #     events_df = pd.read_json(os.path.join(self.matches_path, match.event_file_name), typ='series')
        #     events_embed = ""
        #     for event in events_df:
        #         event_type = event.get('Event')

        #         if event_type == "Task":
        #             player = match.players.get_player_by_name(event.get('Name'))
        #             player.finished_task()
        #             if player.tasks == 10:
        #                 color_emoji = default_color_emojis.get(player.color, "?")
        #                 events_embed += f"{color_emoji} Finished Taskes {'Alive' if player.alive else 'Dead'}\n"

        #         elif event_type == "PlayerVote":
        #             player = match.players.get_player_by_name(event.get('Player'))
        #             target = match.players.get_player_by_name(event.get('Target'))
        #             player_emoji = default_color_emojis.get(player.color, "?")
                    
        #             if target == None:
        #                 events_embed += f"{player_emoji} Skipped.\n"
        #                 continue

        #             target_emoji = default_color_emojis.get(target.color, "?")
        #             if match.players.is_player_impostor(target.name):
        #                 events_embed += f"{player_emoji} Voted {target_emoji}(**Imp**).\n"
        #             else:
        #                 events_embed += f"{player_emoji} Voted {target_emoji}.\n"

        #         elif event_type == "Death":
        #             player = match.players.get_player_by_name(event.get('Name'))
        #             killer = match.players.get_player_by_name(event.get('Killer'))
        #             player_emoji = default_color_emojis.get(player.color, "?")
        #             killer_emoji = default_color_emojis.get(killer.color, "?")
        #             events_embed += f"{killer_emoji} Killed {player_emoji}.\n"

        #         elif event_type == "BodyReport":
        #             player = match.players.get_player_by_name(event.get('Player'))
        #             dead_player = match.players.get_player_by_name(event.get('DeadPlayer'))
        #             if player:
        #                 player_emoji = default_color_emojis.get(player.color, "?")
        #             else:
        #                 player_emoji = None
        #             if dead_player:
        #                 dead_emoji = default_color_emojis.get(dead_player.color, "?")
        #             else:
        #                 dead_emoji = None
        #             events_embed += f"{player_emoji} Reported {dead_emoji} Body.\n"
        #             events_embed += f"----------------------\n"

        #         elif event_type == "MeetingStart":
        #             player = match.players.get_player_by_name(event.get('Player'))
        #             player_emoji = default_color_emojis.get(player.color, "?")
        #             events_embed += f"{player_emoji} Called a Meeting.\n"
        #             events_embed += f"----------------------\n"

        #         elif event_type == "Exiled":
        #             ejected_player = match.players.get_player_by_name(event.get('Player'))
        #             ejected_emoji = default_color_emojis.get(ejected_player.color, "?")
        #             ejected_imp = match.players.is_player_impostor(ejected_player.name)
        #             if ejected_imp:
        #                 events_embed += f"{ejected_emoji} (**Imp**) was Ejected.\n"
        #             else:
        #                 events_embed += f"{ejected_emoji} was Ejected.\n"
        #                 events_embed += f"----------------------\n"


        #         elif event_type == "MeetingEnd":
        #             if (event.get("Result") == "Skipped"):
        #                 events_embed += f"No one was Ejected.\n"
        #                 events_embed += f"----------------------\n"
        #             votes_embed.add_field(name = "", value=events_embed, inline=True)
        #             print(events_embed)
        #             events_embed = ""

            



        #     # await ctx.send(embed=embed)
        #     await ctx.send(embed=votes_embed)

        
    def add_events(self):
        @self.event
        async def on_ready():
            self.logger.info(f'{self.user} has connected to Discord!')
            self.guild = self.get_guild(self.guild_id)
            await self.get_members_in_channel()
            await self.update_leaderboard_discords()
        

        @self.event
        async def on_voice_state_update(member, before, after):
            voice_channel_ids = [channel['voice_channel_id'] for channel in self.channels.values()]
            if (before.channel != after.channel) and \
                    ((before.channel and before.channel.id in voice_channel_ids) or (after.channel and after.channel.id in voice_channel_ids)):
                for channel in self.channels.values():
                    if before.channel and before.channel.id == channel['voice_channel_id']:
                        if member in channel['members']:
                            channel['members'].remove(member)
                            self.logger.info(f'{member.display_name} left {before.channel.name}')
                    elif after.channel and after.channel.id == channel['voice_channel_id']:
                        if member not in channel['members']:
                            channel['members'].append(member)
                            self.logger.info(f'{member.display_name} joined {after.channel.name}')
    
    
    async def get_members_in_channel(self): #updates all the members that are in the ranked channels on start
        for channel in self.channels.values():
            voice_channel = self.get_channel(channel['voice_channel_id'])
            if voice_channel:
                members = voice_channel.members
                channel['members'] = [member for member in members]


    async def update_leaderboard_discords(self):
        self.leaderboard.leaderboard['Player Discord'] = None
        self.leaderboard.save_leaderboard()
    # Remove Discord IDs that are not in the guild
        players_to_remove = []
        for index, player_row in self.leaderboard.leaderboard.iterrows():
            player_name = player_row['Player Name']
            discord_id = player_row['Player Discord']
            if pd.notnull(discord_id):
                try:
                    discord_id = int(discord_id)
                    member = self.guild.get_member(discord_id)
                    if member is None:
                        players_to_remove.append(player_name)
                except Exception as e:
                    self.logger.debug(f"Encountered exception {e}, {type(discord_id)}, {discord_id}")

        for player_name in players_to_remove:
            self.logger.debug(f"Removing player {player_name} discord {discord_id} (wrong discord)")
            self.leaderboard.delete_player_discord(player_name)

        if players_to_remove:
            self.logger.info(f"Removed Discord IDs for players not found in the guild: {', '.join(players_to_remove)}")
        else:
            self.logger.info("All Discord IDs in the leaderboard are valid.")

        for member in self.guild.members:
            player_name = member.display_name
            player_row = self.leaderboard.get_player_row(player_name)
            if player_row is not None:  # Check if Discord ID is empty
                if self.leaderboard.get_player_discord(player_row) is None:
                    self.leaderboard.add_player_discord(player_name, member.id)
                    self.logger.debug(f"Added {member.display_name} to {player_name} in leaderboard")

        players_with_empty_discord = self.leaderboard.players_with_empty_discord()

        for _, player_row in players_with_empty_discord.iterrows():
            player_name = player_row['Player Name']
            best_match = None
            best_score = 0
            for member in self.guild.members:
                member_display_name = member.display_name.lower().replace(" ","")
                player_name_normalized = player_name.lower().replace(" ","")
                match_score = fuzz.token_sort_ratio(player_name_normalized, member_display_name)
                if match_score > best_score and match_score >= 80:
                    best_match = member
                    best_score = match_score
            if best_match:
                discord_id = best_match.id
                self.leaderboard.add_player_discord(player_name, discord_id)
                self.logger.debug(f"Added {best_match.display_name} to {player_name} in leaderboard (#2)")
        self.logger.warning(self.leaderboard.players_with_empty_discord()['Player Name'])
        self.leaderboard.save_leaderboard()


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
            color_emoji = default_color_emojis.get(player_color, ":question:")
            value = color_emoji
            try:
                player_discord = self.guild.get_member(int(player_discord_id))
                value += f" {player_discord.mention}"
            except:
                value += f" @{player_name}"
            player_mmr = self.leaderboard.get_player_mmr(player_row)
            value += "\nMMR: " + f" {player_mmr if player_mmr else 'New Player'}"
            embed.add_field(name=player_name, value=value, inline=True)
        
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        embed.set_image(url='https://www.essentiallysports.com/stories/the-best-among-us-mods-news-esports-sheriff-doctor-minecraft/assets/24.jpeg')
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match Started: {current_time} - Bot Programmed by Aiden", icon_url=self.guild.icon.url)
        return embed


    def end_game_embed(self, json_data, match: Match) -> discord.Embed:

        player_colors = json_data.get("PlayerColors", [])
        game_code = json_data["GameCode"]
        match.players.set_player_colors_in_match(player_colors)
        self.logger.info(f'Creating an embed for game End MatchId={match.id}')


        if match.result.lower() == "impostors win":
            embed_color = discord.Color.red()
        elif match.result.lower() == "canceled":
            embed_color = discord.Color.orange()
        else:
            embed_color = discord.Color.green()
        embed = discord.Embed(title=f"Ranked Match Ended - {match.result}", 
                      description=f"Match ID: {match.id} Code: {game_code}\nPlayers:", color=embed_color)
        
        members_discord = [(member.display_name.lower().strip(), member) for member in self.guild.members]

        for player in match.players.players:
            if player.discord == 0: 
                best_match = None
                best_match, score = process.extractOne(player.name.lower().strip(), [member_name for member_name, _ in members_discord])
                if score > self.ratio:  # Adjust the threshold score as needed
                    player.discord = next(member_id for member_name, member_id in members_discord if member_name == best_match)

        for player in match.players.get_players_by_team("impostor"):
            self.logger.debug(f"processing impostor:{player.name}")
            value = "" 
            color_emoji = default_color_emojis.get(player.color, ":question:")
            
            value = color_emoji
            try:
                player_in_discord = self.guild.get_member(int(player.discord))
                value += f" {player_in_discord.mention}"
            except:
                self.logger.error(f"Can't find discord for player {player.name}, please link")
            value += "\nMMR: " + f" {round(player.current_mmr, 1) if player.current_mmr else 'New Player'}"
            value += f"\nImp MMR: {'+' if player.impostor_mmr_gain >= 0 else ''}{round(player.impostor_mmr_gain, 1)}"
            embed.add_field(name=f"{player.name} __**(Imp)**__", value=value, inline=True)

        embed.add_field(name=f"Imp Win rate: {round(match.players.impostor_win_rate*100,2)}%\nCrew Win Rate: {round(match.players.crewmate_win_rate*100,2)}%", value=" ", inline=True) 

        for player in match.players.get_players_by_team("crewmate"):
            value = "" 
            self.logger.debug(f"processing crewmate:{player.name}")
            color_emoji = default_color_emojis.get(player.color, ":question:")
            value = color_emoji
            try:
                player_in_discord = self.guild.get_member(int(player.discord))
                value += f" {player_in_discord.mention}"
            except:
                self.logger.error(f"Can't find discord for player {player.name}, please link")
            value += "\nMMR: " + f" {round(player.current_mmr, 1) if player.current_mmr else 'New Player'}"
            value += f"\nCrew MMR: {'+' if player.crewmate_mmr_gain >= 0 else ''}{round(player.crewmate_mmr_gain, 1)}"
            value += f"\nTasks: {player.tasks}/10"
            embed.add_field(name=f"{player.name}", value=value, inline=True)

        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        if match.result == "Impostors Win":
            # embed.set_image(url="https://i.redd.it/gn3u8lc2exx51.jpg")
            embed.set_image(url="https://i.ibb.co/BzGQ8MM/maxresdefault.jpg")
        elif match.result in ["Crewmates Win", "HumansByVote"]:
            embed.set_image(url="https://i.ytimg.com/vi/m4xtGCx8Tao/maxresdefault.jpg")
        else:
            embed.set_image(url="https://i.ytimg.com/vi/hLHcNeIkIg8/maxresdefault.jpg")
            
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match Started: {current_time} - Bot Programmed by Aiden", icon_url=self.guild.icon.url)
        return embed  


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
                    self.leaderboard.save_leaderboard()

                if self.leaderboard.get_player_discord(player_row) is None:
                    self.logger.info(f"Player {player_name} has no discord in the leaderboard, adding discord {member.id}")
                    self.leaderboard.add_player_discord(player_name, member.id)
                    self.leaderboard.save_leaderboard()
            else:
                self.logger.error(f"Can't find a match a player for member {member.display_name}")


    async def handle_game_start(self, json_data):
        match_id = json_data.get("MatchID", "")
        game_code = json_data.get("GameCode", "")
        self.games_in_progress.append({"GameCode":game_code, "MatchID": match_id, "GameData": json_data})
        game_channel = self.find_most_matched_channel(json_data)
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
        else:
            self.logger.error(f"Could not find a matching game channel to the game not found.")


    async def game_start_automute(self, game_channel):
        voice_channel_id = game_channel['voice_channel_id']
        voice_channel = self.get_channel(voice_channel_id)
        if voice_channel is not None:
            tasks = []
            for member in voice_channel.members:
                tasks.append(member.edit(mute=True, deafen=True))
                self.logger.info(f"Deafened and Muted {member.display_name}")
            try:
                await asyncio.gather(*tasks)  # undeafen all players concurrently
            except:
                self.logger.warning("Some players left the VC on Game Start")
        else:
            self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")


    async def handle_meeting_start(self, json_data):
        players = set(json_data.get("Players", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        alive_players = players - dead_players
        dead_players_normalized = {player.lower().replace(" ", "") for player in dead_players}
        alive_players_normalized = {player.lower().replace(" ", "") for player in alive_players}
        tasks = []
            
        game_channel = self.find_most_matched_channel(json_data)
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
                        self.logger.info(f"undeafened and muted {member.display_name}")
                        match_found = True 
                        continue

                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"undeafened and unmuted {member.display_name}")
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
                        self.logger.info(f"deafened and unmuted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"undeafened and unmuted {member.display_name}")
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
                        self.logger.info(f"undeafened and muted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=False, deafen=False))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"undeafened and unmuted {member.display_name}")
                        match_found = True

                    if not match_found:
                        self.logger.error(f"Could not perform automute on {member.display_name}")
                        await text_channel.send(f"Could not perform automute on{member.display_name}")
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
        alive_players = players - dead_players
        dead_players_normalized = {player.lower().replace(" ", "") for player in dead_players}
        alive_players_normalized = {player.lower().replace(" ", "") for player in alive_players}
        game_channel = self.find_most_matched_channel(json_data)
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
                        self.logger.info(f"undeafened and unmuted {member.display_name}")
                        tasks.append(member.edit(mute=False, deafen=False))
                        dead_players_normalized.remove(best_match[0])
                        match_found = True

                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=1.0)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"deafened and muted {member.display_name}")
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
                        self.logger.info(f"undeafened and unmuted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.9)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"deafened and muted {member.display_name}")
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
                        self.logger.info(f"undeafened and muted {member.display_name}")
                        match_found = True
                    
                    best_match = difflib.get_close_matches(display_name, alive_players_normalized, cutoff=0.75)
                    if len(best_match) == 1:
                        tasks.append(member.edit(mute=True, deafen=True))
                        alive_players_normalized.remove(best_match[0])
                        self.logger.info(f"deafened and muted {member.display_name}")
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


    async def handle_game_end(self, json_data):
        match_id = json_data.get("MatchID", "")
        game_code = json_data.get("GameCode", "")
        for game in self.games_in_progress:
            if game.get("GameCode") == game_code:
                match_id = game.get("MatchID")
                self.games_in_progress.remove(game)

        game_channel = self.find_most_matched_channel(json_data)
        voice_channel_id = game_channel['voice_channel_id']
        text_channel_id = game_channel['text_channel_id']
        voice_channel = self.get_channel(voice_channel_id)
        if self.auto_mute:
            await self.game_end_automute(voice_channel, voice_channel_id)
        await asyncio.sleep(5)

        last_match = self.file_handler.process_match_by_id(match_id)
        embed = self.end_game_embed(json_data, last_match)
        await self.get_channel(text_channel_id).send(embed=embed)
        await self.get_channel(self.match_logs).send(embed=embed)
        game_channel['members_in_match'] = []


    async def handle_client(self, reader, writer):
        data = await reader.read(1024)
        message = data.decode('utf-8')
        self.logger.debug(f"Received: {message}") 

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
            self.logger.error("Error processing event:", e, message)
    
    
    async def start_server(self):
        server = await asyncio.start_server(self.handle_client, 'localhost', 5000)
        async with server:
            self.logger.info("Socket server is listening on localhost:5000...")
            await server.serve_forever()


    async def start_bot(self):
        await asyncio.gather(
            self.start_server(),
            super().start(self.token)
        )


# class VotesView(discord.ui.View):
#     def __init__(self, *, timeout=180, embed=None):
#         super().__init__(timeout=timeout)
#         self.embed = embed

#     @discord.ui.button(label="Show Votes", style=ButtonStyle.gray)
#     async def gray_button(self, button: discord.ui.Button, interaction: discord.Interaction):
#         if interaction.data.get("custom_id") == "gray_button":  # Check if the custom ID matches the button ID
#             if button.label == "Show Votes":  # If the button label is "Show Votes"
#                 # Update the button label to "Hide Votes"
#                 button.label = "Hide Votes"
#                 button.style = ButtonStyle.red  # Change button style to red to indicate hiding
#                 await interaction.response.edit_message(content="This is the votes?")
#                 await interaction.followup.send(embed=self.embed, ephemeral=True)
#             else:  # If the button label is "Hide Votes"
#                 # Update the button label to "Show Votes"
#                 button.label = "Show Votes"
#                 button.style = ButtonStyle.gray  # Change button style back to gray
#                 # Delete the message containing the votes
#                 await interaction.followup.delete()


if __name__ == "__main__":
    token = "XXXXXXX"

    ranked_channels = {
        'ranked1': {'voice_channel_id': 1200119601627926629, 'text_channel_id': 1200120470616428545, 'members': [], 'members_in_match': [], 'lobby_code': ""},
        'ranked2': {'voice_channel_id': 1200119662680219658, 'text_channel_id': 1200120538341834782, 'members': [], 'members_in_match': [], 'lobby_code': ""},
        'ranked3': {'voice_channel_id': 1200119714920276168, 'text_channel_id': 1200120699264704533, 'members': [], 'members_in_match': [], 'lobby_code': ""},
        'ranked4': {'voice_channel_id': 1217501389366890576, 'text_channel_id': 1217951844156833854, 'members': [], 'members_in_match': [], 'lobby_code': ""}
    }
    variables = {
        'ranked_channels' : ranked_channels,
        'guild_id' : 1116951598422315048,
        'match_logs_channel' : 1220864275581767681,
        'moderator_role_id' : 1199319511011180575, 
        'cancels_channel' : 1199323422631657512,
        'matches_path' : "~/plugins/MatchLogs/Preseason/",
        'database_location' : "leaderboard_full.csv",
        'season_name' : "Pre-Season"
    }
    bot = DiscordBot(token=token, variables=variables)

    # test_token = "XXXXXXXX"
    # test_channels = {
    # 'ranked1': {'voice_channel_id': 1229151012221354076, 'text_channel_id': 1229150964213219430, 'members': [], 'members_in_match': []}
    # }
    # test_variables = {
    #     'ranked_channels' : test_channels,
    #     'guild_id' : 1229122991330426990,
    #     'match_logs_channel' : 1229808964137648239,
    #     'moderator_role_id' : 1229221887918346321, 
    #     'cancels_channel' : 1229808964137648239,
    #     'matches_path' : "~/Resistance/test_match/",
    #     'database_location' : "leaderboard_full.csv",
    #     'season_name' : "Pre-Season"
    # }
    # bot = DiscordBot(token=test_token, variables=test_variables)


    asyncio.run(bot.start_bot())
