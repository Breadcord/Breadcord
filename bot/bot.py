from logging import getLogger
from pathlib import Path

import discord
from discord.ext import commands

from . import config
from .module import Module


_logger = getLogger('bot')


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.settings = config.Settings()
        self.modules: list[Module] = []
        super().__init__(
            command_prefix=None,
            intents=discord.Intents.all()
        )

    def run(self, **kwargs) -> None:
        discord.utils.setup_logging()
        self.reload_settings()
        self.command_prefix = commands.when_mentioned_or(self.settings.command_prefix)

        if not Path('config/settings.toml').is_file():
            _logger.info('Generating missing config/settings.toml file'),
            self.save_settings()
            _logger.warning('Bot token must be supplied to start the bot')
            return

        super().run(token=self.settings.token, log_handler=None, **kwargs)

    async def setup_hook(self) -> None:
        for module_path in Path('bot/modules').iterdir():
            if (module_path / 'manifest.toml').is_file() and module_path.name in self.settings.modules:
                module = Module(self, module_path)
                self.modules.append(module)
                await module.load()

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def reload_settings(self) -> None:
        settings = config.Settings()
        settings.set_schema('bot/settings_schema.toml')
        settings.update_from_dict(config.load_settings('config/settings.toml'), strict=False)
        for module in self.modules:
            module.load_settings_schema()
        self.settings = settings

    def save_settings(self) -> None:
        _logger.info('Saving settings to config/settings.toml')
        Path('config').mkdir(exist_ok=True)
        with open('config/settings.toml', 'w+', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)
