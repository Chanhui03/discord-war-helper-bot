import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import numbered
from app.database.repositories import aliases_for, all_players
from app.database.session import session_factory

def roster_embed(players, aliases=None) -> discord.Embed:
    """갱신이 최근인 순서로 등록자를 나열한다. 갱신 기록이 없는 사람은 뒤로 보낸다."""
    ordered = sorted(
        (player for player in players if player.stats),
        key=lambda player: player.stats.updated_at,
        reverse=True,
    ) + [player for player in players if not player.stats]

    extra = aliases or {}

    def line(player) -> str:
        alias_note = (
            f" (+부계정 {len(extra[player.id])})" if extra.get(player.id) else ""
        )
        refreshed = (
            f"갱신 {player.stats.updated_at:%Y-%m-%d}"
            if player.stats
            else "갱신 기록 없음"
        )
        return (
            f"<@{player.discord_id}> "
            f"`{player.riot_game_name}#{player.riot_tagline}`"
            f"{alias_note} — {refreshed}"
        )

    return discord.Embed(
        title=f"등록된 게이머 {len(ordered)}명",
        description=numbered(ordered, line) or "아직 등록한 사람이 없습니다.",
        colour=discord.Colour.blurple(),
    )

class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="등록목록", description="등록된 게이머와 최근 갱신 날짜를 봅니다.")
    async def roster(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            players = await all_players(session)
            aliases = await aliases_for(session, [player.id for player in players])

        await interaction.response.send_message(
            embed=roster_embed(players, aliases), ephemeral=True
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roster(bot))
