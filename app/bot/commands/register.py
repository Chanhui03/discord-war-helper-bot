import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.exc import IntegrityError

from app.database.repositories import upsert_player
from app.database.session import session_factory
from app.services.riot.client import RiotClient
from app.services.riot.exceptions import RiotAPIError
from app.services.stats import refresh_player_stats

class Register(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.riot = RiotClient()

    @app_commands.command(name="등록", description="Riot 계정을 등록합니다.")
    @app_commands.describe(riot_id="게임이름#태그")
    async def register(self, interaction: discord.Interaction, riot_id: str) -> None:
        game_name, _, tagline = riot_id.partition("#")
        game_name, tagline = game_name.strip(), tagline.strip()

        if not game_name or not tagline:
            await interaction.response.send_message(
                "Riot ID는 `게임이름#태그` 형식으로 입력해주세요.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            account = await self.riot.get_account(game_name, tagline)
        except RiotAPIError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        async with session_factory() as session:
            try:
                player = await upsert_player(
                    session,
                    discord_id=interaction.user.id,
                    puuid=account["puuid"],
                    game_name=account["gameName"],
                    tagline=account["tagLine"],
                )
            except IntegrityError:
                await session.rollback()
                await interaction.followup.send(
                    "이미 다른 Discord 사용자가 등록한 계정입니다.", ephemeral=True
                )
                return

            # 전적 수집이 실패해도 계정 등록 자체는 유지한다.
            try:
                await refresh_player_stats(session, self.riot, player)
                note = ""
            except RiotAPIError as error:
                note = f"\n전적 수집 실패: {error} — `/등록`으로 다시 시도해주세요."

        await interaction.followup.send(
            f"등록 완료: **{player.riot_game_name}#{player.riot_tagline}**{note}",
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Register(bot))
