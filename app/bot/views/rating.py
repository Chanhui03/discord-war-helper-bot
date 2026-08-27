"""경기 후 MVP 투표.

이긴 팀과 관전자가 한 명씩 고른다. 9명에게 1~10 을 매기던 방식은 아무도 끝까지
하지 않아 표가 비었다(실제로 한 판에 3~7명만 참여했다). 한 번 누르면 끝나는
쪽이 실제로 모인다.

이 표는 밸런싱에 쓰지 않는다. AI 가 대본과 전적을 읽고 매긴 순위가 사람 판단과
맞는지 확인하는 정답지로 쓴다.
"""

import logging

import discord

from app.bot.views.persistent import PersistentView
from app.bot.views.teams import TeamEditView, match_profiles, series_embed
from app.database.repositories import (
    create_rematch,
    get_match,
    pick_vote_mvp,
    save_vote,
    vote_by,
    vote_counts,
)
from app.database.session import session_factory
from app.log import event
from app.roles import ROLE_LABELS
from app.services.matchmaking import score_assignment

log = logging.getLogger(__name__)

NOT_ALLOWED = "이긴 팀과 관전자만 MVP 를 뽑을 수 있습니다."
NO_WINNER = "아직 결과가 확정되지 않았습니다."

REMATCH_FAILED = {
    "open": NO_WINNER,
    "busy": "이미 진행 중인 내전이 있습니다. 그 내전을 끝낸 뒤에 눌러주세요.",
}

def winners(match):
    return [entry for entry in match.participants if entry.win]

def can_vote(match, discord_id: int) -> bool:
    """이긴 팀 또는 관전자. 진 팀에게는 주지 않는다.

    진 직후의 표는 감정이 섞이거나 기권이 많아 정답지로 쓰기 어렵다.
    """
    return any(e.player.discord_id == discord_id for e in winners(match)) or any(
        viewer.discord_id == discord_id for viewer in match.spectators
    )

def mvp_line(match, counts, spectator_counts) -> str:
    winner = pick_vote_mvp(counts, spectator_counts)
    if winner is None:
        return "아직 표가 갈리지 않았습니다." if counts else "아직 표가 없습니다."

    entry = next(e for e in match.participants if e.player_id == winner)
    return (
        f"🏆 <@{entry.player.discord_id}> "
        f"`{ROLE_LABELS[entry.role]}` — {counts[winner]}표"
    )

def vote_embed(match, counts, spectator_counts) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} MVP",
        description=mvp_line(match, counts, spectator_counts),
        colour=discord.Colour.gold(),
    )
    lines = [
        f"`{ROLE_LABELS[entry.role]:<2}` <@{entry.player.discord_id}> "
        f"— {counts.get(entry.player_id, 0)}표"
        for entry in sorted(
            winners(match), key=lambda e: -counts.get(e.player_id, 0)
        )
    ]
    embed.add_field(name="승리 팀", value="\n".join(lines) or "없음")
    embed.set_footer(text=f"총 {sum(counts.values())}표 · 동점이면 관전자 표로 가릅니다")
    return embed

class MvpSelect(discord.ui.Select):
    """이긴 팀 중 한 명. 본인은 뺀다."""

    def __init__(self, match, voter_discord_id: int, given) -> None:
        options = [
            discord.SelectOption(
                label=f"{ROLE_LABELS[entry.role]} · {entry.player.riot_game_name}",
                value=str(entry.player_id),
                default=given == entry.player_id,
            )
            for entry in winners(match)
            if entry.player.discord_id != voter_discord_id
        ]
        super().__init__(placeholder="이번 판 MVP", options=options)
        self.match_id = match.id

    async def callback(self, interaction: discord.Interaction) -> None:
        target_id = int(self.values[0])

        async with session_factory() as session:
            await save_vote(session, self.match_id, interaction.user.id, target_id)
            match = await get_match(session, self.match_id)
            counts, by_spectator = await vote_counts(session, self.match_id)

        await interaction.response.edit_message(
            content=f"<@{target_id}> 에게 투표했습니다. 다시 고르면 바뀝니다.",
            embed=vote_embed(match, counts, by_spectator),
            view=None,
        )

class RatingView(PersistentView):
    """결과 메시지에 붙는 영속 버튼."""

    PREFIX = "rating"

    @discord.ui.button(label="MVP 뽑기", style=discord.ButtonStyle.primary, custom_id="rate")
    async def rate(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            if not match.completed:
                await interaction.response.send_message(NO_WINNER, ephemeral=True)
                return
            if not can_vote(match, interaction.user.id):
                await interaction.response.send_message(NOT_ALLOWED, ephemeral=True)
                return

            mine = await vote_by(session, self.match_id, interaction.user.id)

        view = discord.ui.View(timeout=600)
        view.add_item(MvpSelect(match, interaction.user.id, mine))
        note = (
            "이번 판에서 제일 잘한 사람을 골라주세요."
            if mine is None
            else f"지금 <@{mine}> 에게 투표했습니다. 바꾸려면 다시 고르세요."
        )
        await interaction.response.send_message(note, view=view, ephemeral=True)

    @discord.ui.button(label="팀 그대로", style=discord.ButtonStyle.success, custom_id="again")
    async def again(self, interaction: discord.Interaction, button: discord.ui.Button):
        """같은 팀·라인으로 다음 판을 열고, 그동안 쓴 챔피언을 보여준다."""
        # 챔피언 이름표를 처음 받아올 때는 3초를 넘길 수 있다.
        await interaction.response.defer(thinking=True)

        async with session_factory() as session:
            status, match = await create_rematch(session, self.match_id)
            if match is None:
                await interaction.followup.send(REMATCH_FAILED[status], ephemeral=True)
                return

            profiles = await match_profiles(session, match)
            assignment = {
                entry.player_id: (entry.team, entry.role)
                for entry in match.participants
            }
            embed = await series_embed(
                session, match, score_assignment(profiles, assignment)
            )

        event(
            log,
            "rematch_created",
            match=match.id,
            previous=self.match_id,
            by=interaction.user.id,
        )
        await interaction.followup.send(embed=embed, view=TeamEditView(match))

    @discord.ui.button(label="결과 보기", style=discord.ButtonStyle.secondary, custom_id="show")
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            counts, by_spectator = await vote_counts(session, self.match_id)

        await interaction.response.send_message(
            embed=vote_embed(match, counts, by_spectator), ephemeral=True
        )
