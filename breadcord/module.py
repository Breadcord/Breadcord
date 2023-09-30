from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import discord
import pydantic
from discord.ext import commands
from packaging.requirements import Requirement
from packaging.version import Version

from breadcord import config

if TYPE_CHECKING:
    from collections.abc import Generator
    from os import PathLike

    from breadcord import Bot

_logger = getLogger('breadcord.module')


class Module:
    def __init__(self, bot: Bot, module_path: str | PathLike[str]) -> None:
        self.bot = bot
        self.path = Path(module_path).resolve()
        self.import_string = self.path.relative_to(Path().resolve()).as_posix().replace('/', '.')
        self.logger = getLogger(self.import_string.removeprefix('breadcord.'))
        self.loaded = False

        if not (self.path / 'manifest.toml').is_file():
            raise FileNotFoundError('manifest.toml file not found')
        self.manifest = parse_manifest(config.load_settings(self.path / 'manifest.toml'))

        self.id = self.manifest.id
        if self.id != self.path.name:
            self.logger.warning(f"Module ID '{self.id}' does not match directory name")

    @property
    def storage_path(self) -> Path:
        path = self.bot.storage_dir / self.id
        path.mkdir(exist_ok=True)
        return path

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.import_string})'

    async def load(self) -> None:
        self.load_settings_schema()
        self.install_requirements()
        await self.bot.load_extension(self.import_string)
        self.loaded = True
        self.logger.info('Module successfully loaded')

    async def unload(self) -> None:
        await self.bot.unload_extension(self.import_string)
        self.loaded = False
        self.logger.info('Module successfully unloaded')

    def load_settings_schema(self) -> None:
        if not (schema_path := self.path / 'settings_schema.toml').is_file():
            return
        settings = self.bot.settings.get_child(self.id, allow_new=True)
        settings.load_schema(file_path=schema_path)
        settings.in_schema = True

    def install_requirements(self) -> None:
        installed_distributions = tuple(importlib.metadata.distributions())

        def is_missing(requirement: Requirement) -> bool:
            for distribution in installed_distributions:
                if requirement.name == distribution.name and distribution.version in requirement.specifier:
                    return False
            return True

        if missing_requirements := set(filter(
            is_missing,
            self.manifest.requirements,
        )):
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing_requirements])  # noqa: S603


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
        self._modules[module.id] = module

    def remove(self, module_id: str) -> None:
        del self._modules[module_id]

    def discover(self, bot: Bot, search_paths: Iterable[str | PathLike[str]]) -> None:
        self._modules = {}
        for path in map(Path, search_paths):
            if not path.is_dir():
                _logger.warning(f"Module path '{path.as_posix()}' not found")
                continue
            for module_path in [path, *list(path.iterdir())]:
                if not (module_path / 'manifest.toml').is_file():
                    continue
                self.add(Module(bot, module_path))
                if module_path == path:
                    break


class ModuleCog(commands.Cog):
    def __init__(self, module_id: str):
        self.module = global_modules.get(module_id)
        self.bot = self.module.bot
        self.logger = self.module.logger

    @property
    def settings(self) -> config.SettingsGroup:
        if self.module.id not in self.bot.settings.child_keys():
            raise AttributeError(f"module '{self.module.id}' does not have settings")
        return self.bot.settings.get_child(self.module.id)


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
    license: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=16,
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
    def parse_version(cls, value: str) -> Version:
        return Version(value)

    @pydantic.field_validator('requirements', mode='before')
    def parse_requirement(cls, values: list) -> list[Requirement]:
        return [Requirement(value) for value in values]

    @pydantic.field_validator('permissions', mode='before')
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
