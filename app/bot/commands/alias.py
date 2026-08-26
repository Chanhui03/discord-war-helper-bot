import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import NEED_REGISTER
from app.database.repositories import (
    add_alias,
    aliases_for,
    get_player,
    remove_alias,
)
from app.database.session import session_factory
from app.services.riot.client import RiotClient
from app.services.riot.exceptions import RiotAPIError

def alias_lines(aliases) -> str:
    if not aliases:
        return "등록한 부계정이 없습니다."
    return "\n".join(
        f"- `{alias.riot_game_name}#{alias.riot_tagline}`" for alias in aliases
    )

class RemoveSelect(discord.ui.Select):
    def __init__(self, player_id: int, aliases) -> None:
        super().__init__(
            placeholder="지울 부계정을 고르세요",
            options=[
                discord.SelectOption(
                    label=f"{alias.riot_game_name}#{alias.riot_tagline}",
                    value=str(alias.id),
                )
                for alias in aliases
            ],
        )
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            removed = await remove_alias(session, self.player_id, int(self.values[0]))
            aliases = (await aliases_for(session, [self.player_id])).get(self.player_id, [])

        await interaction.response.edit_message(
            content=("지웠습니다.\n" if removed else "") + alias_lines(aliases),
            view=None,
        )

class Alias(commands.Cog):
    """본계정이 정지됐을 때 쓰는 부계정. 전적 파일에서 사람을 알아보는 데만 쓴다."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.riot = RiotClient()

    @app_commands.command(name="부계정등록", description="내전에서 쓰는 부계정 Riot ID 를 등록합니다.")
    @app_commands.describe(riot_id="게임이름#태그")
    @app_commands.rename(riot_id="게임이름태그")
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
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.followup.send(NEED_REGISTER, ephemeral=True)
                return

            status = await add_alias(
                session, player.id, account["gameName"], account["tagLine"]
            )
            aliases = (await aliases_for(session, [player.id])).get(player.id, [])

        notes = {
            "taken": "이미 다른 사람이 쓰고 있는 Riot ID 입니다.",
            "mine": "이미 등록된 계정입니다.",
        }
        head = notes.get(status, "부계정을 등록했습니다. 솔랭 지표는 본계정만 씁니다.")
        await interaction.followup.send(
            f"{head}\n{alias_lines(aliases)}", ephemeral=True
        )

    @app_commands.command(name="부계정삭제", description="등록한 부계정을 봅니다. 골라서 지울 수 있습니다.")
    async def remove(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            aliases = (
                (await aliases_for(session, [player.id])).get(player.id, [])
                if player
                else []
            )

        if player is None:
            await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
            return
        if not aliases:
            await interaction.response.send_message(alias_lines([]), ephemeral=True)
            return

        view = discord.ui.View(timeout=180)
        view.add_item(RemoveSelect(player.id, aliases))
        await interaction.response.send_message(
            alias_lines(aliases), view=view, ephemeral=True
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Alias(bot))
