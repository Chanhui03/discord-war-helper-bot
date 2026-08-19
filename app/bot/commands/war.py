import discord
from discord import app_commands
from discord.ext import commands

from app.bot.views.lobby import LobbyView, lobby_embed
from app.database.repositories import create_match, get_match, get_open_match
from app.database.session import session_factory

class War(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="내전", description="내전 참가자를 모집합니다.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def war(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            existing = await get_open_match(session, interaction.guild_id)
            if existing is not None:
                await interaction.response.send_message(
                    f"이미 진행 중인 내전이 있습니다. (#{existing.id})", ephemeral=True
                )
                return

            match = await create_match(session, interaction.guild_id)
            match = await get_match(session, match.id)

        await interaction.response.send_message(
            embed=lobby_embed(match), view=LobbyView(match.id)
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "내전 생성은 서버 관리 권한이 있는 사람만 할 수 있습니다.", ephemeral=True
            )
            return
        raise error

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(War(bot))
