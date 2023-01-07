from __future__ import annotations

from collections.abc import Generator
from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

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

        self.name = self.manifest.name

    @property
    def storage_path(self) -> Path:
        path = Path(f'storage/{self.name}').resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def __repr__(self) -> str:
        return f'Module({self.import_string})'

    async def load(self) -> None:
        self.load_settings_schema()
        await self.bot.load_extension(self.import_string)
        self.loaded = True
        self.logger.info(f'{self.name} module loaded')

    def load_settings_schema(self) -> None:
        if not (schema_path := self.path / 'settings_schema.toml').is_file():
            return
        self.bot.settings.update_from_dict({self.name: {}})
        setting = self.bot.settings.get(self.name)
        setting.value.set_schema(schema_path)
        setting.in_schema = True


class Modules:
    def __init__(self, modules: list[Module] | None = None) -> None:
        self._modules: dict[str, Module] = {} if modules is None else {module.name: module for module in modules}

    def __repr__(self) -> str:
        return f'Modules({", ".join(self._modules.keys())})'

    def __iter__(self) -> Generator[Module, None, None]:
        yield from self._modules.values()

    def get(self, module_name: str) -> Module:
        return self._modules[module_name]

    def add(self, module: Module) -> None:
        if module.name in self._modules:
            module.logger.error(
                f'module name conflicts with {self.get(module.name).import_string} so it will not be loaded'
            )
        self._modules[module.name] = module

    def discover(self, bot: Bot, search_paths: Iterable[PathLike | str]) -> None:
        self._modules = {}
        for path in search_paths:
            path = Path(path)
            path.mkdir(exist_ok=True)
            for module_path in path.iterdir():
                if not (module_path / 'manifest.toml').is_file() or module_path.name not in bot.settings.modules.value:
                    continue
                module = Module(bot, module_path)
                self.add(module)


class ModuleCog(commands.Cog):
    def __init__(self, name: str | None = None):
        self.name: str = self.__class__.__name__ if name is None else name
        self.module = global_modules.get(self.name)
        self.bot = self.module.bot
        self.logger = self.module.logger


class ModuleManifest(pydantic.BaseModel):
    class Config:
        arbitrary_types_allowed = True

    name: pydantic.constr(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        regex=r'^[\w\-]+$'
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

    @pydantic.validator('version', pre=True)
    def parse_version(cls, value: str) -> Version:
        return Version(value)

    @pydantic.validator('requirements', pre=True, each_item=True)
    def parse_requirement(cls, value: str) -> Requirement:
        return Requirement(value)


def parse_manifest(manifest: dict[str, Any]) -> ModuleManifest:
    match manifest:
        case {'manifest_version': 1, **data}:
            flattened_data: dict[str, Any] = data['module']
            return ModuleManifest(**flattened_data)
        case _:
            raise ValueError('invalid manifest version')


global_modules = Modules()
