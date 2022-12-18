import logging

from discord.ext import commands

from bot import Bot


class Module(commands.Cog):
    def __init__(self, name: str, bot: Bot):
        self.name = name
        self.bot = bot
        self.logger = logging.getLogger(name)
