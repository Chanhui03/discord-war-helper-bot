import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import NEED_REGISTER
from app.bot.views.role_select import RolePreferenceView, describe
from app.database.repositories import get_player
from app.database.session import session_factory

class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="라인설정", description="선호라인과 기피라인을 설정합니다.")
    async def set_roles(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)

        if player is None:
            await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
            return

        view = RolePreferenceView(
            player.discord_id,
            player.main_role,
            player.secondary_role,
            player.avoid_role,
        )
        await interaction.response.send_message(
            describe(player.main_role, player.secondary_role, player.avoid_role),
            view=view,
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
