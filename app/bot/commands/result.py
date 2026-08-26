import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.views.rating import RatingView
from app.bot.views.result import ResultView, pending_embed, result_embed
from app.database.repositories import (
    custom_records,
    finish_match_with_records,
    get_open_match,
)
from app.database.session import session_factory
from app.log import event
from app.services.replay import ReplayError, find_game, riot_id_key

log = logging.getLogger(__name__)

MISMATCH = (
    "파일의 승패가 봇이 짠 팀과 어긋납니다. 로비에서 진영을 바꿔 들어갔다면 "
    "버튼으로 승리 팀을 직접 골라주세요."
)

class Result(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="결과", description="내전 승리 팀을 확정하고 저장합니다.")
    @app_commands.describe(
        replay="LoL 클라이언트에서 받은 사설 전적 JSON. 첨부하면 개인 성적까지 기록합니다."
    )
    @app_commands.rename(replay="전적파일")
    @app_commands.guild_only()
    async def result(
        self,
        interaction: discord.Interaction,
        replay: Optional[discord.Attachment] = None,
    ) -> None:
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

            if replay is None:
                await interaction.response.send_message(
                    embed=pending_embed(match), view=ResultView(match.id)
                )
                return

            await interaction.response.defer()
            riot_ids = [
                riot_id_key(entry.player.riot_game_name, entry.player.riot_tagline)
                for entry in match.participants
            ]
            try:
                game = find_game((await replay.read()).decode("utf-8"), riot_ids)
            except (ReplayError, UnicodeDecodeError) as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return

            status, saved = await finish_match_with_records(session, match.id, game)
            if status == "mismatch":
                await interaction.followup.send(MISMATCH, ephemeral=True)
                return
            if saved is None:
                await interaction.followup.send(
                    "이미 결과가 저장된 내전입니다.", ephemeral=True
                )
                return

            records = await custom_records(
                session,
                [entry.player_id for entry in saved.participants],
                saved.discord_server_id,
            )
            embed = result_embed(saved, status, records)

        event(
            log,
            "result_imported",
            match=saved.id,
            winner=status,
            game=game.game_id,
            by=interaction.user.id,
        )
        await interaction.followup.send(embed=embed, view=RatingView(saved.id))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Result(bot))
