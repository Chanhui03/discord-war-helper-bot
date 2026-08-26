import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.exc import IntegrityError

from app.bot.messages import NEED_REGISTER
from app.database.repositories import get_player, upsert_player
from app.database.session import session_factory
from app.services.riot.client import RiotClient
from app.services.riot.exceptions import RiotAPIError
from app.services.stats import refresh_player_stats

class Register(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.riot = RiotClient()

    @app_commands.command(name="전적등록", description="Riot 계정을 등록하고 전적을 받아옵니다.")
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
            # 다른 Riot 계정으로 바꿨다면 캐시를 무시하고 다시 받아야 한다.
            existing = await get_player(session, interaction.user.id)
            account_changed = existing is None or existing.puuid != account["puuid"]

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
                refreshed = await refresh_player_stats(
                    session, self.riot, player, force=account_changed
                )
                note = "" if refreshed else "\n최근에 갱신해서 전적 조회는 생략했습니다."
            except RiotAPIError as error:
                note = f"\n전적 수집 실패: {error} — `/전적갱신`으로 다시 시도해주세요."

        await interaction.followup.send(
            f"등록 완료: **{player.riot_game_name}#{player.riot_tagline}**{note}",
            ephemeral=True,
        )

    @app_commands.command(name="전적갱신", description="등록한 계정의 전적을 다시 받아옵니다.")
    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.followup.send(NEED_REGISTER, ephemeral=True)
                return

            try:
                # 직접 부른 갱신이므로 TTL 을 무시하고 항상 다시 받아온다.
                await refresh_player_stats(session, self.riot, player, force=True)
            except RiotAPIError as error:
                await interaction.followup.send(
                    f"전적 수집 실패: {error}", ephemeral=True
                )
                return

        await interaction.followup.send(
            f"**{player.riot_game_name}#{player.riot_tagline}** 전적을 갱신했습니다."
            "\n`/전적`으로 확인해주세요.",
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Register(bot))
