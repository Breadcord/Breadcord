from __future__ import annotations

import asyncio
import shutil
import subprocess
from functools import cache
from typing import Any

import discord
from discord.ext import commands, tasks

import breadcord


@cache
def git_path() -> str:
    if not (path := shutil.which('git')):
        raise FileNotFoundError('git executable not found')
    # A bit of blocking is fine here since this should only be uncached when the module first starts
    subprocess.check_call(
        [path, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,  # noqa: S603
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
            process.returncode,
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
        @self.settings.update_interval.observe
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
            on_update_interval_changed(0, self.settings.update_interval.value)
        task = asyncio.create_task(wait_for_ready())
        task.add_done_callback(lambda _: self.logger.debug('Auto update task scheduled and ran'))

    async def update_modules(self) -> dict[str, tuple[str, str, str]]:
        updated_modules = {}
        self.logger.info('Attempting to update modules')
        for module in self.bot.modules:
            if not module.loaded:
                continue
            if not (module.path / '.git' / 'HEAD').is_file():
                continue
            try:
                await git('fetch', cwd=module.path)
                if (
                    await git('rev-parse', '@{u}', cwd=module.path)
                    ==
                    await git('rev-parse', 'HEAD', cwd=module.path)
                ):
                    self.logger.debug(f'Module {module.id} is up-to-date.')
                    continue
                self.logger.warning(f'Module {module.id} is out-of-date.')
                pull_msg, commit_hash, commit_msg = await self.update_module(module)
                updated_modules[module.id] = pull_msg, commit_hash, commit_msg
            except subprocess.CalledProcessError as error:
                self.logger.error(f'Failed to fetch updates for the module {module.id!r}: {error}\n{error.stderr}')

        if updated_modules:
            self.logger.info(f'Finished updating len({updated_modules}) modules')
        else:
            self.logger.debug('No modules were updated')
        return updated_modules

    async def update_module(self, module: breadcord.module.Module) -> tuple[str, str, str]:
        self.logger.info(f'Updating {module.id}')
        update_text = await git('pull', cwd=module.path)
        self.logger.debug(f'({module.id}) Git output:\n{update_text.strip()}')
        await module.reload()

        git_hash_msg = (await git('log', '-1', '--format="%H %s"', cwd=module.path)).strip().strip('"')
        self.logger.debug(f'Updated {module.id} to {git_hash_msg}')

        parts = git_hash_msg.strip().split(' ', 1)
        return update_text, parts[0], ' '.join(parts[1:])

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx: commands.Context) -> None:
        message = await ctx.send('Updating...')
        updated = await self.update_modules()
        if len(updated) == 0:
            await message.edit(content='No modules were updated.')
        else:
            embeds = [
                discord.Embed(
                    title=f'Updated module `{module_id}`',
                    description='\n'.join(filter(bool, (
                        f'**Latest commit message**: {discord.utils.escape_markdown(commit_msg)}',
                        f'```\n{pull_msg}\n```' if pull_msg else None,
                    ))),
                    color=discord.Colour.green(),
                ).set_footer(text=f'Now on commit {commit_hash}')
                for module_id, (pull_msg, commit_hash, commit_msg) in updated.items()
            ]

            max_embeds = 10
            if len(embeds) > max_embeds:
                embeds = embeds[:max_embeds-1]
                embeds.append(discord.Embed(
                    title='And more...',
                    description=f'{len(updated) - len(embeds)} more modules were updated.',
                    color=discord.Colour.orange(),
                ))
            await message.edit(
                content='Finished updating modules.',
                embeds=embeds,
            )


async def setup(bot: breadcord.Bot):
    await bot.add_cog(AutoUpdate('auto_update'))
