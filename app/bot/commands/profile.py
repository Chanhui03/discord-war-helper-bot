import discord
from discord import app_commands
from discord.ext import commands

from app.database.repositories import get_player
from app.database.session import session_factory
from app.roles import ROLE_LABELS
from app.services.stats import player_score

class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="전적", description="저장된 전적과 라인별 지표를 봅니다.")
    async def profile(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)

        if player is None:
            await interaction.response.send_message(
                "먼저 `/등록`으로 Riot 계정을 연결해주세요.", ephemeral=True
            )
            return

        stats = player.stats
        if stats is None:
            await interaction.response.send_message(
                "아직 수집된 전적이 없습니다. `/등록`을 다시 실행해주세요.", ephemeral=True
            )
            return

        roles = {row.role: row for row in player.roles}
        main_row = roles.get(player.main_role)
        score = player_score(
            stats.tier,
            stats.division,
            stats.lp,
            stats.recent_win_rate,
            stats.avg_kda,
            main_row.role_score if main_row else None,
        )

        rank = (
            f"{stats.tier} {stats.division} {stats.lp}LP"
            if stats.tier
            else "언랭"
        )
        embed = discord.Embed(
            title=f"{player.riot_game_name}#{player.riot_tagline}",
            description=f"종합 점수 **{score:.1f}**",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(
            name="솔로랭크",
            value=f"{rank}\n{stats.wins}승 {stats.losses}패 ({stats.win_rate:.1%})",
        )
        embed.add_field(
            name="최근 폼",
            value=f"승률 {stats.recent_win_rate:.1%}\nKDA {stats.avg_kda:.2f}",
        )
        embed.add_field(
            name="선호 라인",
            value=(
                f"주 {ROLE_LABELS.get(player.main_role, '미설정')} / "
                f"부 {ROLE_LABELS.get(player.secondary_role, '미설정')}"
            ),
            inline=False,
        )

        if roles:
            lines = [
                f"`{ROLE_LABELS[row.role]:<2}` {row.games}전 {row.win_rate:.0%} "
                f"KDA {row.avg_kda:.2f} · 점수 {row.role_score:.1f}"
                for row in sorted(
                    roles.values(), key=lambda r: r.games, reverse=True
                )
            ]
            embed.add_field(name="라인별 지표", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"갱신 {stats.updated_at:%Y-%m-%d %H:%M}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
