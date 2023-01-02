import logging
from pathlib import Path

import discord
from discord.ext import commands

from . import config
from .module import Module


_logger = logging.getLogger('breadcord')


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.settings = config.Settings()
        self.modules: list[Module] = []
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.all()
        )

    def run(self, **kwargs) -> None:
        discord.utils.setup_logging()

        if not Path('config/settings.toml').is_file():
            _logger.info('Generating missing config/settings.toml file'),
            self.save_settings()
            _logger.warning('Bot token must be supplied to start the bot')
            return

        self.reload_settings()
        if self.settings.debug.value:
            logging.getLogger().setLevel(logging.DEBUG)
            _logger.debug('Debug mode enabled')
            logging.getLogger('discord').setLevel(logging.INFO)

        self.command_prefix = commands.when_mentioned_or(self.settings.command_prefix.value)
        super().run(token=self.settings.token.value, log_handler=None, **kwargs)

    async def setup_hook(self) -> None:
        self.discover_modules()
        for module in self.modules:
            await module.load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def discover_modules(self) -> None:
        modules = []
        for search_location in Path('breadcord/core_modules'), Path('breadcord/modules'):
            search_location.mkdir(exist_ok=True)
            for module_path in search_location.iterdir():
                if (module_path / 'manifest.toml').is_file() and module_path.name in self.settings.modules.value:
                    module = Module(self, module_path)
                    modules.append(module)
        self.modules = modules

    def reload_settings(self) -> None:
        settings = config.Settings()
        settings.set_schema('breadcord/settings_schema.toml')
        settings.update_from_dict(config.load_settings('config/settings.toml'), strict=False)
        for module in self.modules:
            module.load_settings_schema()
        self.settings = settings

    def save_settings(self) -> None:
        _logger.info('Saving settings to config/settings.toml')
        Path('config').mkdir(exist_ok=True)
        with open('config/settings.toml', 'w+', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
