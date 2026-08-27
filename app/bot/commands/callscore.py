"""음성 대본으로 메인오더를 채점한다.

대본은 게임이 끝난 뒤 전사를 돌려야 나오므로 `/결과` 와 분리한다. 팀 채널이
나뉘어 있어 파일이 팀의 정답지 역할을 한다.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from app.config.settings import settings
from app.database.repositories import (
    get_match,
    review_agreement,
    match_reviews,
    recently_completed,
    save_match_reviews,
)
from app.database.session import session_factory
from app.log import event
from app.services.transcript import TranscriptError, score_calls

log = logging.getLogger(__name__)

NO_KEY = (
    "`.env` 에 `ANTHROPIC_API_KEY` 가 없습니다. 대본 채점에만 쓰는 키라, "
    "넣지 않으면 나머지 기능은 그대로 동작합니다."
)

async def read(attachment: Optional[discord.Attachment]) -> str:
    if attachment is None:
        return ""
    return (await attachment.read()).decode("utf-8")

def report_embed(match, calls, entries) -> discord.Embed:
    """채점 결과. 근거 대사를 함께 보여준다."""
    by_id = {entry.player_id: entry for entry in entries}
    embed = discord.Embed(
        title=f"내전 #{match.id} 판별 평가",
        description=(
            f"**{len(calls)}명** 채점됨"
            if calls
            else "화자를 특정할 수 있는 사람이 없었습니다."
        ),
        colour=discord.Colour.blurple(),
    )
    for call in calls:
        entry = by_id.get(call.player_id)
        if entry is None:
            continue
        embed.add_field(
            name=(
                f"{entry.team}팀 {call.rank}위 · {entry.player.riot_game_name} "
                f"— 메인오더 {call.main_call}"
            ),
            value=f"-# {call.evidence}",
            inline=False,
        )

    missing = [e for e in entries if e.player_id not in {c.player_id for c in calls}]
    if missing:
        embed.add_field(
            name=f"못 가린 {len(missing)}명",
            value=" ".join(f"<@{e.player.discord_id}>" for e in missing)
            + "\n-# 목소리를 특정하지 못해 이번 판은 건너뜁니다.",
            inline=False,
        )
    embed.set_footer(text="순위는 팀 안에서만 비교합니다. MVP 투표와 대조해 정확도를 잽니다.")
    return embed

class CallScore(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="오더채점", description="내전 음성 대본과 전적으로 판별 평가를 매깁니다."
    )
    @app_commands.describe(
        team_a="A팀 음성 대본 (.txt)",
        team_b="B팀 음성 대본 (.txt)",
        spectators="관전 채널 대본 (선택). 맥락 참고용이며 점수는 매기지 않습니다.",
        match_id="채점할 내전 번호. 비우면 가장 최근에 끝난 내전.",
    )
    @app_commands.rename(
        team_a="a팀대본", team_b="b팀대본", spectators="관전대본", match_id="내전번호"
    )
    @app_commands.guild_only()
    async def callscore(
        self,
        interaction: discord.Interaction,
        team_a: discord.Attachment,
        team_b: discord.Attachment,
        spectators: Optional[discord.Attachment] = None,
        match_id: Optional[int] = None,
    ) -> None:
        if not settings.anthropic_api_key:
            await interaction.response.send_message(NO_KEY, ephemeral=True)
            return

        async with session_factory() as session:
            if match_id is None:
                recent = await recently_completed(session, limit=1)
                match = recent[0] if recent else None
            else:
                match = await get_match(session, match_id)

            if match is None or not match.completed:
                await interaction.response.send_message(
                    "채점할 내전을 찾지 못했습니다. `/결과`로 먼저 확정해주세요.",
                    ephemeral=True,
                )
                return
            if match.discord_server_id != interaction.guild_id:
                await interaction.response.send_message(
                    "다른 서버의 내전입니다.", ephemeral=True
                )
                return

            entries = list(match.participants)
            roster_a = [e for e in entries if e.team == "A"]
            roster_b = [e for e in entries if e.team == "B"]

        await interaction.response.defer()

        try:
            transcripts = {"A팀": await read(team_a), "B팀": await read(team_b)}
            calls = await score_calls(
                roster_a,
                roster_b,
                transcripts,
                await read(spectators),
                duration=match.duration,
            )
        except (TranscriptError, UnicodeDecodeError) as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        async with session_factory() as session:
            await save_match_reviews(session, match.id, calls)
            stored = await match_reviews(session, match.id)
            # AI 순위가 사람 판단과 맞는지. 디스코드에는 안 띄우고 로그로만 남긴다.
            # 나중에 AI 가중치를 정할 때 볼 유일한 근거라 계산은 계속 한다.
            hits, total = await review_agreement(session, match.discord_server_id)

        event(
            log,
            "calls_scored",
            match=match.id,
            scored=len(calls),
            of=len(entries),
            by=interaction.user.id,
        )
        event(
            log,
            "review_agreement",
            hits=hits,
            of=total,
            rate=f"{hits / total:.0%}" if total else "n/a",
            chance="20%",
        )
        await interaction.followup.send(embed=report_embed(match, stored, entries))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CallScore(bot))
