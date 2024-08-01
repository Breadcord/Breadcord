import breadcord.module


class OutOfBoxExperience(breadcord.module.ModuleCog):
    async def cog_load(self) -> None:
        app_info = await self.bot.application_info()
        self.logger.info(
            f'🎉 Welcome to Breadcord! Check your DMs (@{app_info.owner.name}) or run '
            f'{self.bot.settings.command_prefixes.value[0]}setup to get started.',
        )
        self.logger.info(
            "🔕 If you already know what you're doing, disable the 'oobe' module to skip the setup wizard.",
        )

        await app_info.owner.send('This is a placeholder message for the OOBE setup wizard.')


async def setup(bot: breadcord.Bot):
    await bot.add_cog(OutOfBoxExperience('oobe'))
