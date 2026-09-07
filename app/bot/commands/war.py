import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.views.lobby import LobbyView, lobby_embed
from app.database.repositories import (
    create_match,
    delete_match,
    get_match,
    get_open_match,
)
from app.database.session import session_factory
from app.log import event

log = logging.getLogger(__name__)

class War(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="내전", description="내전 참가자를 모집합니다.")
    @app_commands.guild_only()
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

    @app_commands.command(name="내전취소", description="진행 중인 내전을 취소합니다.")
    @app_commands.guild_only()
    async def cancel(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            match = await get_open_match(session, interaction.guild_id)
            if match is None:
                await interaction.response.send_message(
                    "진행 중인 내전이 없습니다.", ephemeral=True
                )
                return

            # 삭제 후에는 match 를 읽을 수 없어 미리 챙긴다.
            match_id, joined = match.id, len(match.participants)
            await delete_match(session, match_id)

        event(log, "match_deleted", match=match_id, by=interaction.user.id)
        await interaction.response.send_message(
            f"내전 #{match_id} 을(를) 취소했습니다. (참가자 {joined}명)"
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(War(bot))
