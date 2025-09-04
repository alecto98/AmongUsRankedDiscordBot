import discord
from discord.ext import commands
from discord import app_commands
import math
import csv
import asyncio
import os
import cv2
import numpy as np
import pytesseract
import io
import glob
import json
import platform

class MortyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Load configuration
        with open('config.json', 'r') as config_file:
            self.config = json.load(config_file)
        
        self.token = self.config['token']
        
        # Set Tesseract command based on OS
        if platform.system() == 'Windows':
            pytesseract.pytesseract.tesseract_cmd = self.config['tesseract_cmd']['windows']
        else:
            pytesseract.pytesseract.tesseract_cmd = self.config['tesseract_cmd']['linux']

    async def setup_hook(self):
        await self.add_cog(MortyCog(self))
        await self.tree.sync()

    async def on_ready(self):
        print(f'Logged in as {self.user.name}')

    async def start_bot(self):
        await super().start(self.token)

    def getMortyStats(self, number):
        with open(self.config['csv_path'], 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['Number'] == str(number):
                    return {
                        'Number': row['Number'],
                        'Name': row['Name'],
                        'Type': row['Type'],
                        'Rarity': row['Rarity'],
                        'XP': int(row['xp']),
                        'HP': int(row['hp']),
                        'ATK': int(row['atk']),
                        'DEF': int(row['def']),
                        'SPD': int(row['spd']),
                        'Total': int(row['total']),
                        'NumberToEvolve': row['NumberToEvolve'] or None,
                        'BadgesRequired': row['BadgesRequired'] if row['BadgesRequired'] != 'N/A' else None
                    }
        return None

    def calculate_hp(self, base_hp, iv, level, ev):
        ev_bonus = math.floor(math.sqrt(ev) / 4)
        return math.floor((base_hp + iv + ev_bonus + 50) * (level / 50)) + 10

    def calculate_hp_iv(self, hp, base_hp, level, ev):
        possible_ivs = []
        for iv in range(17):  # 0 to 16 inclusive
            if self.calculate_hp(base_hp, iv, level, ev) == hp:
                possible_ivs.append(iv)
        if len(possible_ivs) == 1:
            return possible_ivs[0]
        elif len(possible_ivs) > 1:
            return (min(possible_ivs), max(possible_ivs))
        else:
            return None  # No valid IV found

    def calculate_stat(self, base_stat, iv, level, ev):
        ev_bonus = math.floor(math.sqrt(ev) / 4)
        return math.floor((base_stat + iv + ev_bonus) * (level / 50)) + 5

    def calculate_stat_iv(self, stat, base_stat, level, ev):
        possible_ivs = []
        for iv in range(17):  # 0 to 16 inclusive
            if self.calculate_stat(base_stat, iv, level, ev) == stat:
                possible_ivs.append(iv)
        
        if len(possible_ivs) == 1:
            return possible_ivs[0]
        elif len(possible_ivs) > 1:
            return (min(possible_ivs), max(possible_ivs))
        else:
            return None  # No valid IV found

    def calculate_iv(self, mortyNumber, level, hp, attack, defense, spd, ev):
        morty = self.getMortyStats(mortyNumber)
        if morty is None:
            return None
        hp_iv = self.calculate_hp_iv(hp, morty['HP'], level, ev)
        attack_iv = self.calculate_stat_iv(attack, morty['ATK'], level, ev)
        defense_iv = self.calculate_stat_iv(defense, morty['DEF'], level, ev)
        spd_iv = self.calculate_stat_iv(spd, morty['SPD'], level, ev)
        return hp_iv, attack_iv, defense_iv, spd_iv

class MortyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.type_emojis = self.bot.config['type_emojis']
        self.rarity_emojis = self.bot.config['rarity_emojis']

    @app_commands.command(name="iv", description="Calculate IVs for a Morty from a screenshot or stats")
    @app_commands.describe(
        screenshot="Upload a screenshot of your Morty's stats",
        morty_number="Morty's number",
        level="Morty's level (required if not using screenshot)",
        hp="Morty's HP",
        attack="Morty's Attack",
        defense="Morty's Defense",
        speed="Morty's Speed",
        ev="Morty's EV (optional)"
    )
    async def iv(self, interaction: discord.Interaction, 
                 screenshot: discord.Attachment = None,
                 morty_number: int = None,
                 level: int = None,
                 hp: int = None,
                 attack: int = None,
                 defense: int = None,
                 speed: int = None,
                 ev: int = None):
        await interaction.response.defer()

        if screenshot:
            # Process screenshot
            image_data = await screenshot.read()
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            stats = self.process_image(img)
            if stats:
                morty_number = int(stats['Number'])
                level = int(stats['Level'])
                hp = int(stats['HP'])
                attack = int(stats['Attack'])
                defense = int(stats['Defense'])
                speed = int(stats['Speed'])
            else:
                await interaction.followup.send("Unable to process the image. Please make sure it's a clear screenshot of a Morty's stats.")
                return
        elif morty_number is not None and level is not None:
            # Check if at least one stat is provided
            if not any([hp, attack, defense, speed]):
                await interaction.followup.send("Please provide at least one stat (HP, Attack, defense, or Speed) along with Morty number and level.")
                return
        else:
            await interaction.followup.send("Please provide either a screenshot or Morty number, level, and at least one stat.")
            return

        morty_stats = self.bot.getMortyStats(morty_number)
        
        if morty_stats:
            morty_name = morty_stats['Name']
            morty_type = morty_stats['Type']
            morty_rarity = morty_stats['Rarity']
            
            type_emoji = self.type_emojis.get(morty_type, "")
            rarity_emoji = self.rarity_emojis.get(morty_rarity, "")
            
            embed = discord.Embed(
                title=f"#{morty_number} {morty_name} {type_emoji} {rarity_emoji}",
                color=discord.Color.green()
            )
            
            # Display entered stats
            entered_stats = f"Level: {level}\n"
            if hp is not None:
                entered_stats += f"HP: {hp}\n"
            if attack is not None:
                entered_stats += f"Attack: {attack}\n"
            if defense is not None:
                entered_stats += f"Defense: {defense}\n"
            if speed is not None:
                entered_stats += f"Speed: {speed}\n"
            embed.add_field(name="Entered Stats", value=entered_stats, inline=False)
            
            stats_to_calculate = []
            if hp is not None:
                stats_to_calculate.append(('HP', hp, morty_stats['HP']))
            if attack is not None:
                stats_to_calculate.append(('Attack', attack, morty_stats['ATK']))
            if defense is not None:
                stats_to_calculate.append(('Defense', defense, morty_stats['DEF']))
            if speed is not None:
                stats_to_calculate.append(('Speed', speed, morty_stats['SPD']))

            if ev is None:
                # Calculate for both untrained and fully trained
                untrained_results = []
                trained_results = []
                for stat_name, stat_value, base_stat in stats_to_calculate:
                    if stat_name == 'HP':
                        untrained_iv = self.bot.calculate_hp_iv(stat_value, base_stat, level, 0)
                        trained_iv = self.bot.calculate_hp_iv(stat_value, base_stat, level, 65535)
                    else:
                        untrained_iv = self.bot.calculate_stat_iv(stat_value, base_stat, level, 0)
                        trained_iv = self.bot.calculate_stat_iv(stat_value, base_stat, level, 65535)
                    untrained_results.append((stat_name, untrained_iv))
                    trained_results.append((stat_name, trained_iv))

                untrained_text = self.format_iv_text(untrained_results)
                trained_text = self.format_iv_text(trained_results)
                
                if untrained_text:
                    embed.add_field(name="Untrained IVs (EV = 0)", value=untrained_text, inline=False)
                if trained_text:
                    embed.add_field(name="Fully Trained IVs (EV = 65535)", value=trained_text, inline=False)
                
                if not untrained_text and not trained_text:
                    embed.add_field(name="IVs", value="Unable to calculate IVs", inline=False)
            else:
                # Calculate for the provided EV
                results = []
                for stat_name, stat_value, base_stat in stats_to_calculate:
                    if stat_name == 'HP':
                        iv = self.bot.calculate_hp_iv(stat_value, base_stat, level, ev)
                    else:
                        iv = self.bot.calculate_stat_iv(stat_value, base_stat, level, ev)
                    results.append((stat_name, iv))
                
                iv_text = self.format_iv_text(results)
                if iv_text:
                    embed.add_field(name=f"IVs (EV = {ev})", value=iv_text, inline=False)
                else:
                    embed.add_field(name=f"IVs (EV = {ev})", value="Unable to calculate IVs", inline=False)
            
            # Add Morty's image as thumbnail
            morty_image_path = self.find_morty_image(morty_number)
            if morty_image_path:
                file = discord.File(morty_image_path, filename="morty_image.png")
                embed.set_thumbnail(url="attachment://morty_image.png")
            else:
                embed.set_footer(text="Morty image not found")
            
            # Add user's screenshot to the embed if provided
            if screenshot:
                embed.set_image(url=screenshot.url)
            
            if morty_image_path:
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Unable to find Morty stats. Please check the Morty number.")

    def format_iv_text(self, results):
        if results and any(iv is not None for _, iv in results):
            iv_text = ""
            for stat_name, iv in results:
                if iv is not None:
                    iv_text += f"**{stat_name} IV**: {self.format_iv(iv)}\n"
            return iv_text.strip()
        return None

    def format_iv(self, iv):
        if isinstance(iv, tuple):
            return f"{iv[0]} - {iv[1]}"
        return str(iv)

    def find_morty_image(self, morty_number):
        # Search for an image file that starts with the Morty number
        image_pattern = os.path.join(self.bot.config['morty_images_path'], f"{morty_number}_*.png")
        matching_images = glob.glob(image_pattern)
        
        # Return the first matching image, if any
        return matching_images[0] if matching_images else None

    def process_image(self, img):
        # Resize the image to a smaller size
        max_dimension = 1920  # You can adjust this value
        height, width = img.shape[:2]
        if max(height, width) > max_dimension:
            scale = max_dimension / max(height, width)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

        height, width = img.shape[:2]
        
        # Define regions for each stat (x%, y%, w%, h%)
        regions = {
            'Number': (0.075, 0.0667, 0.0688, 0.05),
            'Level': (0.36875, 0.4083, 0.05, 0.05),
            'HP': (0.825, 0.2217, 0.04375, 0.0517),
            'Attack': (0.825, 0.3033, 0.04375, 0.0475),
            'Defense': (0.825, 0.3833, 0.04375, 0.05),
            'Speed': (0.825, 0.4667, 0.04375, 0.0438)
        }
        
        stats = {}
        for key, (x_pct, y_pct, w_pct, h_pct) in regions.items():
            x = int(x_pct * width)
            y = int(y_pct * height)
            w = int(w_pct * width)
            h = int(h_pct * height)
            
            roi = img[y:y+h, x:x+w]
            text = self.ocr_digit(roi, key)
            stats[key] = text
        
        return stats

    def ocr_digit(self, roi, key):
        # Convert ROI to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Apply additional preprocessing
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)  # Reduced kernel size
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Dilate the image to make digits more pronounced
        kernel = np.ones((2,2), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        
        # Use tesseract OCR with adjusted configuration
        if key == 'Number':
            config = '--psm 6 -c tessedit_char_whitelist=#0123456789'
        elif key == 'Level':
            config = '--psm 6 -c tessedit_char_whitelist=LV0123456789'
        else:
            config = '--psm 6 -c tessedit_char_whitelist=0123456789'
        
        text = pytesseract.image_to_string(dilated, config=config)
        
        # Post-process the text
        text = text.strip()
        if key == 'Number':
            text = ''.join(filter(lambda x: x.isdigit(), text))
        elif key == 'Level':
            text = ''.join(filter(lambda x: x.isdigit(), text))
        
        return text

if __name__ == "__main__":
    bot = MortyBot()
    asyncio.run(bot.start_bot())