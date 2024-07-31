from __future__ import annotations

import asyncio
import shutil
import subprocess
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any

import discord
from discord.ext import commands, tasks

import breadcord
from breadcord.helpers import make_codeblock
from breadcord.module import Module  # noqa: TCH001

if TYPE_CHECKING:
    from collections.abc import Iterable


class ModulesConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> list[Module]:
        bot: breadcord.Bot = ctx.bot
        modules = []
        for module_id in argument.lower().split():
            if module_id in ('all', '*'):
                return list(bot.modules)
            if module_id not in bot.modules:
                raise commands.BadArgument(f'Module {module_id!r} not found')
            modules.append(bot.modules.get(module_id))
        return modules


@cache
def git_path() -> str:
    if not (path := shutil.which('git')):
        raise FileNotFoundError('git executable not found')
    # A bit of blocking is fine here since this should only be uncached when the module first starts
    subprocess.check_call(  # noqa: S603
        [path, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
    )
    return path


async def git(*command_arguments: str, timeout: float = 10, **kwargs: Any) -> str:
    process = await asyncio.wait_for(
        asyncio.create_subprocess_exec(
            git_path(),
            *command_arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs,
        ),
        timeout=timeout,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode if process.returncode is not None else -1,
            ' '.join(map(str, (git_path(), *command_arguments))),
            output=stdout.decode(),
            stderr=stderr.decode(),
        )
    return stdout.decode()


class AutoUpdate(breadcord.module.ModuleCog):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        git_path()  # Error early if no git path is found
        self.loop = None

    async def cog_load(self) -> None:
        @self.settings.update_interval.observe  # type: ignore[arg-type]
        def on_update_interval_changed(_, new: float) -> None:
            if self.loop is not None:
                self.loop.stop()
            # Are you kidding me? SQL injection in logger.debug?
            self.logger.debug(f'Auto update interval set to {new} minutes')  # noqa: S608
            self.loop = tasks.loop(minutes=new)(self.update_modules)
            self.loop.start()

        async def wait_for_ready():
            while not self.bot.ready:
                await asyncio.sleep(1)
            on_update_interval_changed(0, self.settings.update_interval.value)  # type: ignore[arg-type]
        task = asyncio.create_task(wait_for_ready())
        task.add_done_callback(lambda _: self.logger.debug('Auto update task scheduled and ran'))

    async def update_modules(
        self,
        module_ids: Iterable[str] | None = None,
        colour: bool = False,
    ) -> dict[str, tuple[str, str, str]]:
        to_update = set(module_ids) if module_ids else {module.id for module in self.bot.modules if module.loaded}
        not_found = tuple(module_id for module_id in to_update if module_id not in self.bot.modules)
        if not_found:
            self.logger.warning(f'Modules not found: {", ".join(not_found)}')

        updated_modules = {}
        self.logger.info('Attempting to update modules')
        for module in self.bot.modules:
            if module.id not in to_update:
                continue
            if not module_ids and not module.loaded:
                continue
            if not await self.should_update(module):
                continue
            try:
                pull_msg, commit_hash, commit_msg = await self.update_module(module, colour=colour)
                updated_modules[module.id] = pull_msg, commit_hash, commit_msg
            except subprocess.CalledProcessError as error:
                self.logger.error(f'Failed to update module {module.id!r}: {error}\n{error.stderr}')

        if updated_modules:
            self.logger.info(f'Finished updating {len(updated_modules)} modules')
        else:
            self.logger.debug('No modules were updated')
        return updated_modules

    async def should_update(self, module: Module) -> bool:
        """Check if the module can safely be updated to the latest commit on the remote repository."""
        if not (module.path / '.git' / 'HEAD').is_file():
            return False
        try:
            await git('fetch', cwd=module.path)
            ahead = (await git('rev-list', '--count', '@{u}..HEAD', cwd=module.path)).strip()
            behind = (await git('rev-list', '--count', 'HEAD..@{u}', cwd=module.path)).strip()
        except subprocess.CalledProcessError as error:
            self.logger.error(f'Failed to check for updates for the module {module.id!r}: {error}\n{error.stderr}')
            return False

        if ahead != '0':
            self.logger.warning(f'Module {module.id} is ahead of the remote repository by {ahead} commits.')
            return False
        if behind == '0':
            self.logger.debug(f'Module {module.id} is up-to-date.')
            return False
        self.logger.debug(f'Module {module.id} is out-of-date by {behind} commits.')
        return True

    async def update_module(self, module: Module, colour: bool = False) -> tuple[str, str, str]:
        """Update a module to the latest commit on the remote repository."""
        self.logger.info(f'Updating {module.id}')
        update_text = await git(
            *(('-c', 'color.ui=always') if colour else ()), 'pull',
            cwd=module.path,
        )
        self.logger.debug(f'({module.id}) Git output:\n{update_text.strip()}')
        if module.loaded:
            await module.reload()

        git_hash_msg = (await git('log', '-1', '--format="%H %s"', cwd=module.path)).strip().strip('"')
        self.logger.debug(f'Updated {module.id} to {git_hash_msg}')

        parts = git_hash_msg.strip().split(' ', 1)
        return update_text, parts[0], ' '.join(parts[1:])

    @commands.command()
    @commands.is_owner()
    async def update(
        self,
        ctx: commands.Context,
        # A bit of a misleading name, but it makes more sense for users
        module_ids: Annotated[list[Module] | None, ModulesConverter] = None,
    ) -> None:
        """Update one or more modules to the latest commit on the remote repository.

        If no modules are specified, all loaded modules will be updated.
        If module IDs are specified, only those modules will be updated, regardless of whether they are loaded.
        If `all` or `*` is specified, all modules will be updated regardless of whether they are loaded.
        """
        response = await ctx.send('Updating...')
        updated = await self.update_modules(
            [module.id for module in module_ids] if module_ids else None,
            colour=True,
        )
        if len(updated) == 0:
            await response.edit(content='No modules were updated.')
            return

        commit_message_length = 1000
        pull_message_length = 2500
        embeds = []
        for module_id, (pull_msg, commit_hash, commit_msg) in updated.items():
            if len(commit_msg) > commit_message_length:
                commit_msg = f'{commit_msg[:commit_message_length]}...'  # noqa: PLW2901  # Would be effort to fix
            if len(pull_msg) > pull_message_length:
                pull_msg = f'{pull_msg[:pull_message_length]}...'        # noqa: PLW2901  # Would be effort to fix
            embeds.append(
                discord.Embed(
                    title=f'Updated module `{module_id}`',
                    description='\n'.join((
                        f'**Latest commit message**: {discord.utils.escape_markdown(commit_msg)}',
                        make_codeblock(
                            # Discord doesn't understand that nothing means reset
                            pull_msg.replace('\x1b[m', '\x1b[0m'),
                            lang='ansi',
                        ),
                    )),
                    color=discord.Colour.green(),
                ).set_footer(text=f'Now on commit {commit_hash}'),
            )
        max_embeds = 10
        if len(embeds) > max_embeds:
            embeds = embeds[:max_embeds]
            embeds.append(discord.Embed(
                title='And more...',
                description=f'{len(updated) - len(embeds)} more modules were updated.',
                color=discord.Colour.orange(),
            ))
        await response.edit(
            content='Finished updating modules.',
            embeds=embeds,
        )


async def setup(bot: breadcord.Bot):
    await bot.add_cog(AutoUpdate('auto_update'))
