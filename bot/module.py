from __future__ import annotations

from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.requirements import Requirement
from packaging.version import Version
import pydantic
from discord.ext import commands

from bot import config

if TYPE_CHECKING:
    from bot import Bot


class Module:
    def __init__(self, bot: Bot, module_path: str | PathLike[str]) -> None:
        self.bot = bot
        self.path = Path(module_path).resolve()
        self.import_path = self.path.relative_to(Path('.').resolve()).as_posix().replace('/', '.')
        self.logger = getLogger(self.import_path)
        self.loaded = False

        if not (self.path / 'manifest.toml').is_file():
            raise FileNotFoundError('manifest.toml file not found')
        self.manifest = parse_manifest(config.load_settings(self.path / 'manifest.toml'))

        self.name = self.manifest.name

    async def load(self) -> None:
        self.load_settings()
        await self.bot.load_extension(self.import_path)
        self.loaded = True
        self.logger.info(f'{self.name} module loaded')

    def load_settings(self) -> None:
        loaded_settings = config.load_settings('config/settings.toml')

        if (schema_path := self.path / 'settings_schema.toml').is_file():
            self.bot.settings.set(self.name, config.load_schema(schema_path), strict=False)
            if self.name in loaded_settings and isinstance(loaded_settings[self.name], dict):
                self.bot.settings.get(self.name).update_values(loaded_settings[self.name], strict=False)
                del loaded_settings[self.name]
        self.bot.settings.update_values(loaded_settings, strict=False)


class ModuleCog(commands.Cog):
    def __init__(self, name: str, bot: Bot):
        self.name = name
        self.bot = bot
        self.logger = getLogger(name)


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
            if 'install' in data:
                flattened_data.update(data['install'])
            return ModuleManifest(**flattened_data)
        case _:
            raise ValueError('invalid manifest version')
