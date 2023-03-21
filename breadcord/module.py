from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from collections.abc import Generator
from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import discord
import pydantic
from discord.ext import commands
from packaging.requirements import Requirement
from packaging.version import Version

from breadcord import config

if TYPE_CHECKING:
    from breadcord import Bot

_logger = getLogger('breadcord.module')


class Module:
    def __init__(self, bot: Bot, module_path: str | PathLike[str]) -> None:
        self.bot = bot
        self.path = Path(module_path).resolve()
        self.import_string = self.path.relative_to(Path().resolve()).as_posix().replace('/', '.')
        self.logger = getLogger(self.import_string)
        self.loaded = False

        if not (self.path / 'manifest.toml').is_file():
            raise FileNotFoundError('manifest.toml file not found')
        self.manifest = parse_manifest(config.load_settings(self.path / 'manifest.toml'))

        self.id = self.manifest.id
        if self.id != self.path.name:
            self.logger.warning(f"Module ID '{self.id}' does not match directory name")

    @property
    def storage_path(self) -> Path:
        path = Path(f'storage/{self.id}').resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def __repr__(self) -> str:
        return f'Module({self.import_string})'

    async def load(self) -> None:
        self.load_settings_schema()
        self.install_requirements()
        await self.bot.load_extension(self.import_string)
        self.loaded = True
        self.logger.info('Module successfully loaded')

    def load_settings_schema(self) -> None:
        if not (schema_path := self.path / 'settings_schema.toml').is_file():
            return
        settings = self.bot.settings.get_child(self.id, allow_new=True)
        settings.load_schema(file_path=schema_path)
        settings.in_schema = True

    def install_requirements(self) -> None:
        distributions = list(importlib.metadata.distributions())
        missing_requirements = []
        for requirement in self.manifest.requirements:
            if not any(
                requirement.name == distribution.name
                and distribution.version in requirement.specifier
                for distribution in distributions
            ):
                missing_requirements.append(str(requirement))

        if missing_requirements:
            self.logger.info(f'Installing missing requirements: {", ".join(missing_requirements)}')
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing_requirements])


class Modules:
    def __init__(self, modules: list[Module] | None = None) -> None:
        self._modules: dict[str, Module] = {} if modules is None else {module.id: module for module in modules}

    def __repr__(self) -> str:
        return f'Modules({", ".join(self._modules.keys())})'

    def __iter__(self) -> Generator[Module, None, None]:
        yield from self._modules.values()

    def __contains__(self, item: str) -> bool:
        return item in self._modules

    def get(self, module_id: str) -> Module:
        return self._modules[module_id]

    def add(self, module: Module) -> None:
        if module.id in self._modules:
            module.logger.warning(
                f'Module ID conflicts with {self.get(module.id).import_string} so it will not be loaded'
            )
        self._modules[module.id] = module
    
    def to_json(self) -> None:
        return {**self._modules} 
    
    def remove(self, module: Module) -> None:
        _modules.pop(module.id)
    
    def replace(self, modules_directory: dict) -> None:
        self._modules = modules_directory

    def discover(self, bot: Bot, search_paths: Iterable[str | PathLike[str]]) -> None:
        self._modules = {}
        for path in search_paths:
            path = Path(path)
            path.mkdir(exist_ok=True)
            for module_path in [path] + list(path.iterdir()):
                if not (module_path / 'manifest.toml').is_file():
                    continue
                self.add(Module(bot, module_path))
                if module_path == path:
                    return


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

    id: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        regex=r'^[a-z_]+$'
    )
    name: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=64
    )
    description: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=128
    ) = 'No description provided'
    version: Version
    license: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=16
    ) = 'No license specified'
    authors: list[pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=32
    )] = []
    requirements: list[Requirement] = []
    required_modules: list[str] = []
    permissions: discord.Permissions = discord.Permissions.none()

    @pydantic.validator('version', pre=True)
    def parse_version(cls, value: str) -> Version:
        return Version(value)

    @pydantic.validator('requirements', pre=True, each_item=True)
    def parse_requirement(cls, value: str) -> Requirement:
        return Requirement(value)

    @pydantic.validator('permissions', pre=True)
    def parse_permissions(cls, value: list[str]) -> discord.Permissions:
        return discord.Permissions(**{permission: True for permission in value})


def parse_manifest(manifest: dict[str, Any]) -> ModuleManifest:
    match manifest:
        case {'manifest_version': 1, **data}:
            flattened_data: dict[str, Any] = data['module']
            return ModuleManifest(**flattened_data)
        case _:
            raise ValueError('invalid manifest version')


global_modules = Modules()
