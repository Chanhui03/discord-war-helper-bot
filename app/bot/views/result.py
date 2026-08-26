import logging

import discord

from app.bot.views.rating import RatingView
from app.database.repositories import custom_records, finish_match
from app.database.session import session_factory
from app.log import event
from app.roles import ROLE_LABELS, ROLES

log = logging.getLogger(__name__)

def team_lines(match, team: str, records=None) -> str:
    rows = sorted(
        (entry for entry in match.participants if entry.team == team),
        key=lambda entry: ROLES.index(entry.role),
    )
    lines = []
    for entry in rows:
        line = f"`{ROLE_LABELS[entry.role]:<2}` <@{entry.player.discord_id}>"
        if records is not None:
            games, wins = records.get(entry.player_id, (0, 0))
            line += f" — 내전 {games}전 {wins}승 ({wins / games:.0%})" if games else " — 내전 첫 경기"
        lines.append(line)
        # 사설 전적 파일로 확정한 내전만 개인 성적이 채워져 있다.
        if entry.kills is not None:
            lines.append(
                f"-# {entry.kills}/{entry.deaths}/{entry.assists} · "
                f"CS {entry.cs} · 딜 {entry.damage:,} · 골드 {entry.gold:,}"
            )
    return "\n".join(lines)

def pending_embed(match) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 결과 입력",
        description="승리한 팀을 선택해주세요.",
        colour=discord.Colour.greyple(),
    )
    embed.add_field(name="A팀", value=team_lines(match, "A"))
    embed.add_field(name="B팀", value=team_lines(match, "B"))
    return embed

def result_embed(match, winner: str, records, missing=()) -> discord.Embed:
    """missing 은 전적 파일에서 못 찾은 참가자들. 승패만 기록된 사람들이다."""
    embed = discord.Embed(
        title=f"내전 #{match.id} 결과",
        description=f"**{winner}팀 승리**",
        colour=discord.Colour.gold(),
    )
    for team in ("A", "B"):
        mark = "승" if team == winner else "패"
        embed.add_field(
            name=f"{team}팀 ({mark})", value=team_lines(match, team, records), inline=False
        )
    if missing:
        embed.add_field(
            name=f"못 맞춘 {len(missing)}명",
            value=" ".join(f"<@{entry.player.discord_id}>" for entry in missing)
            + "\n-# 승패만 기록됐습니다. Riot ID 가 바뀌었다면 `/전적등록`으로 다시 연결해주세요.",
            inline=False,
        )
    return embed

class ResultView(discord.ui.View):
    """재시작 후에도 동작하도록 timeout 없이 match_id 를 custom_id 에 담는다."""

    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=None)
        self.match_id = match_id
        for item in self.children:
            item.custom_id = f"result:{item.custom_id}:{match_id}"

    async def _finish(self, interaction: discord.Interaction, winner: str) -> None:
        async with session_factory() as session:
            match = await finish_match(session, self.match_id, winner)
            if match is None:
                await interaction.response.send_message(
                    "이미 결과가 저장된 내전입니다.", ephemeral=True
                )
                return
            records = await custom_records(
                session,
                [entry.player_id for entry in match.participants],
                match.discord_server_id,
            )
            embed = result_embed(match, winner, records)

        event(
            log,
            "result_saved",
            match=self.match_id,
            winner=winner,
            by=interaction.user.id,
        )
        self.stop()
        await interaction.response.edit_message(
            embed=embed, view=RatingView(self.match_id)
        )

    @discord.ui.button(label="A팀 승리", style=discord.ButtonStyle.success, custom_id="a")
    async def team_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, "A")

    @discord.ui.button(label="B팀 승리", style=discord.ButtonStyle.success, custom_id="b")
    async def team_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, "B")
