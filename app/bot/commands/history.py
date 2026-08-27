"""지난 내전 기록 조회와 전적 파일 뒤늦게 채우기.

버튼으로만 결과를 넣은 내전은 승패밖에 없어 `/내전전적` 의 라인별 지표에서
빠진다. 나중에 전적 파일을 구하면 `/전적보완` 으로 메울 수 있다.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.views.result import team_lines
from app.database.repositories import (
    completed_matches,
    custom_records,
    fill_match_records,
    get_match,
    match_riot_ids,
)
from app.database.session import session_factory
from app.log import event
from app.services.replay import ReplayError, find_game, matched

log = logging.getLogger(__name__)

LIST_LIMIT = 20

MESSAGES = {
    "missing": "그 번호의 내전이 없습니다.",
    "open": "아직 결과가 확정되지 않은 내전입니다. `/결과`로 먼저 확정해주세요.",
    "mismatch": (
        "파일의 승패를 읽을 수 없습니다. 한쪽 팀이 통째로 안 맞는 경우입니다."
    ),
    "conflict": (
        "파일의 승리 팀이 기록된 승리 팀과 다릅니다. 다른 경기의 파일이거나, "
        "로비에서 진영을 바꿔 들어간 내전입니다. 승패를 덮어쓰면 내전 승률과 "
        "이후 팀 밸런싱까지 어긋나므로 아무것도 저장하지 않았습니다."
    ),
}

def has_records(match) -> bool:
    """전적 파일로 채워진 내전인지. 분당 지표의 분모가 있느냐로 본다."""
    return match.duration is not None

def winner_of(match) -> str:
    return "A" if match.team_a_score else "B"

def list_embed(matches) -> discord.Embed:
    if not matches:
        return discord.Embed(
            title="내전 기록",
            description="아직 끝난 내전이 없습니다.",
            colour=discord.Colour.greyple(),
        )

    lines = []
    for match in matches:
        mark = "전적파일 있음" if has_records(match) else "**전적파일 없음**"
        lines.append(
            f"`#{match.id}` {match.created_at:%m/%d %H:%M} · "
            f"{winner_of(match)}팀 승 · {mark}"
        )

    missing = sum(1 for match in matches if not has_records(match))
    embed = discord.Embed(
        title=f"내전 기록 {len(matches)}건",
        description="\n".join(lines),
        colour=discord.Colour.blurple(),
    )
    if missing:
        embed.set_footer(
            text=f"{missing}건은 개인 성적이 비어 있습니다. "
            "/전적보완 으로 채우면 내전전적에 반영됩니다."
        )
    else:
        embed.set_footer(text="번호로 자세히 볼 수 있습니다. 예: /내전기록 내전번호:1")
    return embed

def detail_embed(match, records) -> discord.Embed:
    winner = winner_of(match)
    length = f" · {match.duration // 60}분" if match.duration else ""
    embed = discord.Embed(
        title=f"내전 #{match.id}",
        description=(
            f"{match.created_at:%Y-%m-%d %H:%M} · **{winner}팀 승리**{length}"
        ),
        colour=discord.Colour.gold(),
    )
    for team in ("A", "B"):
        embed.add_field(
            name=f"{team}팀 ({'승' if team == winner else '패'})",
            value=team_lines(match, team, records),
            inline=False,
        )
    if not has_records(match):
        embed.set_footer(
            text="개인 성적이 없습니다. /전적보완 으로 전적 파일을 채울 수 있습니다."
        )
    return embed

class History(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="내전기록", description="이 서버에서 끝난 내전을 봅니다.")
    @app_commands.describe(match_id="자세히 볼 내전 번호. 비우면 목록을 봅니다.")
    @app_commands.rename(match_id="내전번호")
    @app_commands.guild_only()
    async def history(
        self, interaction: discord.Interaction, match_id: Optional[int] = None
    ) -> None:
        async with session_factory() as session:
            if match_id is None:
                matches = await completed_matches(
                    session, interaction.guild_id, LIST_LIMIT
                )
                embed = list_embed(matches)
            else:
                match = await get_match(session, match_id)
                if (
                    match is None
                    or not match.completed
                    or match.discord_server_id != interaction.guild_id
                ):
                    await interaction.response.send_message(
                        MESSAGES["missing"], ephemeral=True
                    )
                    return

                records = await custom_records(
                    session,
                    [entry.player_id for entry in match.participants],
                    interaction.guild_id,
                )
                embed = detail_embed(match, records)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="전적보완", description="이미 끝난 내전에 사설 전적 파일을 뒤늦게 채웁니다."
    )
    @app_commands.describe(
        match_id="채울 내전 번호. `/내전기록`에서 확인할 수 있습니다.",
        replay="LoL 클라이언트에서 받은 사설 전적 JSON",
    )
    @app_commands.rename(match_id="내전번호", replay="전적파일")
    @app_commands.guild_only()
    async def fill(
        self,
        interaction: discord.Interaction,
        match_id: int,
        replay: discord.Attachment,
    ) -> None:
        async with session_factory() as session:
            match = await get_match(session, match_id)
            if match is None or match.discord_server_id != interaction.guild_id:
                await interaction.response.send_message(
                    MESSAGES["missing"], ephemeral=True
                )
                return

            await interaction.response.defer()

            keys = await match_riot_ids(session, match)
            id_groups = [keys[entry.player_id] for entry in match.participants]
            try:
                game = find_game((await replay.read()).decode("utf-8"), id_groups)
            except (ReplayError, UnicodeDecodeError) as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return

            status, filled = await fill_match_records(session, match.id, game)
            if status != "filled":
                await interaction.followup.send(MESSAGES[status], ephemeral=True)
                return

            records = await custom_records(
                session,
                [entry.player_id for entry in filled.participants],
                interaction.guild_id,
            )
            missing = [
                entry
                for entry, ok in zip(filled.participants, matched(game, id_groups))
                if not ok
            ]
            embed = detail_embed(filled, records)
            if missing:
                embed.add_field(
                    name=f"못 맞춘 {len(missing)}명",
                    value=" ".join(f"<@{e.player.discord_id}>" for e in missing)
                    + "\n-# 개인 성적을 비워 뒀습니다. 부계정으로 뛰었다면 "
                    "`/부계정등록` 후 다시 시도해주세요.",
                    inline=False,
                )

        event(
            log,
            "records_filled",
            match=match.id,
            game=game.game_id,
            missing=len(missing),
            by=interaction.user.id,
        )
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(History(bot))
