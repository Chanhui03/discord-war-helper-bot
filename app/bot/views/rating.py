"""경기 후 평점. 평균이 가장 높은 사람이 MVP 가 된다.

참가자와 관전자 모두 평가할 수 있어 평가자를 Discord 사용자로 다룬다.
"""

import discord

from app.database.repositories import (
    get_match,
    match_ratings,
    pick_mvp,
    ratings_by_rater,
    save_rating,
)
from app.database.session import session_factory
from app.roles import ROLE_LABELS

SCORES = list(range(1, 11))
# Discord 버튼은 한 줄에 5개까지다. 0번 줄은 대상 선택이 쓴다.
BUTTONS_PER_ROW = 5

NOT_INVOLVED = "이 내전의 참가자나 관전자만 평점을 남길 수 있습니다."

def mvp_line(match, ratings) -> str:
    """MVP 한 줄. 평점이 하나도 없으면 안내 문구."""
    winner = pick_mvp(ratings)
    if winner is None:
        return "아직 평점이 없습니다."

    entry = next(e for e in match.participants if e.player_id == winner)
    average, votes = ratings[winner]
    return (
        f"🏆 <@{entry.player.discord_id}> "
        f"`{ROLE_LABELS[entry.role]}` — 평점 **{average:.2f}** ({votes}표)"
    )

def rating_embed(match, ratings) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 평점",
        description=mvp_line(match, ratings),
        colour=discord.Colour.gold(),
    )
    for team in ("A", "B"):
        lines = []
        for entry in sorted(
            (e for e in match.participants if e.team == team),
            key=lambda e: -ratings.get(e.player_id, (0.0, 0))[0],
        ):
            average, votes = ratings.get(entry.player_id, (0.0, 0))
            score = f"**{average:.2f}** ({votes}표)" if votes else "미평가"
            lines.append(f"`{ROLE_LABELS[entry.role]:<2}` <@{entry.player.discord_id}> {score}")
        embed.add_field(name=f"{team}팀", value="\n".join(lines))
    return embed

def targets(match, rater_discord_id: int):
    """평가 대상. 본인은 뺀다. 관전자는 10명 전부를 평가한다."""
    return [
        entry
        for entry in match.participants
        if entry.player.discord_id != rater_discord_id
    ]

class TargetSelect(discord.ui.Select):
    """평가할 사람을 고른다. 이미 준 점수는 설명에 보여준다."""

    def __init__(self, match, rater_discord_id: int, given) -> None:
        options = [
            discord.SelectOption(
                label=f"{ROLE_LABELS[entry.role]} · {entry.player.riot_game_name}",
                value=str(entry.player_id),
                description=(
                    f"{given[entry.player_id]}점 매김"
                    if entry.player_id in given
                    else f"{entry.team}팀 · 아직 안 매김"
                ),
            )
            for entry in targets(match, rater_discord_id)
        ]
        super().__init__(placeholder="평가할 사람", options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.target_id = int(self.values[0])
        await interaction.response.edit_message(view=self.view)

class ScoreButton(discord.ui.Button):
    def __init__(self, score: int) -> None:
        super().__init__(
            label=str(score),
            style=discord.ButtonStyle.primary,
            row=1 + (score - 1) // BUTTONS_PER_ROW,
        )
        self.score = score

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RatingPanel" = self.view
        if view.target_id is None:
            await interaction.response.send_message(
                "먼저 평가할 사람을 골라주세요.", ephemeral=True
            )
            return

        async with session_factory() as session:
            await save_rating(
                session,
                view.match_id,
                view.rater_discord_id,
                view.target_id,
                self.score,
            )
            match = await get_match(session, view.match_id)
            given = await ratings_by_rater(
                session, view.match_id, view.rater_discord_id
            )

        view.target_id = None
        view.clear_items()
        view.build(match, given)
        await interaction.response.edit_message(content=view.summary(match, given), view=view)

class RatingPanel(discord.ui.View):
    """평가자 한 명에게만 보이는 임시 창. 여러 명을 이어서 매길 수 있다."""

    def __init__(self, match, rater_discord_id: int, given) -> None:
        super().__init__(timeout=600)
        self.match_id = match.id
        self.rater_discord_id = rater_discord_id
        self.target_id = None
        self.build(match, given)

    def build(self, match, given) -> None:
        self.add_item(TargetSelect(match, self.rater_discord_id, given))
        for score in SCORES:
            self.add_item(ScoreButton(score))

    def summary(self, match, given) -> str:
        total = len(targets(match, self.rater_discord_id))
        return f"평가할 사람을 고르고 점수를 누르세요. **{len(given)} / {total}명** 완료"

class RatingView(discord.ui.View):
    """결과 메시지에 붙는 영속 버튼. 재시작 후에도 동작한다."""

    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=None)
        self.match_id = match_id
        for item in self.children:
            item.custom_id = f"rating:{item.custom_id}:{match_id}"

    @discord.ui.button(label="평점 남기기", style=discord.ButtonStyle.primary, custom_id="rate")
    async def rate(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            # 관전자는 Riot 계정이 없으므로 Discord 사용자로만 확인한다.
            involved = any(
                entry.player.discord_id == interaction.user.id
                for entry in match.participants
            ) or any(
                viewer.discord_id == interaction.user.id for viewer in match.spectators
            )
            if not involved:
                await interaction.response.send_message(NOT_INVOLVED, ephemeral=True)
                return

            given = await ratings_by_rater(session, self.match_id, interaction.user.id)

        panel = RatingPanel(match, interaction.user.id, given)
        await interaction.response.send_message(
            panel.summary(match, given), view=panel, ephemeral=True
        )

    @discord.ui.button(label="결과 보기", style=discord.ButtonStyle.secondary, custom_id="show")
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            ratings = await match_ratings(session, self.match_id)

        await interaction.response.send_message(
            embed=rating_embed(match, ratings), ephemeral=True
        )
