from __future__ import annotations

import logging
import sys
from argparse import Namespace
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
# noinspection PyProtectedMember
from discord.utils import _ColourFormatter

from . import config, errors
from .module import Modules, global_modules

if TYPE_CHECKING:
    from types import TracebackType
    from . import app

_logger = logging.getLogger('breadcord.bot')


class CommandTree(discord.app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError, /) -> None:
        if 'error_handled' in interaction.extras and interaction.extras['error_handled']:
            return

        if isinstance(error, errors.NotAdministratorError):
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Missing permissions!',
                description='This operation is restricted to bot owners only.'
            ))

        else:
            _logger.exception(f'{error.__class__.__name__}: {error}', exc_info=error)


class Bot(commands.Bot):
    def __init__(self, *, tui_app: app.Breadcord | None = None, args: Namespace) -> None:
        self.tui = tui_app
        self.args = args
        self.settings = config.SettingsGroup('settings', observers={})
        self.ready = False

        data_dir = self.args.data or Path('data')
        data_dir.mkdir(exist_ok=True)
        self.data_dir = data_dir.resolve()
        self.logs_dir = self.data_dir / 'logs'
        self.logs_dir.mkdir(exist_ok=True)
        self.modules_dir = self.data_dir / 'modules'
        self.modules_dir.mkdir(exist_ok=True)
        self.storage_dir = self.data_dir / 'storage'
        self.storage_dir.mkdir(exist_ok=True)
        self.settings_file = self.data_dir / 'settings.toml'

        super().__init__(
            command_prefix=[],
            intents=discord.Intents.all(),
            tree_cls=CommandTree
        )

    @property
    def modules(self) -> Modules:
        return global_modules

    def _init_logging(self) -> None:
        def handle_exception(exc_type: type[BaseException], value: BaseException, traceback: TracebackType) -> None:
            _logger.critical(f'Uncaught {exc_type.__name__}: {value}', exc_info=(exc_type, value, traceback))
        sys.excepthook = handle_exception

        if self.tui is None:
            discord.utils.setup_logging(formatter=_ColourFormatter())
        else:
            discord.utils.setup_logging(handler=self.tui.handler)

        log_file = self.logs_dir / 'breadcord_latest.log'
        if log_file.is_file():
            with log_file.open('r', encoding='utf-8') as file:
                timestamp = file.read(10)
            try:
                datetime.strptime(timestamp, '%Y-%m-%d')
            except ValueError:
                timestamp = '0000-00-00'
            base_filename = timestamp + '.{}.log'
            log_number = 1
            while (rename_path := self.logs_dir / base_filename.format(log_number)).is_file():
                log_number += 1
            log_file.rename(rename_path)

        discord.utils.setup_logging(
            handler=logging.FileHandler(log_file, 'w', encoding='utf-8'),
            formatter=logging.Formatter(
                fmt='{asctime} [{levelname}] {name}: {message}',
                datefmt='%Y-%m-%d %H:%M:%S',
                style='{'
            )
        )

    async def start(self, *_, **kwargs) -> None:
        self._init_logging()

        if not self.settings_file.is_file():
            _logger.info('Generating missing settings.toml file'),
            self.settings = config.SettingsGroup('settings', schema_path='breadcord/settings_schema.toml')
            _logger.warning('Bot token must be supplied to start the bot')
            self.ready = True
            await self.close()
            return

        self.load_settings()
        if self.settings.debug.value:
            logging.getLogger().setLevel(logging.DEBUG)
            _logger.debug('Debug mode enabled')
            logging.getLogger('discord').setLevel(logging.INFO)
        self.command_prefix = commands.when_mentioned_or(*self.settings.command_prefixes.value)
        self.owner_ids = set(self.settings.administrators.value)

        await super().start(token=self.settings.token.value)

    def run(self, **kwargs) -> None:
        super().run(token='', log_handler=None, **kwargs)

    async def setup_hook(self) -> None:
        self.modules.discover(self, search_paths=[Path('breadcord/core_modules'), self.modules_dir])

        for module in self.settings.modules.value:
            if module not in self.modules:
                _logger.warning(f"Module '{module}' enabled but not found")
                continue
            await self.modules.get(module).load()

        @self.settings.command_prefixes.observe
        def on_command_prefixes_changed(_, new: list[str]) -> None:
            self.command_prefix = commands.when_mentioned_or(*new)

        @self.settings.administrators.observe
        def on_administrators_changed(_, new: list[int]) -> None:
            self.owner_ids = set(new)

    async def on_connect(self) -> None:
        if self.tui is not None:
            self.tui.online = True
        self.ready = True

    async def on_disconnect(self) -> None:
        if self.tui is not None:
            self.tui.online = False

    async def on_resumed(self) -> None:
        if self.tui is not None:
            self.tui.online = True

    async def close(self) -> None:
        _logger.info('Shutting down bot')
        await super().close()
        if self.ready:
            self.save_settings()
        else:
            _logger.warning('Bot not ready, settings have not been saved')
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers.clear()

    async def is_owner(self, user: discord.User, /) -> bool:
        if user.id == self.owner_id or user.id in self.owner_ids:
            return True

        app_info = await self.application_info()
        if app_info.team:
            self.owner_ids = ids = {member.id for member in app_info.team.members}
            return user.id in ids
        else:
            self.owner_id = owner_id = app_info.owner.id
            return user.id == owner_id

    def load_settings(self, file_path: str | PathLike[str] | None = None) -> None:
        if file_path is None:
            file_path = self.settings_file
        _logger.info(f'Loading settings from {Path(file_path).as_posix()}')

        settings = config.SettingsGroup(
            'settings',
            schema_path='breadcord/settings_schema.toml',
            observers=self.settings.observers
        )
        settings.update_from_dict(config.load_settings(file_path), strict=False)
        for module in self.modules:
            module.load_settings_schema()

        self.settings = settings

    def save_settings(self, file_path: str | PathLike[str] | None = None) -> None:
        if file_path is None:
            path = self.settings_file
        else:
            path = Path(file_path)
        _logger.info(f'Saving settings to {path.as_posix()}')
        path.parent.mkdir(parents=True, exist_ok=True)
        output = self.settings.as_toml().as_string().rstrip() + '\n'
        with path.open('w+', encoding='utf-8') as file:
            file.write(output)
