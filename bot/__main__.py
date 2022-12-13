from pathlib import Path

import discord
from discord.ext import commands

from bot import config


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.settings = config.Settings()
        self.modules = [
            module for module in Path('bot/modules').iterdir()
            if module.is_dir() and (module/'__init__.py').is_file()
        ]
        self.load_settings()
        super().__init__(
            command_prefix=commands.when_mentioned_or(self.settings.command_prefix),
            intents=discord.Intents.all()
        )

    def run(self, **kwargs) -> None:
        super().run(token=self.settings.token, root_logger=True, **kwargs)

    async def setup_hook(self) -> None:
        for module in self.modules:
            if (module/'__init__.py').is_file():
                await self.load_extension(f'bot.modules.{module.name}')

    async def close(self) -> None:
        self.save_settings()
        await super().close()

    def load_settings(self) -> None:
        self.settings = config.load_schema('bot/settings_schema.toml')
        loaded_settings = config.load_settings('config/settings.toml')

        for module in self.modules:
            if (schema_path := module/'settings_schema.toml').is_file():
                self.settings.set(module.name, config.load_schema(schema_path), strict=False)
                if module.name in loaded_settings and isinstance(loaded_settings[module.name], dict):
                    self.settings.get(module.name).update_values(loaded_settings[module.name], strict=False)
                    del loaded_settings[module.name]
        self.settings.update_values(loaded_settings, strict=False)

    def save_settings(self) -> None:
        with open('config/settings.toml', 'w', encoding='utf-8') as file:
            output = self.settings.as_toml().as_string().rstrip() + '\n'
            file.write(output)


bot = Bot()


if __name__ == '__main__':
    bot.run()
