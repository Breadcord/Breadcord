import logging
from os import PathLike
from pathlib import Path

import discord
from discord.ext import commands

from . import config
from .module import Modules, global_modules

_logger = logging.getLogger('breadcord.bot')


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.settings = config.Settings(schema_path='breadcord/settings_schema.toml')
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.all()
        )

    @property
    def modules(self) -> Modules:
        return global_modules

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
        self.modules.discover(self, search_paths=('breadcord/core_modules', 'breadcord/modules'))
        for module in self.modules:
            await module.load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def reload_settings(self) -> None:
        settings = config.Settings(schema_path='breadcord/settings_schema.toml')
        settings.update_from_dict(config.load_settings('config/settings.toml'), strict=False)
        for module in self.modules:
            module.load_settings_schema()
        self.settings = settings

    def save_settings(self, file_path: PathLike | str = 'config/settings.toml') -> None:
        path = Path(file_path)
        _logger.info(f'Saving settings to {path.as_posix()}')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w+', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
