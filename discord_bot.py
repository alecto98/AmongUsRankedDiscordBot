import discord
import asyncio
import json
from datetime import datetime
import pytz
from file_processing import FileHandler
import time 
from match_class import Match
import logging

# default_color_emojis = { #test
#     "0": "<:Red_crewmate:1228161446500634624>",
#     "1": "<:Blue_crewmate:1228161430868725800>",
#     "2": "<:Green_crewmate:1228161436031647807>",
#     "3": "<:Pink_crewmate:1228161443002847262>",
#     "4": "<:Orange_crewmate:1228161677694992394>",
#     "5": "<:Yellow_crewmate:1228161453681279079>",
#     "6": "<:Black_crewmate:1228161429631270952>",
#     "7": "<:White_crewmate:1228161593096011796>",
#     "8": "<:Purple_crewmate:1228161902618742804>",
#     "9": "<:Brown_crewmate:1228161432076554361>",
#     "10": "<:Cyan_crewmate:1228161433926373446>",
#     "11": "<:Lime_crewmate:1228161533268197416>",
#     "12": "<:Maroon_crewmate:1228161439387222016>",
#     "13": "<:Rose_crewmate:1228161620375506984>",
#     "14": "<:Banana_crewmate:1228161428599341076>",
#     "15": "<:Gray_crewmate:1228161434974814260>",
#     "16": "<:Tan_crewmate:1228161450028171334>",
#     "17": "<:Coral_crewmate:1228161433053691904>"
#     # Add more default colors and URLs here...
# }
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
    def __init__(self, token, channels, matches_path, database_location):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename='DiscordBot.log', encoding='utf-8', level=logging.DEBUG)
        self.matches_path = matches_path
        self.database_location = database_location
        self.file_handler = FileHandler(self.matches_path, self.database_location)
        self.leaderboard = self.file_handler.leaderboard
        self.token = token
        self.channels = channels
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        self.client = discord.Client(intents=intents)
        self.guild = self.client.get_guild(1116951598422315048)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.logger.info(f'Imported match files from {matches_path}, and Database location from {database_location}')

    async def on_ready(self):
        self.logger.info(f'{self.client.user} has connected to Discord!')
        self.guild = self.client.get_guild(1116951598422315048)

    async def on_message(self, message):
        if message.author == self.client.user:
            return

        if message.content.startswith('!stats'):
            player_name = message.author.display_name
            player_stats = {
                'Rank': self.leaderboard.get_player_ranking(player_name),
                'Player Name': message.author.display_name,
                'MMR': self.leaderboard.get_player_elo(player_name),
                'Crewmate MMR': self.leaderboard.get_player_crew_elo(player_name),
                'Impostor MMR': self.leaderboard.get_player_imp_elo(player_name)
            }

            # Create an embed
            embed = discord.Embed(title='Player Stats', color=discord.Color.blue())
            for stat_name, stat_value in player_stats.items():
                embed.add_field(name=stat_name, value=stat_value, inline=False)

            # Set thumbnail to player's icon
            embed.set_thumbnail(url=message.author.avatar.url)
            embed.set_footer(text=f"Ranking in the Pre-Season        devs: Aiden, Xer", icon_url=self.guild.icon.url)

            # Send the embed as a message
            await message.channel.send(embed=embed)

        await self.client.process_commands(message)

    def start_game_embed(self, json_data) -> discord.Embed:
        players = json_data.get("Players", [])
        player_colors = json_data.get("PlayerColors", [])
        match_id = json_data.get("MatchID", "")
        game_code = json_data["GameCode"]["Code"]
        player_names_in_game = {player[:4].lower().strip() for player in players}
        members_tuple = []
        for member in self.guild.members:
            if member.display_name[:4].lower().strip() in player_names_in_game:
                self.logger.debug(f"found {member.display_name}")
                members_tuple.append((member.display_name[:4].lower().strip(), member))
        embed = discord.Embed(title=f"Ranked Match Started - Code: {game_code}", description=f"Match ID: {match_id}\n Players:", color=discord.Color.green())
        for player_name, player_color in zip(players, player_colors):
            color_emoji = default_color_emojis.get(player_color, ":question:")
            value = ""
            for member in members_tuple: 
                if member[0] == player_name[:4].lower().strip():
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player_name)
                    value += "\nMMR: " + f" {player_mmr if player_mmr else 'New Player'}"
                    break
            embed.add_field(name=player_name, value=value, inline=True)
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        embed.set_image(url="https://www.essentiallysports.com/stories/the-best-among-us-mods-news-esports-sheriff-doctor-minecraft/assets/24.jpeg")
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match start time: {current_time}", icon_url=self.guild.icon.url)
        return embed

    def end_game_embed(self, json_data, match: Match) -> discord.Embed:
        players = json_data.get("Players", [])
        player_colors = json_data.get("PlayerColors", [])
        match_id = json_data.get("MatchID", "")
        match.players.set_player_colors(players, player_colors)
        player_names_in_game = {player[:4].lower().strip() for player in players}
        members_tuple = [(member.display_name[:4].lower().strip(), member) for member in self.guild.members 
                        if member.display_name[:4].lower().strip() in player_names_in_game]
        
        if match.result.lower() == "impostors win":
            embed_color = discord.Color.red()
        elif match.result.lower() == "canceled":
            embed_color = discord.Color.orange()
        else:
            embed_color = discord.Color.green()
        embed = discord.Embed(title=f"Ranked Match Ended - {match.result}", 
                      description=f"Match ID: {match_id}\n Players:", color=embed_color)
        for player in match.players.get_players_by_team("impostor"):
            color_emoji = default_color_emojis.get(player.color, ":question:")
            value = "" 
            self.logger.info(f"processing player:{player.name}")
            for member in members_tuple:
                if member[0] == player.name[:4].lower().strip():
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player.name)
                    value += "\nMMR: " + f" {round(player_mmr, 1) if player_mmr else 'New Player'}"
                    value += f"\nImp MMR Change: {round(player.impostor_elo_gain, 1)}"
                    break
            embed.add_field(name=f"{player.name}", value=value, inline=True)
        embed.add_field(name="      ", value="      ", inline=True) 

        for player in match.players.get_players_by_team("crewmate"):
            color_emoji = default_color_emojis.get(player.color, ":question:")
            value = "" 
            self.logger.info(f"processing player:{player.name}")
            for member in members_tuple:
                if member[0] == player.name[:4].lower().strip():
                    value = color_emoji + f" {member[1].mention}"
                    player_mmr = self.leaderboard.get_player_elo(player.name)
                    value += "\nMMR: " + f" {round(player_mmr, 1) if player_mmr else 'New Player'}"
                    value += f"\nCrew MMR Change: {round(player.crewmate_elo_gain, 1)}"
                    break
            embed.add_field(name=f"{player.name}", value=value, inline=True)

        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S %Z')
        if match.result == "Impostors Win":
            embed.set_image(url="https://i.redd.it/gn3u8lc2exx51.jpg")
        elif match.result in ["Crewmates Win", "HumansByVote"]:
            embed.set_image(url="https://i.ytimg.com/vi/m4xtGCx8Tao/maxresdefault.jpg")
        embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Match start time: {current_time}", icon_url=self.guild.icon.url)
        return embed  

    async def handle_client(self, reader, writer):
        data = await reader.read(1024)
        message = data.decode('utf-8')
        self.logger.debug('Received:', message) 

        try:
            json_data = json.loads(message)
            event_name = json_data.get("EventName")
            match_id = json_data.get("MatchID", "")
            game_code = json_data["GameCode"]["Code"]

            if event_name == "GameStart":
                self.logger.info(f"Game ID:{match_id} Started. - Code({game_code})")
                await self.handle_game_start(json_data)

            elif event_name == "MeetingStart":
                self.logger.info(f"Game ID:{match_id} Meeting Started.")
                await self.handle_meeting_start(json_data)

            elif event_name == "MeetingEnd":
                self.logger.info(f"Game ID:{match_id} Meeting Endded.")
                await self.handle_meeting_end(json_data)

            elif event_name == "GameEnd":
                self.logger.info(f"Game ID:{match_id} Endded. - Code({game_code})")
                await self.handle_game_end(json_data)
            else:
                self.logger.info("Unsupported event:", event_name)

        except json.JSONDecodeError as e:
            self.logger.error("Error decoding JSON:", e)
        except Exception as e:
            self.logger.error("Error processing event:", e, message)

    async def handle_game_start(self, json_data):
        game_channel = None
        players = json_data.get("Players", [])
        player_names_in_game = {player[:4].lower().strip() for player in players}
        for channel_id in self.channels:
            channel = self.client.get_channel(channel_id[0])
            if channel is not None:
                tasks = []
                for member in channel.members:
                    if member.display_name[:4].lower().strip() in player_names_in_game:
                        tasks.append(member.edit(mute=True, deafen=True))
                        if game_channel == None:
                            game_channel = channel_id
                await asyncio.gather(*tasks)  # Deafen all players concurrently
            else:
                self.logger.error(f"Voice channel with ID {channel_id} not found.")
        embed = self.start_game_embed(json_data)
        await self.client.get_channel(game_channel[1]).send(embed=embed)

    async def handle_meeting_start(self, json_data):
        players = set(json_data.get("Players", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        alive_players = {player[:4].lower().strip() for player in players if player not in dead_players}
        dead_players = {player[:4].lower().strip() for player in dead_players}

        for channel_id in self.channels:
            channel = self.client.get_channel(channel_id[0])
            if channel is not None:
                tasks = []
                for member in channel.members:
                    if member.display_name[:4].lower().strip() in alive_players:
                        tasks.append(member.edit(deafen=False, mute=False))
                    elif member.display_name[:4].lower().strip() in dead_players:
                        tasks.append(member.edit(deafen=False, mute=True))
                await asyncio.gather(*tasks)
            else:
                self.logger.error(f"Voice channel with ID {channel_id} not found.")

    async def handle_meeting_end(self, json_data):
        players = set(json_data.get("Players", []))
        dead_players = set(json_data.get("DeadPlayers", []))
        alive_players = {player[:4].lower().strip() for player in players if player not in dead_players}
        dead_players = {player[:4].lower().strip() for player in dead_players}
        await asyncio.sleep(5)
        for channel_id in self.channels:
            channel = self.client.get_channel(channel_id[0])
            if channel is not None:
                tasks = []
                for member in channel.members:
                    if member.display_name[:4].lower().strip() in alive_players:
                        tasks.append(member.edit(mute=True, deafen=True))
                    elif member.display_name[:4].lower().strip() in dead_players:
                        tasks.append(member.edit(mute=False, deafen=False))
                await asyncio.gather(*tasks)
            else:
                self.logger.error(f"Voice channel with ID {channel_id} not found.")

    async def handle_game_end(self, json_data):
        game_channel = None
        players = set(json_data.get("Players", []))
        player_names_set = {player[:4].lower().strip() for player in players}

        for channel_id in self.channels:
            channel = self.client.get_channel(channel_id[0])
            if channel is not None:
                tasks = []
                for member in channel.members:
                    if member.display_name[:4].lower().strip() in player_names_set:
                        tasks.append(member.edit(mute=False, deafen=False))
                        if game_channel == None:
                            game_channel = channel_id
                await asyncio.gather(*tasks)  # Deafen all players concurrently
            else:
                print(f"Voice channel with ID {channel_id} not found.")
    
        await asyncio.sleep(3)
        last_match = self.file_handler.process_unprocessed_matches()
        embed = self.end_game_embed(json_data, last_match)
        await self.client.get_channel(game_channel[1]).send(embed=embed)
        
    async def start_server(self):
        server = await asyncio.start_server(self.handle_client, 'localhost', 5000)
        async with server:
            print("Socket server is listening on localhost:5000...")
            await server.serve_forever()

    async def start(self):
        await asyncio.gather(
            self.start_server(),
            self.client.start(self.token)
        )

if __name__ == "__main__":
    token = "XXXX"
    channels = [
        (1200119601627926629, 1200120470616428545),
        (1200119662680219658, 1200120538341834782),
        (1200119714920276168, 1200120699264704533),
        (1217501389366890576, 1217951844156833854)
    ]
    matches_path = "~/plugins/MatchLog/"
    database_location = "leaderboard.csv"
    
    bot = DiscordBot(token, channels, matches_path, database_location)
    asyncio.run(bot.start())
