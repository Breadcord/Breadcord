from pathlib import Path

import discord
from discord.ext import commands

from . import config
from .module import Module


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.settings = config.load_schema('bot/settings_schema.toml')
        self.settings.update_values(config.load_settings('config/settings.toml'), strict=False)
        self.modules: list[Module] = []
        super().__init__(
            command_prefix=commands.when_mentioned_or(self.settings.command_prefix),
            intents=discord.Intents.all()
        )

    def run(self, **kwargs) -> None:
        super().run(token=self.settings.token, root_logger=True, **kwargs)

    async def setup_hook(self) -> None:
        for module_path in Path('bot/modules').iterdir():
            if (module_path / 'manifest.toml').is_file() and module_path.name in self.settings.modules:
                module = Module(self, module_path)
                self.modules.append(module)
                await module.load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def save_settings(self) -> None:
        with open('config/settings.toml', 'w', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
