import aiofiles
import discord
import tomlkit
import tomlkit.exceptions
from discord import app_commands
from discord.ext import commands

import breadcord


@breadcord.helpers.simple_transformer(breadcord.config.Setting)
class SettingTransformer(app_commands.Transformer):
    def transform(self, interaction: discord.Interaction, value: str, /) -> breadcord.config.Setting:
        setting: breadcord.config.SettingsGroup = interaction.client.settings
        path = value.split('.')
        for child in path[:-1]:
            setting = setting.get_child(child)
        return setting.get(path[-1])

    async def autocomplete(self, interaction: discord.Interaction, value: str, /) -> list[app_commands.Choice[str]]:
        if not await breadcord.helpers.administrator_check(interaction):
            return [app_commands.Choice(name='⚠️ Missing permissions!', value=value)]

        return [
            app_commands.Choice(name=(path := setting.path_id().removeprefix('settings.')), value=path)
            for setting in breadcord.helpers.search_for(
                query=value,
                objects=interaction.client.settings.walk(skip_groups=True),
                key=lambda setting: '\n'.join(filter(
                    bool,
                    (setting.key, setting.path_id(), setting.description),
                )),
            )
        ]


class SettingsFileEditor(discord.ui.Modal, title='Settings File Editor'):
    editor = discord.ui.TextInput(label='settings.toml', style=discord.TextStyle.paragraph)

    def __init__(self, bot: breadcord.Bot):
        self.bot = bot
        with open(self.bot.settings_file, encoding='utf-8') as file:
            self.editor.default = file.read()
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with aiofiles.open(self.bot.settings_file, 'w', encoding='utf-8') as file:
            await file.write(self.editor.value)
        self.bot.load_settings()
        await interaction.response.send_message(
            embed=discord.Embed(
                title='Settings saved!',
                colour=discord.Colour.green(),
            ),
            ephemeral=self.bot.settings.ephemeral.value,
        )


class Settings(
    breadcord.module.ModuleCog,
    commands.GroupCog,
    group_name='settings',
    group_description='Manage bot settings',
):
    @app_commands.command(description='Get the value of a setting')
    @app_commands.describe(setting='The key of the setting you want to get')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def get(self, interaction: discord.Interaction, setting: SettingTransformer):
        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.blurple(),
                title=f'Inspecting setting: `{setting.key}`',
                description=setting.description,
            ).add_field(
                name='Value',
                value=f'```py\n{setting.value!r}\n```',
                inline=False,
            ).add_field(
                name='Type',
                value=f'```py\n{setting.type.__name__}\n```',
            ).add_field(
                name='In schema',
                value=f'```py\n{setting.in_schema}\n```',
            ),
            ephemeral=self.settings.ephemeral.value,
        )

    @app_commands.command(description='Set the value of a setting')
    @app_commands.describe(setting='The key of the setting you want to change')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def set(self, interaction: discord.Interaction, setting: SettingTransformer, value: str):
        parsed_value = tomlkit.value(value).unwrap()
        old_value = setting.value
        setting.value = parsed_value

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.green(),
                title=f'Updated setting: `{setting}`',
            ).add_field(
                name='Old value',
                value=f'```diff\n- {old_value!r}\n```',
                inline=False,
            ).add_field(
                name='New value',
                value=f'```diff\n+ {parsed_value!r}\n```',
                inline=False,
            ),
            ephemeral=self.settings.ephemeral.value,
        )

    @set.autocomplete('value')
    async def autocomplete_value(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        if not await breadcord.helpers.administrator_check(interaction):
            return [app_commands.Choice(name='Missing permissions!', value=current)]

        try:
            setting = SettingTransformer.transform(interaction, interaction.namespace.setting)
        except KeyError:
            return [app_commands.Choice(name=f"⚠️ Invalid key '{interaction.namespace.setting}'", value=current)]

        current_str = tomlkit.item(setting.value).as_string()
        autocomplete = [app_commands.Choice(name=current_str, value=current_str)]

        if setting.type == int:  # noqa: E721
            current = current or '0'
            try:
                autocomplete.append(app_commands.Choice(name=f'(integer) {int(current)}', value=current))
            except ValueError:
                return [app_commands.Choice(name=f"⚠️ Invalid integer '{current}'", value=current)]

        elif setting.type == str:  # noqa: E721
            if current[0] + current[-1] in ('""', "''"):
                current = current[1:-1]
            autocomplete.append(app_commands.Choice(
                name=f"(string) '{current}'" if current else '(string) <empty>',
                value=tomlkit.item(current).as_string(),
            ))

        elif setting.type == bool:  # noqa: E721
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

    @app_commands.command(description='Directly edit the bot settings file on disk')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SettingsFileEditor(self.bot))

    @app_commands.command(description='Reload bot settings from disk')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def reload(self, interaction: discord.Interaction):
        self.bot.load_settings()
        await interaction.response.send_message(
            'Settings reloaded from config file.',
            ephemeral=self.settings.ephemeral.value,
        )

    @app_commands.command(description='Save bot settings to disk')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def save(self, interaction: discord.Interaction):
        self.bot.save_settings()
        await interaction.response.send_message(
            'Settings saved to config file.',
            ephemeral=self.settings.ephemeral.value,
        )


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Settings('settings_manager'))
