import discord
from discord import app_commands
from discord.ext import commands

from app.bot.views.role_select import RolePreferenceView, describe
from app.database.repositories import get_player
from app.database.session import session_factory

class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="라인설정", description="주라인과 부라인을 설정합니다.")
    async def set_roles(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)

        if player is None:
            await interaction.response.send_message(
                "먼저 `/등록`으로 Riot 계정을 연결해주세요.", ephemeral=True
            )
            return

        view = RolePreferenceView(
            player.discord_id, player.main_role, player.secondary_role
        )
        await interaction.response.send_message(
            describe(player.main_role, player.secondary_role),
            view=view,
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
