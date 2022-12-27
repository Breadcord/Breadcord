from logging import getLogger
from pathlib import Path

import discord
from discord.ext import commands

from . import config
from .module import Module


class Bot(commands.Bot):
    logger = getLogger('bot')

    def __init__(self) -> None:
        self.settings = config.load_schema('bot/settings_schema.toml')
        self.modules: list[Module] = []
        super().__init__(
            command_prefix=commands.when_mentioned_or(self.settings.command_prefix),
            intents=discord.Intents.all()
        )

    def run(self, **kwargs) -> None:
        discord.utils.setup_logging()

        if not (settings_path := Path('config/settings.toml')).is_file():
            self.logger.info('Generating missing config/settings.toml file')
            self.save_settings()
            self.logger.warning('Bot token must be supplied to start the bot')
            return

        self.settings.update_values(config.load_settings(settings_path), strict=False)
        super().run(token=self.settings.token, **kwargs)

    async def setup_hook(self) -> None:
        for module_path in Path('bot/modules').iterdir():
            if (module_path / 'manifest.toml').is_file() and module_path.name in self.settings.modules:
                module = Module(self, module_path)
                self.modules.append(module)
                await module.load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def save_settings(self) -> None:
        Path('config').mkdir(exist_ok=True)
        with open('config/settings.toml', 'w+', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
