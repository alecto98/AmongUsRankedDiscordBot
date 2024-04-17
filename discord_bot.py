import discord
import asyncio
import json
from datetime import datetime
import pytz
from file_processing import FileHandler
import time 
from match_class import Match
import logging
from rapidfuzz import fuzz

import time

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

class DiscordBot:
    def __init__(self, token, channels, matches_path, database_location, guild_id):
        logging.basicConfig(level=logging.INFO, encoding='utf-8', format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler("DiscordBot.log", encoding='utf-8'),logging.StreamHandler()])
        self.logger = logging.getLogger(__name__)
        self.matches_path = matches_path
        self.database_location = database_location
        self.file_handler = FileHandler(self.matches_path, self.database_location)
        self.leaderboard = self.file_handler.leaderboard
        self.token = token
        self.channels = channels
        self.guild_id = guild_id
        self.match_logs = 1220864275581767681
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        self.client = discord.Client(intents=intents)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.client.event(self.on_voice_state_update)
        self.logger.info(f'Imported match files from {self.matches_path}, and Database location from {database_location}')
        self.logger.info(f'Imported Database location from {self.database_location}')
        self.logger.info(f'Guild ID is {self.guild_id}')
        self.ratio = 85

    async def on_ready(self):
        self.logger.info(f'{self.client.user} has connected to Discord!')
        self.guild = self.client.get_guild(self.guild_id)
        await self.update_channel_members()

    async def on_message(self, message):
        if message.author == self.client.user:
            return

        if message.content.startswith('!stats'):
            if message.content == "!stats":
                player_name = message.author.display_name
                thumbnail = message.author.avatar.url
            elif message.content.startswith('!stats '):
                player_name = message.content[7:]
                try:
                    await self.guild.fetch_member(player_name)
                    thumbnail = self.guild.get_member_named(player_name).avatar.url
                except:
                    # await message.channel.send(f"I couldn't find the player in {self.guild}")
                    thumbnail = self.guild.icon.url
                    self.logger.error(f"Cant find {player_name} as a nickname")
                    
            if self.leaderboard.is_player_in_leaderboard(player_name):
                player_stats = {
                    'Rank': self.leaderboard.get_player_ranking(player_name),
                    'Player Name': player_name,
                    'MMR': self.leaderboard.get_player_elo(player_name),
                    'Win Rate': str(round(self.leaderboard.get_player_win_rate(player_name),1))+"%",
                    'Crewmate MMR': self.leaderboard.get_player_crew_elo(player_name),
                    'Crewmate Win Rate': str(round(self.leaderboard.get_player_crew_win_rate(player_name),1))+"%",
                    'Impostor MMR': self.leaderboard.get_player_imp_elo(player_name),
                    'Impostor Win Rate': str(round(self.leaderboard.get_player_imp_win_rate(player_name),1))+"%"
                }
            else:
                player_stats = {
                    'Rank': "New Player",
                    'Player Name': f"**{player_name}**",
                    'MMR': None,
                    'Win Rate': "None%",
                    'Crewmate MMR': None,
                    'Crewmate Win Rate': "None%",
                    'Impostor MMR': None,
                    'Impostor Win Rate': "None%"}

            embed = discord.Embed(title='Player Stats', color=discord.Color.blue())
            for stat_name, stat_value in player_stats.items():
                embed.add_field(name=stat_name, value=stat_value, inline=False)
            embed.set_thumbnail(url=thumbnail)
            embed.set_footer(text=f"Ranking in the Pre-Season        devs: Aiden, Xer", icon_url=self.guild.icon.url)

            if self.leaderboard.is_player_sherlock(player_name):
                embed.title = "Stats of **Sherlock Crewmate**"
                embed.set_image(url="https://static.wikia.nocookie.net/deathnote/images/8/83/Lawliet-L-Cole.png/revision/latest?cb=20170907105910")
            if self.leaderboard.is_player_jack_the_ripper(player_name):
                embed.title = "Stats of **Jack The Ripper Impostor**"
                embed.set_image(url="https://static.wikia.nocookie.net/9a57a21c-6c64-4876-aade-d64dfddaf740/scale-to-width-down/800")    
            await message.channel.send(embed=embed)
            self.logger.info(f'Sent stats of {player_name} to Channel {message.channel.name}')

        if message.content.startswith('!lb'):
            thumbnail = message.author.avatar.url
            if message.content.lower().startswith('!lb imp'):
                try:
                    top = int(message.content[7:])
                except:
                    top = 10
                top_players = self.leaderboard.top_players_by_impostor_mmr(top)
                title = str(top)+" Top Impostors"
                color = discord.Color.red()

            elif message.content.lower().startswith('!lb crew'):
                try:
                    top = int(message.content[8:])
                except:
                    top = 10
                top_players = self.leaderboard.top_players_by_crewmate_mmr(top)
                title = str(top)+" Top Crewmates"
                color = discord.Color.green()

            elif message.content.lower().startswith("!lb"):
                try:
                    top = int(message.content[4:])
                except:
                    top = 10
                top_players = self.leaderboard.top_players_by_mmr(top)
                title = str(top)+" Top Players Overall"
                color = discord.Color.blue()
        
            embed = discord.Embed(title=title, color=color)
            for index, row in top_players.iterrows():
                embed.add_field(name=f"{index + 1}: {row['Player Name']}", value=row.iloc[1], inline=False)
            embed.set_thumbnail(url=self.guild.icon.url)
            embed.set_footer(text=f"Ranking in the Pre-Season        devs: Aiden, Xer", icon_url=self.guild.icon.url)
            await message.channel.send(embed=embed)
            self.logger.info(f'Sent stats of {top, title} to Channel {message.channel.name}')
            # await self.client.process_commands(message)
        if message.content.startswith("!update"):
            match = self.file_handler.process_unprocessed_matches()
            if match is not None:
                await message.channel.send(f"The Leaderboard has been updated!")


    async def update_channel_members(self):
        for channel in self.channels.values():
            voice_channel = self.client.get_channel(channel['voice_channel_id'])
            if voice_channel:
                members = voice_channel.members
                channel['members'] = [member for member in members]

    async def on_voice_state_update(self, member, before, after):
        voice_channel_ids = [channel['voice_channel_id'] for channel in self.channels.values()]
        if (before.channel != after.channel) and \
                ((before.channel and before.channel.id in voice_channel_ids) or (after.channel and after.channel.id in voice_channel_ids)):
            for channel in self.channels.values():
                if before.channel and before.channel.id == channel['voice_channel_id']:
                    if member in channel['members']:
                        channel['members'].remove(member)
                        self.logger.info(f'{member.display_name} left {before.channel.name}')
                        # try:
                        #     await member.edit(mute=False, deafen=False) 
                        # except discord.errors.HTTPException as e:
                        #     if e.code == 40032:  # Target user is not connected to voice
                        #         pass
                elif after.channel and after.channel.id == channel['voice_channel_id']:
                    if member not in channel['members']:
                        channel['members'].append(member)
                        self.logger.info(f'{member.display_name} joined {after.channel.name}')


    def start_game_embed(self, json_data) -> discord.Embed:
        players = json_data.get("Players", [])
        player_colors = json_data.get("PlayerColors", [])
        match_id = json_data.get("MatchID", "")
        game_code = json_data["GameCode"] 
        player_names_in_game = {player.lower().strip() for player in players}
        self.logger.info(f'Creating an embed for game start MatchId={match_id}')
        
        members_tuple = []
        for member in self.guild.members:
            best_match = None
            best_similarity_ratio = 0
            for player_name in player_names_in_game:
                cropped_player_name = player_name[:min(len(player_name), len(member.display_name.strip()))]
                cropped_member_name = member.display_name.lower().strip()[:min(len(player_name), len(member.display_name.strip()))]
                similarity_ratio = fuzz.ratio(cropped_player_name, cropped_member_name)
                if similarity_ratio >= self.ratio and similarity_ratio > best_similarity_ratio:
                    best_similarity_ratio = similarity_ratio
                    best_match = (cropped_player_name, member)
            if best_match is not None:
                self.logger.debug(f"found {best_match[1].display_name}")
                members_tuple.append(best_match)
        
        embed = discord.Embed(title=f"Ranked Match Started", description=f"Match ID: {match_id} - Code: {game_code}\n Players:", color=discord.Color.dark_purple())
        
        for player_name, player_color in zip(players, player_colors):
            color_emoji = default_color_emojis.get(player_color, ":question:")
            value = ""
            for member in members_tuple: 
                if player_name.strip().lower().startswith(member[0]): 
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player_name)
                    value += "\nMMR: " + f" {player_mmr if player_mmr else 'New Player'}"
                    break
            embed.add_field(name=player_name, value=value, inline=True)
        
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        embed.set_image(url='https://www.essentiallysports.com/stories/the-best-among-us-mods-news-esports-sheriff-doctor-minecraft/assets/24.jpeg')
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match start time: {current_time}", icon_url=self.guild.icon.url)
        
        return embed

    def end_game_embed(self, json_data, match: Match) -> discord.Embed:
        players = json_data.get("Players", [])
        player_colors = json_data.get("PlayerColors", [])
        match_id = json_data.get("MatchID", "")
        game_code = json_data["GameCode"]
        match.players.set_player_colors(players, player_colors)
        player_names_in_game = {player[:4].lower().strip() for player in players}
        player_names_in_game = {player.name[:4].lower().strip() for player in match.players.players}
        self.logger.info(f'Creating an embed for game End MatchId={match_id}')

        if match.result.lower() == "impostors win":
            embed_color = discord.Color.red()
        elif match.result.lower() == "canceled":
            embed_color = discord.Color.orange()
        else:
            embed_color = discord.Color.green()
        embed = discord.Embed(title=f"Ranked Match Ended - {match.result}", 
                      description=f"Match ID: {match_id} Code: {game_code}\nPlayers:", color=embed_color)
      
        members_tuple = []
        for member in self.guild.members:
            best_match = None
            best_similarity_ratio = 0
            for player_name in player_names_in_game:
                cropped_player_name = player_name[:min(len(player_name), len(member.display_name.strip()))]
                cropped_member_name = member.display_name.lower().strip()[:min(len(player_name), len(member.display_name.strip()))]
                similarity_ratio = fuzz.ratio(cropped_player_name, cropped_member_name)
                if (similarity_ratio >= self.ratio) and (similarity_ratio > best_similarity_ratio):
                    best_similarity_ratio = similarity_ratio
                    best_match = (cropped_player_name, member)
            if best_match is not None:
                self.logger.debug(f"found {best_match[1].display_name}")
                members_tuple.append(best_match)

        for player in match.players.get_players_by_team("impostor"):
            color_emoji = default_color_emojis.get(player.color, ":question:")
            value = "" 
            self.logger.debug(f"processing player:{player.name}")
            for member in members_tuple:
                if player.name.strip().lower().startswith(member[0]):
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player.name)
                    value += "\nMMR: " + f" {round(player_mmr, 1) if player_mmr else 'New Player'}"
                    value += f"\nImp MMR: {'+' if player.impostor_elo_gain >= 0 else ''}{round(player.impostor_elo_gain, 1)}"
                    value += f"\nImp Win{round(self.leaderboard.get_player_imp_win_rate(player.name),1)} %"
                    break
            embed.add_field(name=f"{player.name} __**(Imp)**__", value=value, inline=True)
        embed.add_field(name=" ", value=" ", inline=True) 

        for player in match.players.get_players_by_team("crewmate"):
            color_emoji = default_color_emojis.get(player.color, ":question:")
            value = "" 
            self.logger.debug(f"processing player:{player.name}")
            for member in members_tuple:
                if player.name.strip().lower().startswith(member[0]):
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player.name)
                    value += "\nMMR: " + f" {round(player_mmr, 1) if player_mmr else 'New Player'}"
                    value += f"\nCrew MMR: {'+' if player.crewmate_elo_gain >= 0 else ''}{round(player.crewmate_elo_gain, 1)}"
                    value += f"\nCrew Win {round(self.leaderboard.get_player_crew_win_rate(player.name),1)} %"
                    break
            embed.add_field(name=f"{player.name}", value=value, inline=True)

        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        if match.result == "Impostors Win":
            embed.set_image(url="https://i.redd.it/gn3u8lc2exx51.jpg")
        elif match.result in ["Crewmates Win", "HumansByVote"]:
            # embed.set_image(url="https://i.ytimg.com/vi/m4xtGCx8Tao/maxresdefault.jpg")
            embed.set_image(url="https://i.ibb.co/BzGQ8MM/maxresdefault.jpg")
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match start time: {current_time}", icon_url=self.guild.icon.url)
        return embed  

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
                # await self.handle_meeting_start(json_data) #this is automute

            elif event_name == "MeetingEnd":
                self.logger.info(f"Game Code:{game_code} Meeting Endded.")
                # await self.handle_meeting_end(json_data) #this is automute

            elif event_name == "GameEnd":
                self.logger.info(f"Game ID:{match_id} Endded. - Code({game_code})")
                await self.handle_game_end(json_data)
                
            else:
                self.logger.info("Unsupported event:", event_name)

        except json.JSONDecodeError as e:
            self.logger.error("Error decoding JSON:", e)
        except Exception as e:
            self.logger.error("Error processing event:", e, message)

    def find_most_matched_channel(self, players):
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
    

    async def game_start_automute(self, game_channel, player_names_normalized_cropped):
        voice_channel_id = game_channel['voice_channel_id']
        
        voice_channel = self.client.get_channel(voice_channel_id)
        for channel in self.channels.values():
            if channel['voice_channel_id'] == voice_channel_id:
                members = voice_channel.members
                channel['members_in_match'] = [(member.display_name.lower().strip(), member) for member in members]

        if voice_channel is not None:
            tasks = []
            for member in voice_channel.members:
                if member.display_name[:4].lower().strip() in player_names_normalized_cropped:
                    tasks.append(member.edit(mute=True, deafen=True))
            await asyncio.gather(*tasks)  # Deafen all players concurrently
        else:
            self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")


    async def handle_game_start(self, json_data):
        players = json_data.get("Players", [])
        player_names_normalized = {player: player.lower().strip() for player in players}
        player_names_normalized_cropped = {player.lower().strip()[:4] for player in players}
        game_channel = self.find_most_matched_channel(players)
        if game_channel:
            #self.game_start_automute(self, game_channel, player_names_normalized_cropped)
            text_channel_id = game_channel['text_channel_id']
            embed = self.start_game_embed(json_data)
            text_channel = self.client.get_channel(text_channel_id)
            if text_channel:
                await text_channel.send(embed=embed)
            else:
                self.logger.error(f"Text channel with ID {text_channel_id} not found.")
        else:
            self.logger.error(f"Could not find a matching game channel to the game not found.")

    async def handle_meeting_start(self, json_data, timeout=10):
        players = set(json_data.get("Players", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        game_channel = self.find_most_matched_channel(players)
        start_time = time.time()

        if game_channel:
            voice_channel_id = game_channel.get('voice_channel_id')
            voice_channel = self.client.get_channel(voice_channel_id)

            if voice_channel:
                tasks = []

                # Preprocess player names for matching
                players_normalized = {player.lower().strip(): 'alive' for player in players}
                players_normalized.update({dead_player.lower().strip(): 'dead' for dead_player in dead_players})

                for member in voice_channel.members:
                    member_display_name_normalized = member.display_name.lower().strip()

                    # Compare normalized names with member display names
                    for player_name_normalized, status in players_normalized.items():
                        similarity_ratio = fuzz.ratio(player_name_normalized, member_display_name_normalized)
                        if similarity_ratio >= self.ratio:
                            tasks.append(member.edit(deafen=False, mute=status == 'dead'))
                            break  # No need to continue checking other player names

                try:
                    await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
                except asyncio.TimeoutError:
                    self.logger.error("Timed out while handling meeting start.")
            else:
                self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")
        else:
            self.logger.error("No suitable game channel found for the players.")

        end_time = time.time()
        execution_time = end_time - start_time  # Calculate the execution time
        self.logger.info(f"Execution time of meeting_start: {execution_time} seconds")

    async def handle_meeting_end(self, json_data):
        players = set(json_data.get("Players", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        players_normalized = {player.lower().strip(): 'alive' for player in players}
        players_normalized.update({dead_player.lower().strip(): 'dead' for dead_player in dead_players})

        start_time = time.time()

        # Find the most matched game channel
        game_channel = self.find_most_matched_channel(players)
        if game_channel:
            end_time = time.time()
            execution_time = end_time - start_time  # Calculate the execution time
            self.logger.info(f"Execution time of find_most_matched_channel: {execution_time} seconds")

            voice_channel_id = game_channel['voice_channel_id']
            voice_channel = self.client.get_channel(voice_channel_id)
            
            start_time = time.time()
            if voice_channel:
                tasks = []
                for member in voice_channel.members:
                    member_display_name_normalized = member.display_name.lower().strip()
                    for player_name_normalized, status in players_normalized.items():
                        similarity_ratio = fuzz.ratio(player_name_normalized, member_display_name_normalized)
                        if similarity_ratio >= self.ratio:
                            tasks.append(member.edit(mute=status != 'dead', deafen=status != 'dead'))
                            break
                await asyncio.sleep(5)  
                await asyncio.gather(*tasks)
            else:
                self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")

            end_time = time.time()
            execution_time = end_time - start_time  # Calculate the execution time
            self.logger.info(f"Execution time of deafen after meeting end: {execution_time} seconds")
        else:
            self.logger.error(f"Could not find a matching game channel to the game not found.")

    async def game_end_automute(self, voice_channel, voice_channel_id):
        if voice_channel is not None:
            tasks = []
            for member in voice_channel.members:
                tasks.append(member.edit(mute=False, deafen=False))
            
            await asyncio.gather(*tasks)  # Deafen all players concurrently
        else:
            self.logger.error(f"Voice channel with ID {voice_channel_id} not found.")

    async def handle_game_end(self, json_data):
        players = set(json_data.get("Players", []))
        player_names_normalized = {player: player.lower().strip() for player in players}
        game_channel = self.find_most_matched_channel(players)
        members_started_match = game_channel['members_in_match']
        voice_channel_id = game_channel['voice_channel_id']
        text_channel_id = game_channel['text_channel_id']
        voice_channel = self.client.get_channel(voice_channel_id)
        # self.game_end_automute(voice_channel, voice_channel_id)
        await asyncio.sleep(7)
        last_match = self.file_handler.process_unprocessed_matches()
        embed = self.end_game_embed(json_data, last_match)
        await self.client.get_channel(text_channel_id).send(embed=embed)
        await self.client.get_channel(self.match_logs).send(embed=embed)
        

        
    async def start_server(self):
        server = await asyncio.start_server(self.handle_client, 'localhost', 5000)
        async with server:
            self.logger.info("Socket server is listening on localhost:5000...")
            await server.serve_forever()


    async def start(self):
        await asyncio.gather(
            self.start_server(),
            self.client.start(self.token)
        )

if __name__ == "__main__":
    token = "XXXXX"
    channels = {
    'ranked1': {'voice_channel_id': 1200119601627926629, 'text_channel_id': 1200120470616428545, 'members': [], 'members_in_match': []},
    'ranked2': {'voice_channel_id': 1200119662680219658, 'text_channel_id': 1200120538341834782, 'members': [], 'members_in_match': []},
    'ranked3': {'voice_channel_id': 1200119714920276168, 'text_channel_id': 1200120699264704533, 'members': [], 'members_in_match': []},
    'ranked4': {'voice_channel_id': 1217501389366890576, 'text_channel_id': 1217951844156833854, 'members': [], 'members_in_match': []}
    }
    # channels = {
    # 'ranked1': {'voice_channel_id': 1229151012221354076, 'text_channel_id': 1229150964213219430, 'members': [], 'members_in_match': []},
    
    # }
    matches_path = "~/plugins/MatchLog/"
    database_location = "leaderboard_full.csv"

    guild_id = 1116951598422315048
    # guild_id = 1229122991330426990
    bot = DiscordBot(token, channels, matches_path, database_location, guild_id)
    asyncio.run(bot.start())
