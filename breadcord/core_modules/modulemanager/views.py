from __future__ import annotations

from asyncio import to_thread
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Callable
from zipfile import ZipFile

import aiofiles  # noqa
import discord

from breadcord.module import Module, ModuleManifest

if TYPE_CHECKING:
    from . import ModuleManager


def nested_zip_extractor(zip_path: Path) -> Callable[[], None]:
    def callback() -> None:
        with ZipFile(zip_path, 'r') as zipfile:
            for zipinfo in filter(lambda i: not i.is_dir(), zipfile.infolist()):
                zipinfo.filename = zipinfo.filename.split('/', 1)[1]
                zipfile.extract(zipinfo, zip_path.parent / zip_path.stem)
        zip_path.unlink()
    return callback


class ModuleInstallView(discord.ui.View):
    def __init__(self, cog: ModuleManager, manifest: ModuleManifest, user_id: int, zipfile_url: str):
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
        self.cog.logger.info(f"Installing module with ID: {self.manifest.id}")

        zip_path = self.cog.bot.modules_dir / f'{self.manifest.id}.zip'
        async with self.cog.session.get(self.zip_url) as response:
            async with aiofiles.open(zip_path, 'wb') as file:
                async for chunk in response.content:
                    await file.write(chunk)
        await to_thread(nested_zip_extractor(zip_path))
        self.cog.bot.modules.add(Module(self.cog.bot, zip_path.parent / zip_path.stem))
        self.cog.logger.info(f"Installed module with ID: {self.manifest.id}")

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


class ModuleUninstallView(discord.ui.View):
    def __init__(self, cog: ModuleManager, module: Module, user_id: int):
        super().__init__()
        self.cog = cog
        self.module = module
        self.user_id = user_id

    @discord.ui.button(emoji='🗑️', label='Uninstall Module', style=discord.ButtonStyle.red)
    async def uninstall_module(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                f'Only <@{self.user_id}> can perform this action!',
                ephemeral=True
            )
            return

        if self.module.path.parent.name == 'core_modules':
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Cannot uninstall core modules!',
                description=f'If you know what you are doing, this module can be disabled instead.'
            ))

        embed = interaction.message.embeds[0]
        embed.title = 'Module uninstalling...'
        embed.colour = discord.Colour.yellow()
        for button in self.children:
            button.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

        if self.module.loaded:
            await self.module.unload()
            self.cog.bot.settings.modules.value.remove(self.module.id)
        await to_thread(lambda: rmtree(self.module.path))

        embed.title = 'Module uninstalled!'
        embed.colour = discord.Colour.green()
        await interaction.message.edit(embed=embed)

    @discord.ui.button(emoji='🛑', label='Cancel', style=discord.ButtonStyle.blurple)
    async def cancel(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                f'Only <@{self.user_id}> can perform this action!',
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        embed.title = 'Uninstallation cancelled'
        embed.colour = discord.Colour.red()
        await interaction.message.edit(embed=embed, view=None)
