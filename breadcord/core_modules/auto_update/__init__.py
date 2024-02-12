from __future__ import annotations

import asyncio
import shutil
import subprocess
from functools import cache
from typing import Any

from discord.ext import tasks, commands

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
        git_path()  # Error early if not git path is found
        self.loop = None

    async def cog_load(self) -> None:
        @self.settings.update_interval.observe
        def on_update_interval_changed(_, new: float) -> None:
            if self.loop is not None:
                self.loop.stop()
            # Are you kidding me? SQL injection from Git?
            self.logger.debug(f'Auto update interval now set to {new}')  # noqa: S608
            self.loop = tasks.loop(hours=new)(self.update_modules)
            self.loop.start()

        on_update_interval_changed(0, self.settings.update_interval.value)

    async def update_modules(self) -> None:
        if self.loop.current_loop == 0:
            return

        self.logger.info('Attempting to update modules')
        for module in self.bot.modules:
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
                    return
                await self.update_module(module)
            except subprocess.CalledProcessError as error:
                self.logger.error(f'Failed to fetch updates for the module {module.id!r}: {error}\n{error.stderr}')

    async def update_module(self, module: breadcord.module.Module) -> None:
        self.logger.info(f'Updating {module.id}')
        update_text = await git('pull', cwd=module.path)
        self.logger.debug(update_text.strip())
        await module.unload()
        await module.load()

        git_hash_msg = await git('log', '-1', '--format="%H %s"', cwd=module.path)
        self.logger.debug(f'Module {module.id} now on: {git_hash_msg[1:-2]}')

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx: commands.Context) -> None:
        message = await ctx.send('Updating...')
        await self.update_modules()
        await message.edit(content='Finished updating modules.')


async def setup(bot: breadcord.Bot):
    await bot.add_cog(AutoUpdate('auto_update'))
