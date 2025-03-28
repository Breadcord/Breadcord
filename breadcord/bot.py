from __future__ import annotations

import asyncio
import hashlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os.path
import sys
from collections.abc import Awaitable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import discord
from discord.ext import commands
from discord.ext.commands.view import StringView

from . import config, errors
from .helpers import IndentFormatter
from .module import Module, Modules, global_modules

if TYPE_CHECKING:
    from argparse import Namespace
    from os import PathLike
    from types import TracebackType

    from . import app

_logger = logging.getLogger('breadcord.bot')
module_path = Path(__file__).parent


def _get_emoji_name(module: Module, path: Path, data: bytes) -> str:
    file_hash = hashlib.md5(data).hexdigest()
    return f'{module.id}_{path.stem}__{file_hash[:6]}'


class CommandTree(discord.app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError, /) -> None:
        if interaction.extras.get('error_handled'):
            return

        if isinstance(error, errors.NotAdministratorError):
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Missing permissions!',
                description='This operation is restricted to bot owners only.',
            ))

        else:
            _logger.exception(f'{error.__class__.__name__}: {error}', exc_info=error)


class Bot(commands.Bot):
    def __init__(self, *, tui_app: app.Breadcord | None = None, args: Namespace) -> None:
        self.tui = tui_app
        self.args = args
        self.settings = config.SettingsGroup('settings', observers={})
        self._registered_emojis: dict[tuple[Module, Path], discord.PartialEmoji] = {}
        # self._cached_application_emojis: set[discord.PartialEmoji] = set()
        self.ready = False
        self._new_data_dir = False

        data_dir = self.args.data_dir or Path('data')
        if not data_dir.is_dir():
            self._new_data_dir = True
            data_dir.mkdir()
        self.data_dir = data_dir.resolve()

        logs_dir = self.args.logs_dir or self.data_dir / 'logs'
        logs_dir.mkdir(exist_ok=True)
        self.logs_dir = logs_dir.resolve()

        modules_dir = self.data_dir / 'modules'
        modules_dir.mkdir(exist_ok=True)
        self.modules_dir = modules_dir.resolve()

        storage_dir = self.args.storage_dir or self.data_dir / 'storage'
        storage_dir.mkdir(exist_ok=True)
        self.storage_dir = storage_dir.resolve()

        self.settings_file = (self.args.setting_file or self.data_dir / 'settings.toml').resolve()

        super().__init__(
            command_prefix=[],
            intents=discord.Intents.all(),
            tree_cls=CommandTree,
        )

    @property
    def modules(self) -> Modules:
        return global_modules

    def _init_logging(self) -> None:
        def handle_exception(exc_type: type[BaseException], value: BaseException, traceback: TracebackType) -> None:
            _logger.critical(f'Uncaught {exc_type.__name__}: {value}', exc_info=(exc_type, value, traceback))
        sys.excepthook = handle_exception

        if self.tui is None:
            # noinspection PyProtectedMember
            discord.utils.setup_logging(formatter=IndentFormatter(discord.utils._ColourFormatter()))
        else:
            discord.utils.setup_logging(handler=self.tui.handler)

        log_file = self.logs_dir / 'breadcord_latest.log'
        if log_file.is_file():
            with log_file.open(encoding='utf-8') as file:
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
            formatter=IndentFormatter(logging.Formatter(
                fmt='{asctime} [{levelname}] {name}: {message}',
                datefmt='%Y-%m-%d %H:%M:%S',
                style='{',
            )),
        )

    async def on_command_error(
        self,
        _,
        exception: commands.errors.CommandError,
        /,
    ) -> None:
        error = exception.__traceback__
        _logger.debug(error)
        _logger.exception(f'{exception.__class__.__name__}: {exception}', exc_info=exception)

    async def start(self, *_, **__) -> None:
        self._init_logging()

        if self._new_data_dir:
            _logger.info('Creating new data directory in current location')

        if not self.settings_file.is_file():
            _logger.info('Generating missing settings.toml file')
            self.settings = config.SettingsGroup('settings', schema_path=module_path / 'settings_schema.toml')
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
        for unresolved_path in self.args.module_dirs:
            path = unresolved_path.resolve()
            _logger.info(f'Extra module path: {path.as_posix()}')
            relative_path = path.relative_to(Path().resolve())
            self.modules.discover(self, search_path=relative_path)

        _logger.debug('Finding core modules')
        self.modules.discover(self, search_path=module_path / 'core_modules', import_relative_to=module_path.parent)

        _logger.debug(f'Finding user modules ({self.modules_dir.as_posix()})')
        self.modules.discover(self, search_path=self.modules_dir)

        for loaf in self.modules_dir.glob('*.loaf'):
            _logger.info(f'Loaf pending install: {loaf.name}')
            self.modules.install_loaf(self, loaf_path=loaf, install_path=self.modules_dir, delete_source=True)

        await self.load_modules()

        @self.settings.command_prefixes.observe
        def on_command_prefixes_changed(_, new: list[str]) -> None:
            self.command_prefix = commands.when_mentioned_or(*new)

        @self.settings.administrators.observe
        def on_administrators_changed(_, new: list[int]) -> None:
            self.owner_ids = set(new)

        async def run_when_ready(coroutine: Awaitable) -> None:
            await self.wait_until_ready()
            await coroutine

        self.loop.create_task(run_when_ready(self.on_first_connect()))

    async def load_modules(self) -> None:
        modules: list[str] = self.settings.modules.value
        unique_modules: list[str] = []
        for m in modules:
            if m not in unique_modules:
                unique_modules.append(m)

        if len(modules) != len(unique_modules):
            _logger.warning(
                f'Duplicate module entries found in settings. '
                f'Removing {len(modules) - len(unique_modules)} duplicate(s).',
            )
            self.settings.modules.value = unique_modules

        failed: list[Module] = []

        async def load_wrapper(module_id: str) -> None:
            if module_id not in self.modules:
                _logger.warning(f"Module '{module_id}' enabled but not found")
                return
            module = self.modules.get(module_id)
            try:
                await module.load()
            except Exception as error:
                _logger.exception(f'Failed to load module {module!r}: {error}')
                # Not needed as of writing (2024/03/29), but it means we won't ever have a "ghost loaded" module
                module.loaded = False
                failed.append(module)

        await asyncio.gather(*map(load_wrapper, unique_modules))
        if failed:
            _logger.warning('Failed to load modules: ' + ', '.join(module.id for module in failed))

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

        self.owner_id = owner_id = app_info.owner.id
        return user.id == owner_id

    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[commands.Context[Any]] = discord.utils.MISSING,
    ) -> Any:
        if not self.settings.case_insensitive_prefix.value:
            return await super().get_context(origin, cls=cls)

        if cls is discord.utils.MISSING:
            cls = commands.Context

        if isinstance(origin, discord.Interaction):
            return await cls.from_interaction(origin)

        view = StringView(origin.content)
        ctx = cls(view=view, bot=self, message=origin)
        if origin.author.id == self.user.id:
            return ctx

        prefix = await self.get_prefix(origin)
        if origin.content.lower().startswith(tuple(p.lower() for p in prefix)):
            # Upon success `skip_string` will remove the prefix from the view
            invoked_prefix = discord.utils.find(
                StringView(origin.content.lower()).skip_string,
                prefix,
            )
            view = StringView(origin.content[len(invoked_prefix):])
            ctx = cls(view=view, bot=self, message=origin)
        else:
            return ctx

        if self.strip_after_prefix:
            view.skip_ws()

        invoker = view.get_word()
        ctx.invoked_with = invoker
        ctx.prefix = invoked_prefix
        ctx.command = self.all_commands.get(invoker)
        return ctx

    def load_settings(self, file_path: str | PathLike[str] | None = None) -> None:
        if file_path is None:
            file_path = self.settings_file
        _logger.info(f'Loading settings from {Path(file_path).as_posix()}')

        settings = config.SettingsGroup(
            'settings',
            schema_path=module_path / 'settings_schema.toml',
            observers=self.settings.observers,
        )
        settings.update_from_dict(config.load_toml(file_path), strict=False)
        for module in self.modules:
            module.load_settings_schema()

        self.settings = settings

    def save_settings(self, file_path: str | PathLike[str] | None = None) -> None:
        path = self.settings_file if file_path is None else Path(file_path)
        _logger.info(f'Saving settings to {path.as_posix()}')
        path.parent.mkdir(parents=True, exist_ok=True)
        output = self.settings.as_toml().as_string().rstrip() + '\n'
        with path.open('w', encoding='utf-8') as file:
            file.write(output)

    async def load_module(self, module: Module) -> None:
        await self.load_extension(module.import_string, module=module)

    async def unload_module(self, module: Module) -> None:
        await self.unload_extension(module.import_string)

    async def reload_module(self, module: Module) -> None:
        await self.reload_extension(module.import_string, module=module)

    async def load_extension(
        self,
        name: str,
        *,
        package: str | None = None,
        module: Module | None = None,
    ) -> None:
        name = self._resolve_name(name, package)
        if name in self.extensions:
            raise commands.errors.ExtensionAlreadyLoaded(name)
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise commands.errors.ExtensionNotFound(name)

        await self._load_from_module_spec(spec, name, module=module)

    async def _load_from_module_spec(
        self,
        spec: importlib.machinery.ModuleSpec,
        key: str,
        *,
        module: Module | None = None,
    ) -> None:
        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib
        try:
            spec.loader.exec_module(lib)
        except Exception as e:
            del sys.modules[key]
            raise commands.errors.ExtensionFailed(key, e) from e
        try:
            setup = getattr(lib, 'setup')  # noqa: B009 # idc what ruff thinks, this is what d.py does
        except AttributeError:
            del sys.modules[key]
            raise commands.errors.NoEntryPointError(key)  # noqa: B904 # idc what ruff thinks, this is what d.py does
        try:
            if module is not None and len(inspect.signature(setup).parameters) > 1:
                await setup(self, module)
            else:
                await setup(self)
        except Exception as e:
            del sys.modules[key]
            await self._remove_module_references(lib.__name__)
            await self._call_module_finalizers(lib, key)
            raise commands.errors.ExtensionFailed(key, e) from e
        else:
            # name mangling
            # noinspection PyUnresolvedReferences
            self._BotBase__extensions[key] = lib

    async def reload_extension(
        self,
        name: str,
        *,
        package: str | None = None,
        module: Module | None = None,
    ) -> None:
        name = self._resolve_name(name, package)
        lib = self.extensions.get(name)
        if lib is None:
            raise commands.errors.ExtensionNotLoaded(name)
        # noinspection PyProtectedMember
        modules = {
            name: module
            for name, module in sys.modules.items()
            if discord.utils._is_submodule(lib.__name__, name)
        }
        try:
            await self._remove_module_references(lib.__name__)
            await self._call_module_finalizers(lib, name)
            await self.load_extension(name, module=module)
        except Exception:
            await lib.setup(self)
            # name mangling
            # noinspection PyUnresolvedReferences
            self._BotBase__extensions[name] = lib
            sys.modules.update(modules)
            raise

    async def on_first_connect(self) -> None:
        application_emojis = await self.fetch_application_emojis()

        for module, path in dict(self._registered_emojis):  # Copy
            async with aiofiles.open(path, 'rb') as file:
                name = _get_emoji_name(module, path, await file.read())
            emoji = discord.utils.get(application_emojis, name=name)
            if emoji is None:
                await self.register_custom_emoji(module, path)
            else:
                _logger.debug(f'Emoji {emoji} found from {path.relative_to(self.data_dir).as_posix()}')
                self._registered_emojis[(module, path)] = discord.PartialEmoji(
                    name=emoji.name,
                    id=emoji.id,
                    animated=emoji.animated,
                )

    async def register_custom_emoji(self, module: Module, path: Path) -> discord.PartialEmoji:
        """Register a custom application emoji. Returned emoji objects will not have an ID if registered before bot ready."""
        if os.path.getsize(path) > 256*1024: # 256 KiB
            raise ValueError(f'Emojis cannot be larger than 256 KiB: {path.as_posix()}')

        # We use this method before the bot is ready, and deal with that in on_first_connect
        if not self.ready:
            partial = discord.PartialEmoji(
                name=path.stem,
                id=None,
                animated=path.suffix == '.gif',
            )
            self._registered_emojis[(module, path)] = partial
            return partial

        if (module, path) in self._registered_emojis:
            del self._registered_emojis[(module, path)]  # Might error when adding

        async with aiofiles.open(path, 'rb') as file:
            img_data = await file.read()
        name = _get_emoji_name(module, path, img_data)

        emoji = await self.create_application_emoji(name=name, image=img_data)
        partial = discord.PartialEmoji(
            name=emoji.name,
            id=emoji.id,
            animated=emoji.animated,
        )
        _logger.debug(f'Emoji {partial} registered from {path.relative_to(self.data_dir).as_posix()}')
        self._registered_emojis[(module, path)] = partial  # It didn't error
        return partial
