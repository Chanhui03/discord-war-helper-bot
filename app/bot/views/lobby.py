import asyncio

import discord

from app.database.repositories import (
    custom_records,
    get_match,
    get_player,
    join_match,
    leave_match,
    save_teams,
)
from app.database.session import session_factory
from app.roles import ROLE_LABELS, ROLES
from app.services.matchmaking import LOBBY_SIZE, find_best_teams
from app.services.stats import build_profile

def lobby_embed(match) -> discord.Embed:
    count = len(match.participants)
    lines = [
        f"{index}. <@{entry.player.discord_id}> "
        f"({entry.player.riot_game_name}#{entry.player.riot_tagline})"
        for index, entry in enumerate(match.participants, 1)
    ]

    embed = discord.Embed(
        title=f"내전 모집 #{match.id}",
        description=f"**{count} / {LOBBY_SIZE}명**",
        colour=discord.Colour.green() if count == LOBBY_SIZE else discord.Colour.greyple(),
    )
    embed.add_field(
        name="참가자",
        value="\n".join(lines) if lines else "아직 참가자가 없습니다.",
    )
    if count == LOBBY_SIZE:
        embed.set_footer(text="인원이 모두 찼습니다.")
    return embed

def teams_embed(match, result) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 팀 구성",
        description=(
            f"밸런스 점수 **{result.score:.2f}** "
            f"({result.splits}개 분할 · {result.evaluated:,}개 배정 평가)\n"
            + " · ".join(
                f"{key} {value:.1f}" for key, value in result.breakdown.items()
            )
        ),
        colour=discord.Colour.blurple(),
    )

    by_id = {entry.player_id: entry for entry in match.participants}
    for label, team in (("A팀", result.team_a), ("B팀", result.team_b)):
        order = {role: index for index, role in enumerate(ROLES)}
        lines = [
            f"`{ROLE_LABELS[role]:<2}` <@{by_id[member.player_id].player.discord_id}> "
            f"({team.role_power[role]:.1f})"
            for member, role in sorted(team.members, key=lambda item: order[item[1]])
        ]
        embed.add_field(
            name=f"{label} — 전투력 {team.power:.1f}",
            value="\n".join(lines),
        )
    return embed

class LobbyView(discord.ui.View):
    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=1800)
        self.match_id = match_id

    async def _update(self, interaction: discord.Interaction, action) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.response.send_message(
                    "먼저 `/등록`으로 Riot 계정을 연결해주세요.", ephemeral=True
                )
                return

            status, match = await action(session, self.match_id, player.id)
            embed = lobby_embed(match) if match else None

        messages = {
            "closed": "이미 종료된 내전입니다.",
            "already": "이미 참가 중입니다.",
            "full": f"인원이 모두 찼습니다. ({LOBBY_SIZE}명)",
            "absent": "참가 중이 아닙니다.",
        }
        if status in messages:
            await interaction.response.send_message(messages[status], ephemeral=True)
            return

        self.generate.disabled = len(match.participants) < LOBBY_SIZE
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="참가", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, join_match)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, leave_match)

    @discord.ui.button(label="팀 생성", style=discord.ButtonStyle.primary, disabled=True)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "팀 생성은 서버 관리 권한이 있는 사람만 할 수 있습니다.", ephemeral=True
            )
            return

        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            if match is None or len(match.participants) < LOBBY_SIZE:
                await interaction.response.send_message(
                    f"참가자가 {LOBBY_SIZE}명이어야 합니다.", ephemeral=True
                )
                return
            records = await custom_records(
                session,
                [entry.player_id for entry in match.participants],
                match.discord_server_id,
            )
            profiles = [
                build_profile(entry.player, *records.get(entry.player_id, (0, 0)))
                for entry in match.participants
            ]

        # 조합 탐색은 1초 이상 걸릴 수 있어 이벤트 루프를 막지 않는다.
        await interaction.response.defer()
        result = await asyncio.to_thread(find_best_teams, profiles)

        async with session_factory() as session:
            match = await save_teams(session, self.match_id, result)
            embed = teams_embed(match, result)

        self.stop()
        await interaction.edit_original_response(embed=embed, view=None)
