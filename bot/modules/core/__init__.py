from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot.__main__ import Bot


class Core(commands.Cog):
    def __init__(self, bot: 'Bot'):
        self.bot = bot

    @app_commands.command()
    async def sync(self, interaction: discord.Interaction):
        self.bot.tree.copy_global_to(guild=interaction.guild)
        await self.bot.tree.sync(guild=interaction.guild)
        await interaction.response.send_message('Commands synchronised!')


async def setup(bot: 'Bot'):
    await bot.add_cog(Core(bot))
