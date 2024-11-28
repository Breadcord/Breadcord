from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import shutil
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zipfile import ZipFile

import discord
import pydantic
import tomlkit
from discord.ext import commands
from packaging.requirements import Requirement
from packaging.version import Version

from breadcord import config

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from os import PathLike

    from breadcord import Bot

_logger = getLogger('breadcord.module')


class StreamLogger:
    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
        self.linebuf = ''

    def write(self, buffer: str) -> int:
        self.logger.log(self.level, buffer.rstrip())
        return len(buffer)

    def flush(self):
        pass


class Module:
    def __init__(
        self,
        bot: Bot,
        module_path: str | PathLike[str],
        import_relative_to: str | PathLike[str] = Path(),
    ) -> None:
        self.bot = bot
        self.path = Path(module_path).resolve()
        self.import_string = self.path.relative_to(Path(import_relative_to).resolve()).as_posix().replace('/', '.')
        self.logger = getLogger(self.import_string.removeprefix('breadcord.'))
        self.loaded = False

        if not (self.path / 'manifest.toml').is_file():
            raise FileNotFoundError('manifest.toml file not found')
        self.manifest = parse_manifest(config.load_toml(self.path / 'manifest.toml'))

        self.id = self.manifest.id

    @property
    def storage_path(self) -> Path:
        path = self.bot.storage_dir / self.id
        path.mkdir(exist_ok=True)
        return path

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.import_string})'

    async def load(self) -> None:
        self.load_settings_schema()
        # Some modules might fail to load because of their settings. We want to save them so the user can fix them
        self.bot.save_settings()

        await self.install_requirements()
        await self.bot.load_module(self)
        self.loaded = True
        self.logger.info('Module successfully loaded')

    async def unload(self) -> None:
        await self.bot.unload_module(self)
        self.loaded = False
        self.logger.info('Module successfully unloaded')

    async def reload(self) -> None:
        self.loaded = False
        self.load_settings_schema()
        await self.install_requirements()
        await self.bot.reload_module(self)
        self.loaded = True
        self.logger.info('Module successfully reloaded')

    def load_settings_schema(self) -> None:
        if not (schema_path := self.path / 'settings_schema.toml').is_file():
            return
        settings = self.bot.settings.get_child(self.id, allow_new=True)
        settings.load_schema(file_path=schema_path)
        settings.in_schema = True

    async def install_requirements(self) -> None:
        installed_distributions = tuple(importlib.metadata.distributions())

        def is_missing(requirement: Requirement) -> bool:
            for distribution in installed_distributions:
                if requirement.name == distribution.name and distribution.version in requirement.specifier:
                    return False
            return True

        missing_requirements: tuple[Requirement, ...] = tuple(filter(is_missing, self.manifest.requirements))
        if not missing_requirements:
            return
        self.logger.info('Installing missing requirements: ' + ', '.join(req.name for req in missing_requirements))

        if shutil.which('uv'):
            cmd = ['uv', 'pip', 'install', '--python', sys.executable, *map(str, missing_requirements)]
        else:
            cmd = [sys.executable, '-m', 'pip', 'install', *map(str, missing_requirements)]
            self.logger.warning(
                'uv is not installed, using it is the preferred way to install module requirements. '
                'Falling back to pip.',
            )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        async def log_stream(stream: asyncio.StreamReader, logger_func: Callable[[str], None]) -> None:
            while line := (await stream.readline()).decode().rstrip():
                logger_func(line)

        await asyncio.gather(
            log_stream(process.stdout, self.logger.info),
            log_stream(process.stderr, self.logger.error),
        )
        return_code = await process.wait()
        if return_code != 0:
            self.logger.error(f'Failed to install requirements with exit code {return_code}')
            raise subprocess.CalledProcessError(return_code, cmd)

    async def register_emoji(self, path: str | PathLike[str]) -> discord.PartialEmoji:
        """Register a custom application emoji. Returned emoji objects will not have an ID if registered before bot ready."""
        return await self.bot.register_custom_emoji(self, Path(path).resolve())

    async def register_emojis(self, *paths: str | PathLike[str]) -> list[discord.PartialEmoji]:
        """Register multiple custom application emojis. Returned emoji objects will not have an ID if registered before bot ready."""
        return [await self.register_emoji(path) for path in paths]

    def get_emoji(self, path: str | PathLike[str]) -> discord.PartialEmoji | None:
        """Get a custom application emoji by path. Returns None if the emoji is not registered."""
        # noinspection PyProtectedMember
        return self.bot._registered_emojis.get((self, Path(path).resolve()))


class Modules:
    def __init__(self, modules: list[Module] | None = None) -> None:
        self._modules: dict[str, Module] = {} if modules is None else {module.id: module for module in modules}

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({", ".join(self._modules.keys())})'

    def __iter__(self) -> Generator[Module, None, None]:
        yield from self._modules.values()

    def __contains__(self, item: str) -> bool:
        if not isinstance(item, str):
            raise TypeError(
                f"'in <{self.__class__.__name__}>' requires string as left operand, not '{type(item).__name__}'",
            )
        return item in self._modules

    def get(self, module_id: str) -> Module:
        return self._modules[module_id]

    def add(self, module: Module) -> None:
        if module.id in self._modules:
            module.logger.warning(
                f'Module ID conflicts with {self.get(module.id).import_string} so it will not be loaded',
            )
            return

        self._modules[module.id] = module

    def remove(self, module_id: str) -> None:
        del self._modules[module_id]

    def install_loaf(
        self,
        bot: Bot,
        loaf_path: str | PathLike[str],
        install_path: str | PathLike[str],
        *,
        delete_source: bool = False,
    ) -> None:
        loaf_path = Path(loaf_path)
        install_path = Path(install_path)

        with ZipFile(loaf_path, mode='r') as archive:
            manifest = parse_manifest(tomlkit.loads(archive.read('manifest.toml')).unwrap())
            module_path = install_path / manifest.id
            archive.extractall(module_path)
            module = Module(bot, module_path)
            self.add(module)
            _logger.info(f'Installed module {module.id} from path {loaf_path.resolve()}')
        if delete_source:
            loaf_path.unlink()

    def discover(
        self,
        bot: Bot,
        search_path: str | PathLike[str],
        import_relative_to: str | PathLike[str] = Path(),
    ) -> None:
        path = Path(search_path).resolve()

        if not path.is_dir():
            raise FileNotFoundError(f"module path '{path.as_posix()}' not found")

        for module_path in [path, *list(path.iterdir())]:
            if not (module_path / 'manifest.toml').is_file():
                continue

            module = Module(bot, module_path, import_relative_to=import_relative_to)
            _logger.debug(f'Discovered module: {module.import_string}')
            self.add(module)

            if module_path == path:
                break


class ModuleCog(commands.Cog):
    def __init__(self, module_id: str):
        self.module = global_modules.get(module_id)
        self.bot = self.module.bot
        self.logger = self.module.logger

    @property
    def storage_path(self) -> Path:
        return self.module.storage_path

    @property
    def settings(self) -> config.SettingsGroup:
        if self.module.id not in self.bot.settings.child_keys():
            raise AttributeError(f"module '{self.module.id}' does not have settings")
        return self.bot.settings.get_child(self.module.id)


# PyCharm complains about having @classmethod underneath @pydantic.field_validator
# noinspection PyNestedDecorators
class ModuleManifest(pydantic.BaseModel):
    class Config:
        arbitrary_types_allowed = True

    is_core_module: bool = False
    id: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r'^[a-z_]+$',
    )
    name: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
    )
    description: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
    ) = ''
    version: Version | None = None
    # TODO: add SPDX license validation to the license field
    license: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
    ) = 'No license specified'
    authors: list[pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
    )] = []
    requirements: list[Requirement] = []
    permissions: discord.Permissions = discord.Permissions.none()

    @pydantic.model_validator(mode='after')
    def validate_core_module(self) -> ModuleManifest:
        if self.is_core_module:
            self.license = self.license or 'GNU LGPLv3'
            self.authors = self.authors or ['Breadcord Team']
        elif self.version is None:
            raise ValueError('field required: version')
        return self

    @pydantic.field_validator('version', mode='before')
    @classmethod
    def parse_version(cls, value: str) -> Version:
        return Version(value)

    @pydantic.field_validator('requirements', mode='before')
    @classmethod
    def parse_requirement(cls, values: list[str]) -> list[Requirement]:
        return [Requirement(value) for value in values]

    @pydantic.field_validator('permissions', mode='before')
    @classmethod
    def parse_permissions(cls, value: list[str]) -> discord.Permissions:
        return discord.Permissions(**{permission: True for permission in value})


def parse_manifest(manifest: dict[str, Any]) -> ModuleManifest:
    match manifest:
        case {'core_module': data}:
            return ModuleManifest(**data, is_core_module=True)
        case {'manifest_version': 1, **data}:
            flattened_data: dict[str, Any] = data['module']
            return ModuleManifest(**flattened_data)
        case _:
            raise ValueError('invalid manifest version')


global_modules = Modules()
