import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import need_manage_guild
from app.bot.views.result import ResultView, pending_embed
from app.database.repositories import get_open_match
from app.database.session import session_factory

class Result(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="결과", description="내전 승리 팀을 확정하고 저장합니다.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def result(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            match = await get_open_match(session, interaction.guild_id)
            if match is None:
                await interaction.response.send_message(
                    "진행 중인 내전이 없습니다.", ephemeral=True
                )
                return
            if not all(entry.team for entry in match.participants):
                await interaction.response.send_message(
                    "먼저 팀 생성을 완료해주세요.", ephemeral=True
                )
                return
            embed = pending_embed(match)

        await interaction.response.send_message(embed=embed, view=ResultView(match.id))

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(need_manage_guild("결과 확정"), ephemeral=True)
            return
        raise error

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Result(bot))
