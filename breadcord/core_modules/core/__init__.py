import discord
from discord import app_commands

import breadcord


class Core(breadcord.module.ModuleCog):
    @app_commands.command(description="Sync bot slash commands")
    async def sync(self, interaction: discord.Interaction):
        self.bot.tree.copy_global_to(guild=interaction.guild)
        await self.bot.tree.sync(guild=interaction.guild)
        await interaction.response.send_message('Commands synchronised!')


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Core('core'))
