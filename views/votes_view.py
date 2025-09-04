import discord

class VotesView(discord.ui.View):
    def __init__(self, *, timeout=None, embed=None):
        super().__init__(timeout=timeout)
        self.embed = embed
    @discord.ui.button(label="Show Events", style=discord.ButtonStyle.blurple, custom_id="events_button")
    async def gray_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.data.get("custom_id") == "events_button": 
            await interaction.response.send_message(embed=self.embed, ephemeral=True)