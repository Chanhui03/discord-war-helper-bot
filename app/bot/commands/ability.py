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
from app.traits import CHAMPS, SHOTCALL, summary

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

    @app_commands.command(name="능력평가", description="다른 사람의 오더능력과 챔피언폭을 1~10 으로 매깁니다.")
    @app_commands.describe(
        member="평가할 사람", shotcall="1~10 (팀 배정에서 상위 2명을 갈라 놓습니다)",
        champs="1~10",
    )
    @app_commands.rename(member="대상", shotcall="오더능력", champs="챔피언폭")
    @app_commands.guild_only()
    async def rate(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        shotcall: app_commands.Range[int, 1, 10] = None,
        champs: app_commands.Range[int, 1, 10] = None,
    ) -> None:
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "자기 자신은 평가할 수 없습니다.", ephemeral=True
            )
            return
        if shotcall is None and champs is None:
            await interaction.response.send_message(
                "오더능력이나 챔피언폭 중 하나는 입력해주세요.", ephemeral=True
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

            for trait, score in ((SHOTCALL, shotcall), (CHAMPS, champs)):
                if score is not None:
                    await save_trait(session, player.id, interaction.user.id, trait, score)

            scores = (await trait_scores(session, [player.id])).get(player.id, {})

        await interaction.response.send_message(
            f"<@{member.id}> — {summary(scores)}", ephemeral=True
        )

    @app_commands.command(
        name="능력평가현황", description="등록한 사람들의 오더능력·챔피언폭을 한눈에 봅니다."
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
