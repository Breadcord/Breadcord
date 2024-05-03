from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import discord
import pydantic
from discord.ext import commands
from packaging.requirements import Requirement
from packaging.version import Version

from breadcord import config

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from os import PathLike

    from breadcord import Bot

_logger = getLogger('breadcord.module')


class Module:
    def __init__(self, bot: Bot, module_path: str | PathLike[str], *, is_core_module: bool = False) -> None:
        self.bot = bot
        self.path = Path(module_path).resolve()
        self.import_string = self.path.relative_to(Path().resolve()).as_posix().replace('/', '.')
        self.loaded = False

        manifest_file_path = self.path / ('core_module.toml' if is_core_module else 'pyproject.toml')
        if not manifest_file_path.is_file():
            raise FileNotFoundError(f'{manifest_file_path.name} file not found')

        if is_core_module:
            self.manifest = ModuleManifest.from_core_module_manifest(config.load_toml(manifest_file_path))
        else:
            self.manifest = ModuleManifest.from_pyproject(config.load_toml(manifest_file_path))

        self.id = self.manifest.id
        self.logger = getLogger(('core_modules.' if is_core_module else 'modules.') + self.id)

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

    async def reload(self) -> None:
        self.loaded = False
        self.load_settings_schema()
        self.install_requirements()
        await self.bot.reload_extension(self.import_string)
        self.loaded = True
        self.logger.info('Module successfully reloaded')

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

        if missing_requirements := tuple(map(str, filter(is_missing, self.manifest.dependencies))):
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

            for module_path in [path, *path.iterdir()]:
                if Path('breadcord/core_modules') in module_path.parents:
                    if not (module_path / 'core_module.toml').is_file():
                        continue
                    self.add(Module(bot, module_path, is_core_module=True))
                else:
                    if not (module_path / 'pyproject.toml').is_file():
                        continue
                    self.add(Module(bot, module_path))

                if module_path == path:
                    break


class ModuleCog(commands.Cog):
    def __init__(self, module_id: str):
        self.module = global_modules.get(module_id)
        self.bot = self.module.bot
        self.logger = self.module.logger
        self.storage_path = self.module.storage_path

    @property
    def settings(self) -> config.SettingsGroup:
        if self.module.id not in self.bot.settings.child_keys():
            raise AttributeError(f"module '{self.module.id}' does not have settings")
        return self.bot.settings.get_child(self.module.id)


class ModuleAuthor(pydantic.BaseModel):
    name: str | None = None
    email: str | None = None

    @pydantic.model_validator(mode='after')
    def either_or(self) -> Self:
        if self.name is None and self.email is None:
            raise ValueError('either name or email must be specified')
        return self

    def __str__(self) -> str:
        return ' '.join(filter(None, (self.name, f'<{self.email}>' if self.email is not None else None)))


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
    authors: list[ModuleAuthor] = []
    dependencies: list[Requirement] = []
    permissions: discord.Permissions = discord.Permissions.none()

    @pydantic.model_validator(mode='after')
    def validate_core_module(self) -> Self:
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

    @pydantic.field_validator('dependencies', mode='before')
    @classmethod
    def parse_requirement(cls, values: list[str]) -> list[Requirement]:
        return [Requirement(value) for value in values]

    @pydantic.field_validator('permissions', mode='before')
    @classmethod
    def parse_permissions(cls, value: list[str]) -> discord.Permissions:
        return discord.Permissions(**{permission: True for permission in value})

    @classmethod
    def from_core_module_manifest(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(dict(data, is_core_module=True))

    @classmethod
    def from_pyproject(cls, data: dict[str, Any]) -> Self:
        pyproject_keymap = {
            'name': 'id',  # I hate this!
            'description': 'description',
            'version': 'version',
            'dependencies': 'dependencies',
        }
        flattened_data = {
            pyproject_keymap[key]: data['project'][key]
            for key in pyproject_keymap.keys() & data['project'].keys()
        }

        flattened_data['is_core_module'] = False
        flattened_data.update(data.get('tool', {}).get('breadcord', {}))

        return cls.model_validate(flattened_data)


global_modules = Modules()
