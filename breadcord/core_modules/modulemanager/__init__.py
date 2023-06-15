from __future__ import annotations

import re
from base64 import b64decode

import aiohttp
import discord
import tomlkit
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

import breadcord
from breadcord.module import parse_manifest
from . import views

REPO_PATH = re.compile(r'[\w.-]+/[\w.-]+')
GH_BASE_URL = re.compile(r'^(https?://)?(www\.)?github\.com/')


class ModuleTransformer(app_commands.Transformer):
    def transform(self, interaction: discord.Interaction, value: str, /) -> breadcord.module.Module:
        return interaction.client.modules.get(value)

    async def autocomplete(self, interaction: discord.Interaction, value: str, /) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(
                name=f'{module.id} ({"enabled" if module.loaded else "disabled"})',
                value=module.id
            )
            for module in breadcord.helpers.search_for(
                query=value,
                objects=list(interaction.client.modules),
                key=lambda module: '\n'.join(filter(
                    bool,
                    (module.id, module.manifest.name, module.manifest.description)
                ))
            )
        ]


class ModuleManager(
    breadcord.module.ModuleCog,
    commands.GroupCog,
    group_name="module",
    group_description="Manage Breadcord modules"
):
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

    @app_commands.command(description="Install a module from github")
    @app_commands.describe(module="A github url or repo path", branch="A branch of the repo")
    @app_commands.check(breadcord.helpers.administrator_check)
    async def install(self, interaction: discord.Interaction, module: str, branch: str | None = None):
        module = GH_BASE_URL.sub('', module).removesuffix('.git').replace(" ", "-")
        branch = branch.replace(' ', '-') if branch else None
        if not REPO_PATH.match(module):
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Invalid module!',
                description='Try using a `username/repo` reference to the GitHub repository.'
            ))
            return

        async with self.session.get(
            f'https://api.github.com/repos/{module}/contents/manifest.toml' + (f'?ref={branch}' if branch else '')
        ) as response:
            if response.status != 200:
                await interaction.response.send_message(embed=discord.Embed(
                    colour=discord.Colour.red(),
                    title='Module not found!',
                    description=(
                        "The repository or branch specified does not exist, "
                        "can't be reached or isn't a Breadcord module."
                    )
                ))
                return

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

        requirements_str = ", ".join(req.name for req in manifest.requirements) or 'No requirements specified'
        permissions = []
        for manifest_permission, bot_permission in zip(manifest.permissions, interaction.app_permissions):
            if manifest_permission[1]:
                emoji = '✅' if bot_permission[1] else '⚠️'
                permissions.append(f'{emoji} {manifest_permission[0]}')
        view = views.ModuleInstallView(
            cog=self,
            user_id=interaction.user.id,
            manifest=manifest,
            zipfile_url=f'https://api.github.com/repos/{module}/zipball/{branch or ""}'
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.blurple(),
                title='Install this module?',
                description=manifest.description,
                url=f'https://github.com/{module}/{f"tree/{branch}" if branch else ""}'
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
            view=view
        )
        view.message = await interaction.original_response()

    @app_commands.command(description="Uninstall an installed module")
    @app_commands.describe(module="The id of the module to be uninstalled")
    @app_commands.rename(module='module_id')
    @app_commands.check(breadcord.helpers.administrator_check)
    async def uninstall(
        self,
        interaction: discord.Interaction,
        module: app_commands.Transform[breadcord.module.Module, ModuleTransformer]
    ):
        if module.manifest.is_core_module:
            await interaction.response.send_message(embed=discord.Embed(
                colour=discord.Colour.red(),
                title='Cannot uninstall core modules!',
                description=f'If you know what you are doing, this module can be disabled instead using\n'
                            f'`/module disable module_id:{module.id}`.'
            ))
            return

        requirements_str = ", ".join(f'`{req}`' for req in module.manifest.requirements) or 'No requirements specified'
        view = views.ModuleUninstallView(cog=self, user_id=interaction.user.id, module=module)

        await interaction.response.send_message(
            embed=discord.Embed(
                colour=discord.Colour.blurple(),
                title='Uninstall this module?',
                description=module.manifest.description
            ).add_field(
                name=module.manifest.name,
                value=f'**Authors:** {escape_markdown(", ".join(module.manifest.authors))}\n'
                      f'**License:** {escape_markdown(module.manifest.license)}\n'
                      f'**Requirements:** {escape_markdown(requirements_str)}',
                inline=False
            ).set_footer(
                text=f'{module.manifest.id} v{module.manifest.version}'
            ),
            view=view
        )
        view.message = await interaction.original_response()

    @app_commands.command(description="Enable an installed module")
    @app_commands.describe(module="The id of the module to be enabled")
    @app_commands.rename(module='module_id')
    @app_commands.check(breadcord.helpers.administrator_check)
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

    @app_commands.command(description="Disable an installed module")
    @app_commands.describe(module="The id of the module to be disabled")
    @app_commands.rename(module='module_id')
    @app_commands.check(breadcord.helpers.administrator_check)
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
    await bot.add_cog(ModuleManager('modulemanager'))
