"""팀 구성 메시지: 밸런싱 결과를 보여주고 자리를 바꿀 수 있게 한다."""

import logging

import discord

from app.database.repositories import (
    call_averages,
    custom_records,
    rank_averages,
    last_assigned_roles,
    swap_team_slots,
    trait_scores,
)
from app.database.session import session_factory
from app.log import event
from app.roles import ROLE_LABELS, ROLES
from app.services.matchmaking import score_assignment
from app.services.stats import build_profile

log = logging.getLogger(__name__)

def teams_embed(match, result) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 팀 구성",
        description=(
            f"밸런스 점수 **{result.score:.1f}** "
            + (
                f"({result.splits}개 분할 · {result.evaluated:,}개 배정 평가)\n"
                if result.evaluated
                else "(직접 바꾼 구성)\n"
            )
            + " · ".join(
                f"{key} {value:.1f}" for key, value in result.breakdown.items()
            )
        ),
        colour=discord.Colour.blurple(),
    )
    if not result.bans_honoured:
        embed.add_field(
            name="⚠️ 기피 라인 금지 미적용",
            value="이번 참가자 구성으로는 기피 라인을 모두 피할 수 없었습니다.",
            inline=False,
        )
    if not result.leaders_split:
        embed.add_field(
            name="⚠️ 메인오더 분리 미적용",
            value="메인오더 상위 2명을 서로 다른 팀에 둘 수 없었습니다.",
            inline=False,
        )

    by_id = {entry.player_id: entry for entry in match.participants}
    order = {role: index for index, role in enumerate(ROLES)}
    for label, team in (("A팀", result.team_a), ("B팀", result.team_b)):
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

async def match_profiles(session, match):
    """이 내전 참가자들의 밸런싱용 스냅샷. 팀 생성과 팀 수정이 같이 쓴다."""
    player_ids = [entry.player_id for entry in match.participants]
    records = await custom_records(session, player_ids, match.discord_server_id)
    previous = await last_assigned_roles(
        session, player_ids, match.discord_server_id, exclude_match_id=match.id
    )
    traits = await trait_scores(session, player_ids)
    calls = await call_averages(session, player_ids, match.discord_server_id)
    ranks = await rank_averages(session, player_ids, match.discord_server_id)
    return [
        build_profile(
            entry.player,
            *records.get(entry.player_id, (0, 0)),
            last_role=previous.get(entry.player_id),
            traits=traits.get(entry.player_id),
            recorded_call=calls.get(entry.player_id, (None, 0))[0],
            ranks=ranks.get(entry.player_id),
        )
        for entry in match.participants
    ]

class SwapSelect(discord.ui.Select):
    """고른 두 사람의 자리(팀·라인)를 맞바꾼다. 자리 교환이라 라인 구성은 유지된다."""

    def __init__(self, match) -> None:
        options = [
            discord.SelectOption(
                label=f"{entry.player.riot_game_name}#{entry.player.riot_tagline}",
                value=str(entry.player_id),
                description=f"{entry.team}팀 · {ROLE_LABELS[entry.role]}",
            )
            for entry in match.participants
        ]
        super().__init__(
            placeholder="자리를 바꿀 두 명을 고르세요",
            min_values=2,
            max_values=2,
            options=options,
            custom_id=f"teams:swap:{match.id}",
        )
        self.match_id = match.id

    async def callback(self, interaction: discord.Interaction) -> None:
        first, second = (int(value) for value in self.values)

        async with session_factory() as session:
            match = await swap_team_slots(session, self.match_id, first, second)
            if match is None:
                await interaction.response.send_message(
                    "이미 결과가 확정됐거나 없는 내전입니다.", ephemeral=True
                )
                return

            profiles = await match_profiles(session, match)
            assignment = {
                entry.player_id: (entry.team, entry.role)
                for entry in match.participants
            }
            embed = teams_embed(match, score_assignment(profiles, assignment))

        event(
            log,
            "teams_edited",
            match=self.match_id,
            by=interaction.user.id,
            swapped=f"{first}-{second}",
        )
        await interaction.response.edit_message(embed=embed, view=TeamEditView(match))

class TeamEditView(discord.ui.View):
    """팀 생성 뒤에도 서버 인원 누구나 자리를 바꿀 수 있게 한다."""

    def __init__(self, match) -> None:
        super().__init__(timeout=None)
        self.add_item(SwapSelect(match))
