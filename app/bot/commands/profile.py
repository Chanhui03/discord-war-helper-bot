from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import NEED_REGISTER, numbered
from app.config.settings import ROOT
from app.database.repositories import (
    all_players,
    custom_mmr,
    custom_records,
    custom_stats,
    get_player,
    mvp_counts,
    scored_players,
)
from app.database.session import session_factory
from app.roles import ROLE_LABELS

RANK_ICONS = ROOT / "assets" / "ranks"

def rank_icon(tier: Optional[str]) -> Path:
    """티어 엠블럼 파일. 모르는 티어나 언랭이면 Unranked 엠블럼."""
    emblem = RANK_ICONS / f"{(tier or 'unranked').lower()}.png"
    return emblem if emblem.exists() else RANK_ICONS / "unranked.png"

class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="내점수", description="내 종합 점수와 서버 순위를 봅니다.")
    @app_commands.guild_only()
    async def profile(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
                return

            records = await custom_records(session, [player.id], interaction.guild_id)
            mmr = (await custom_mmr(session, interaction.guild_id)).get(player.id)
            recorded = await custom_stats(session, player.id, interaction.guild_id)
            mvps = await mvp_counts(session, [player.id], interaction.guild_id)
            # 순위를 매기려면 어차피 전원의 점수가 필요하다. 내 점수도 여기서 꺼내
            # 쓰면 순위와 점수가 따로 계산돼 어긋날 일이 없다.
            standings = await scored_players(
                session, await all_players(session), interaction.guild_id
            )

        stats = player.stats
        if stats is None:
            await interaction.response.send_message(
                "아직 수집된 전적이 없습니다. `/전적갱신`을 실행해주세요.", ephemeral=True
            )
            return

        custom_games, custom_wins = records.get(player.id, (0, 0))
        # stats 가 있으면 scored_players 에 반드시 들어 있다.
        place, score = next(
            (index, value)
            for index, (entry, value) in enumerate(standings, 1)
            if entry.id == player.id
        )

        rank = (
            f"{stats.tier} {stats.division} {stats.lp}LP"
            if stats.tier
            else "언랭"
        )
        embed = discord.Embed(
            title=f"{player.riot_game_name}#{player.riot_tagline}",
            description=(
                f"종합 점수 **{score:.1f}** · 서버 **{place}위** / {len(standings)}명"
            ),
            colour=discord.Colour.blurple(),
        )
        # 최고 티어는 지금과 다를 때만 보여준다. 같으면 줄만 늘어난다.
        peak = (
            f"\n-# 최고 {stats.peak_tier} {stats.peak_division or ''}".rstrip()
            if stats.peak_tier and stats.peak_tier != stats.tier
            else ""
        )
        embed.add_field(
            name="솔로랭크",
            value=f"{rank}\n{stats.wins}승 {stats.losses}패 ({stats.win_rate:.1%}){peak}",
        )
        embed.add_field(
            name="최근 폼",
            value=f"승률 {stats.recent_win_rate:.1%}\nKDA {stats.avg_kda:.2f}",
        )
        custom = (
            f"{custom_games}전 {custom_wins}승 ({custom_wins / custom_games:.1%})"
            f"\nMMR {mmr:.0f}"
            if custom_games
            else "기록 없음"
        )
        if recorded:
            games, custom_kda, avg_cs, avg_damage = recorded
            custom += (
                f"\nKDA {custom_kda:.2f} · CS {avg_cs:.0f} · 딜 {avg_damage:,.0f}"
                f"\n-# {games}경기 전적 파일 기준"
            )
        if mvps.get(player.id):
            custom += f"\n🏆 MVP {mvps[player.id]}회"
        embed.add_field(name="내전 전적", value=custom)
        embed.add_field(
            name="선호 라인",
            value=(
                f"1순위 {ROLE_LABELS.get(player.main_role, '미설정')} / "
                f"2순위 {ROLE_LABELS.get(player.secondary_role, '미설정')} / "
                f"기피 {ROLE_LABELS.get(player.avoid_role, '없음')}"
            ),
            inline=False,
        )

        embed.set_footer(text=f"갱신 {stats.updated_at:%Y-%m-%d %H:%M}")

        # 엠블럼은 봇이 들고 있는 파일을 그때그때 붙인다(외부 링크에 기대지 않는다).
        emblem = rank_icon(stats.tier)
        embed.set_thumbnail(url=f"attachment://{emblem.name}")
        await interaction.response.send_message(
            embed=embed, file=discord.File(emblem), ephemeral=True
        )

    @app_commands.command(name="랭킹", description="등록자 전원의 종합 점수 순위를 봅니다.")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            standings = await scored_players(
                session, await all_players(session), interaction.guild_id
            )

        if not standings:
            await interaction.response.send_message(
                "아직 점수를 매길 사람이 없습니다. `/전적갱신`을 먼저 실행해주세요.",
                ephemeral=True,
            )
            return

        def line(entry) -> str:
            player, score = entry
            tier = player.stats.tier
            rank = f"{tier} {player.stats.division}" if tier else "언랭"
            return (
                f"**{score:.1f}** <@{player.discord_id}> "
                f"`{player.riot_game_name}#{player.riot_tagline}` — {rank}"
            )

        embed = discord.Embed(
            title=f"종합 점수 랭킹 {len(standings)}명",
            description=numbered(standings, line),
            colour=discord.Colour.blurple(),
        )
        # 팀을 가르는 점수와 같은 값이라, 여기서 위아래로 붙은 사람끼리는
        # 밸런서도 비슷하게 본다는 뜻이다.
        embed.set_footer(text="팀 짤 때 쓰는 점수와 같습니다. /내점수 로 자세히 보세요.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
