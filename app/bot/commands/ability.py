import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import numbered
from app.database.repositories import (
    all_players,
    get_player,
    save_trait,
    trait_scores,
)
from app.database.session import session_factory
from app.traits import CHAMPS, FOLLOW, MAIN_CALL, summary

def status_embed(players, scores) -> discord.Embed:
    """평가가 적게 쌓인 사람부터 나열한다. 아직 아무도 안 매긴 사람이 맨 위로 온다."""

    def votes(player):
        return sum(count for _, count in scores.get(player.id, {}).values())

    ordered = sorted(players, key=lambda player: (votes(player), player.riot_game_name))

    def line(player) -> str:
        return f"<@{player.discord_id}> — {summary(scores.get(player.id, {}))}"

    return discord.Embed(
        title=f"능력평가 현황 {len(ordered)}명",
        description=numbered(ordered, line) or "아직 등록한 사람이 없습니다.",
        colour=discord.Colour.blurple(),
    )

class Ability(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="능력평가", description="다른 사람의 메인오더·오더수행·챔피언폭을 1~10 으로 매깁니다.")
    @app_commands.describe(
        member="평가할 사람",
        main_call="1~10 · 판을 읽고 콜을 내리는 능력 (상위 2명을 서로 다른 팀에 둡니다)",
        follow="1~10 · 남의 콜에 맞춰 움직이는 능력 (점수에 그대로 더합니다)",
        champs="1~10 · 저격밴을 맞아도 꺼낼 카드가 있는지",
    )
    @app_commands.rename(
        member="대상", main_call="메인오더", follow="오더수행", champs="챔피언폭"
    )
    @app_commands.guild_only()
    async def rate(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        main_call: app_commands.Range[int, 1, 10] = None,
        follow: app_commands.Range[int, 1, 10] = None,
        champs: app_commands.Range[int, 1, 10] = None,
    ) -> None:
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "자기 자신은 평가할 수 없습니다.", ephemeral=True
            )
            return
        if main_call is None and follow is None and champs is None:
            await interaction.response.send_message(
                "메인오더·오더수행·챔피언폭 중 하나는 입력해주세요.", ephemeral=True
            )
            return

        async with session_factory() as session:
            player = await get_player(session, member.id)
            if player is None:
                await interaction.response.send_message(
                    f"{member.display_name} 님은 아직 `/전적등록`을 하지 않았습니다.",
                    ephemeral=True,
                )
                return

            for trait, score in (
                (MAIN_CALL, main_call), (FOLLOW, follow), (CHAMPS, champs)
            ):
                if score is not None:
                    await save_trait(session, player.id, interaction.user.id, trait, score)

            scores = (await trait_scores(session, [player.id])).get(player.id, {})

        await interaction.response.send_message(
            f"<@{member.id}> — {summary(scores)}", ephemeral=True
        )

    @app_commands.command(
        name="능력평가현황", description="등록한 사람들의 메인오더·오더수행·챔피언폭을 한눈에 봅니다."
    )
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            players = await all_players(session)
            scores = await trait_scores(session, [player.id for player in players])

        await interaction.response.send_message(
            embed=status_embed(players, scores), ephemeral=True
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ability(bot))
