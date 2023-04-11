from __future__ import annotations

import re
from asyncio import to_thread
from base64 import b64decode
from pathlib import Path
from typing import Callable
from zipfile import ZipFile

# noinspection PyPackageRequirements
import aiofiles
# noinspection PyPackageRequirements
import aiohttp
import discord
import tomlkit
from discord import app_commands
from discord.utils import escape_markdown

import breadcord
from breadcord.helpers import search_for
from breadcord.module import Module, ModuleManifest, parse_manifest

REPO_PATH = re.compile(r'[\w.-]+/[\w.-]+')
GH_BASE_URL = re.compile(r'^(https?://)?(www\.)?github\.com/')


def nested_zip_extractor(zip_path: Path) -> Callable[[], None]:
    def callback() -> None:
        with ZipFile(zip_path, 'r') as zipfile:
            for zipinfo in filter(lambda i: not i.is_dir(), zipfile.infolist()):
                zipinfo.filename = zipinfo.filename.split('/', 1)[1]
                zipfile.extract(zipinfo, zip_path.parent / zip_path.stem)
        zip_path.unlink()
    return callback


class ModuleTransformer(app_commands.Transformer):
    def transform(self, interaction: discord.Interaction, value: str, /) -> breadcord.module.Module:
        return interaction.client.modules.get(value)

    async def autocomplete(self, interaction: discord.Interaction, value: str, /) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(
                name=f'{module.id} ({"enabled" if module.loaded else "disabled"})',
                value=module.id
            )
            for module in search_for(
                query=value,
                objects=list(interaction.client.modules),
                key=lambda module: '\n'.join((module.id, module.manifest.name, module.manifest.description))
            )
        ]


class ModuleInstallView(discord.ui.View):
    def __init__(self, cog: Modules, manifest: ModuleManifest, user_id: int, zipfile_url: str):
        super().__init__()
        self.cog = cog
        self.manifest = manifest
        self.user_id = user_id
        self.zip_url = zipfile_url

    @discord.ui.button(emoji='📥', label='Install Module', style=discord.ButtonStyle.green)
    async def install_module(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                f'Only <@{self.user_id}> can perform this action!',
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        embed.title = 'Module installing...'
        embed.colour = discord.Colour.yellow()
        for button in self.children:
            button.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

        zip_path = Path(f'breadcord/modules/{self.manifest.id}.zip').resolve()
        async with self.cog.session.get(self.zip_url) as response:
            async with aiofiles.open(zip_path, 'wb') as file:
                async for chunk in response.content:
                    await file.write(chunk)
        await to_thread(nested_zip_extractor(zip_path))
        self.cog.bot.modules.add(Module(self.cog.bot, zip_path.parent / zip_path.stem))

        embed.title = 'Module installed!'
        embed.colour = discord.Colour.green()
        await interaction.message.edit(embed=embed)

    @discord.ui.button(emoji='🛑', label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                f'Only <@{self.user_id}> can perform this action!',
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        embed.title = 'Installation cancelled'
        embed.colour = discord.Colour.red()
        await interaction.message.edit(embed=embed, view=None)


class Modules(breadcord.module.ModuleCog):
    group = app_commands.Group(name='module', description='Manage Breadcord modules')

    def __init__(self, module_id: str):
        super().__init__(module_id)
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        await self.session.close()

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.TransformerError) and isinstance(error.transformer, ModuleTransformer):
            interaction.extras['error_handled'] = True
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Module not found!',
                description=f'No module with the ID `{error.value}` was found.'
            ))

    @group.command()
    @app_commands.check(breadcord.commands.administrator_check)
    async def install(self, interaction: discord.Interaction, module: str):
        module = GH_BASE_URL.sub('', module)
        if not REPO_PATH.match(module):
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Invalid module!',
                description='Try using a `username/repo` reference to the GitHub repository.'
            ))
            return

        async with self.session.get(f'https://api.github.com/repos/{module}/contents/manifest.toml') as response:
            content = (await response.json())['content']
            manifest_str = b64decode(content).decode()
            manifest = parse_manifest(tomlkit.loads(manifest_str).unwrap())

        if manifest.id in self.bot.modules:
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Module already installed!',
                description=f'A module with the ID `{manifest.id}` is already installed.'
            ))
            return

        requirements_str = ", ".join(f'`{req}`' for req in manifest.requirements) or 'No requirements specified'
        permissions = []
        for manifest_permission, bot_permission in zip(manifest.permissions, interaction.app_permissions):
            if manifest_permission[1]:
                emoji = '✅' if bot_permission[1] else '⚠️'
                permissions.append(f'{emoji} {manifest_permission[0]}')

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.blurple(),
                title='Install this module?',
                description=manifest.description,
                url=f'https://github.com/{module}'
            ).add_field(
                name=manifest.name,
                value=f'**Authors:** {escape_markdown(", ".join(manifest.authors))}\n'
                      f'**License:** {escape_markdown(manifest.license)}\n'
                      f'**Requirements:** {escape_markdown(requirements_str)}',
                inline=False
            ).add_field(
                name='Required permissions',
                value='\n'.join(permissions) or '❓ No permissions specified',
                inline=False
            ).set_footer(
                text=f'{manifest.id} v{manifest.version}'
            ),
            view=ModuleInstallView(
                cog=self,
                manifest=manifest,
                user_id=interaction.user.id,
                zipfile_url=f'https://api.github.com/repos/{module}/zipball'
            )
        )

    @group.command()
    @app_commands.rename(module='module_id')
    @app_commands.check(breadcord.commands.administrator_check)
    async def enable(
        self,
        interaction: discord.Interaction,
        module: app_commands.Transform[breadcord.module.Module, ModuleTransformer]
    ):
        await module.load()
        self.bot.settings.modules.value.append(module.id)

        await interaction.response.send_message(embed=discord.Embed(
            colour=discord.Colour.green(),
            title='Module enabled!'
        ).set_footer(
            text=f'{module.manifest.id} v{module.manifest.version}'
        ))

    @group.command()
    @app_commands.rename(module='module_id')
    @app_commands.check(breadcord.commands.administrator_check)
    async def disable(
        self,
        interaction: discord.Interaction,
        module: app_commands.Transform[breadcord.module.Module, ModuleTransformer]
    ):
        await module.unload()
        self.bot.settings.modules.value.remove(module.id)

        await interaction.response.send_message(embed=discord.Embed(
            colour=discord.Colour.green(),
            title='Module disabled!'
        ).set_footer(
            text=f'{module.manifest.id} v{module.manifest.version}'
        ))


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Modules('modulemanager'))
