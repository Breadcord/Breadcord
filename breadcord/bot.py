import logging
from argparse import Namespace
from os import PathLike
from pathlib import Path

import discord
from discord.ext import commands

from . import config, errors
from .module import Modules, global_modules

_logger = logging.getLogger('breadcord.bot')


class CommandTree(discord.app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError, /) -> None:
        if isinstance(error, errors.NotAdministratorError):
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Missing permissions!',
                description='This operation is restricted to bot owners only.'
            ))
        else:
            raise error


class Bot(commands.Bot):
    def __init__(self, args: Namespace) -> None:
        self.args = args
        self.settings = config.SettingsGroup('settings', schema_path='breadcord/settings_schema.toml', observers={})
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.all(),
            tree_cls=CommandTree
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
        search_paths = ['breadcord/core_modules']
        if self.args.include is not None:
            search_paths.extend(self.args.include)
        search_paths.append('breadcord/modules')
        self.modules.discover(self, search_paths=search_paths)

        for module in self.settings.modules.value:
            if module not in self.modules:
                _logger.warning(f'Module \'{module}\' enabled but not found')
                continue
            await self.modules.get(module).load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def reload_settings(self, file_path: str | PathLike[str] = 'config/settings.toml') -> None:
        _logger.info(f'Reloading settings from {Path(file_path).as_posix()}')

        settings = config.SettingsGroup(
            'settings',
            schema_path='breadcord/settings_schema.toml',
            observers=self.settings.observers
        )
        settings.update_from_dict(config.load_settings(file_path), strict=False)
        for module in self.modules:
            module.load_settings_schema()

        self.settings = settings

    def save_settings(self, file_path: str | PathLike[str] = 'config/settings.toml') -> None:
        path = Path(file_path)
        _logger.info(f'Saving settings to {path.as_posix()}')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w+', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
