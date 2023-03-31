import discord

import breadcord


async def administrator_check(interaction: discord.Interaction) -> bool:
    if not await interaction.client.is_owner(interaction.user):
        raise breadcord.errors.NotAdministratorError
    return True
