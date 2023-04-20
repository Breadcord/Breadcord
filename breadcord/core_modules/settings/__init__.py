import discord
import tomlkit
import tomlkit.exceptions
from discord import app_commands

import breadcord


class SettingsFileEditor(discord.ui.Modal, title='Settings File Editor'):
    editor = discord.ui.TextInput(label='settings.toml', style=discord.TextStyle.paragraph)

    def __init__(self, bot: breadcord.Bot):
        self.bot = bot
        with open(self.bot.settings_file, 'r', encoding='utf-8') as file:
            self.editor.default = file.read()
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        with open(self.bot.settings_file, 'w', encoding='utf-8') as file:
            file.write(self.editor.value)
        self.bot.load_settings()
        await interaction.response.send_message(
            embed=discord.Embed(
                title='Settings saved!',
                colour=discord.Colour.green()
            ),
            ephemeral=self.bot.settings.settings.ephemeral.value
        )


class Settings(breadcord.module.ModuleCog):
    group = app_commands.Group(name='settings', description='Manage bot settings')

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def get(self, interaction: discord.Interaction, key: str):
        setting = self.bot.settings.get(key)

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.blurple(),
                title=f'Inspecting setting: `{setting.key}`',
                description=setting.description
            ).add_field(
                name='Value',
                value=f'```py\n{setting.value!r}\n```',
                inline=False
            ).add_field(
                name='Type',
                value=f'```py\n{setting.type.__name__}\n```'
            ).add_field(
                name='In schema',
                value=f'```py\n{setting.in_schema}\n```'
            ),
            ephemeral=self.bot.settings.settings.ephemeral.value
        )

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def set(self, interaction: discord.Interaction, key: str, value: str):
        setting = self.bot.settings.get(key)
        parsed_value = tomlkit.value(value).unwrap()
        old_value = setting.value
        setting.value = parsed_value

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.green(),
                title=f'Updated setting: `{key}`'
            ).add_field(
                name='Old value',
                value=f'```diff\n- {old_value!r}\n```',
                inline=False
            ).add_field(
                name='New value',
                value=f'```diff\n+ {parsed_value!r}\n```',
                inline=False
            ),
            ephemeral=self.bot.settings.settings.ephemeral.value
        )

    @get.autocomplete('key')
    @set.autocomplete('key')
    async def autocomplete_key(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        if not await breadcord.commands.administrator_check(interaction):
            return [app_commands.Choice(name='⚠️ Missing permissions!', value=current)]

        return [
            app_commands.Choice(name=setting.key, value=setting.key)
            for setting in self.bot.settings
            if current in setting.key
        ]

    @set.autocomplete('value')
    async def autocomplete_value(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        if not await breadcord.commands.administrator_check(interaction):
            return [app_commands.Choice(name='Missing permissions!', value=current)]
        if interaction.namespace.key not in self.bot.settings:
            return [app_commands.Choice(name=f"⚠️ Invalid key '{interaction.namespace.key}'", value=current)]

        setting = self.bot.settings.get(interaction.namespace.key)
        current_str = tomlkit.item(setting.value).as_string()
        autocomplete = [app_commands.Choice(name=current_str, value=current_str)]

        if setting.type == int:
            current = current or '0'
            try:
                autocomplete.append(app_commands.Choice(name=f'(integer) {int(current)}', value=current))
            except ValueError:
                return [app_commands.Choice(name=f"⚠️ Invalid integer '{current}'", value=current)]

        elif setting.type == str:
            if len(current) >= 2 and current[0] == current[-1] and current[0] in '\'"':
                current = current[1:-1]
            autocomplete.append(app_commands.Choice(
                name=f"(string) '{current}'" if current else '(string) <empty>',
                value=tomlkit.item(current).as_string()
            ))

        elif setting.type == bool:
            autocomplete.extend(booleans := [
                app_commands.Choice(name=f'(boolean) {choice}', value=choice)
                for choice in ('false', 'true')
                if current.lower() in choice
            ])
            if not booleans:
                return [app_commands.Choice(name=f"⚠️ Invalid boolean '{current}'", value=current)]

        elif current:
            autocomplete.append(app_commands.Choice(name=current, value=current))

        return autocomplete

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SettingsFileEditor(self.bot))

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def reload(self, interaction: discord.Interaction):
        self.bot.load_settings()
        await interaction.response.send_message(
            'Settings reloaded from config file.',
            ephemeral=self.bot.settings.settings.ephemeral.value
        )

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def save(self, interaction: discord.Interaction):
        self.bot.save_settings()
        await interaction.response.send_message(
            'Settings saved to config file.',
            ephemeral=self.bot.settings.settings.ephemeral.value
        )


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Settings('settings'))
