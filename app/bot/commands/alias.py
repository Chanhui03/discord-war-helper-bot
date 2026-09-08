import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import NEED_REGISTER
from app.database.repositories import (
    add_alias,
    aliases_for,
    get_player,
    promote_alias,
    remove_alias,
)
from app.database.session import session_factory
from app.services.riot.client import RiotClient
from app.services.riot.exceptions import RiotAPIError
from app.services.stats import refresh_player_stats

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

class PromoteSelect(discord.ui.Select):
    """고른 부계정을 본계정으로 올린다. 쓰던 본계정은 부계정으로 내려간다."""

    def __init__(self, player_id: int, aliases, riot: RiotClient) -> None:
        super().__init__(
            placeholder="본계정으로 올릴 부계정을 고르세요",
            options=[
                discord.SelectOption(
                    label=f"{alias.riot_game_name}#{alias.riot_tagline}",
                    value=str(alias.id),
                )
                for alias in aliases
            ],
        )
        self.player_id = player_id
        self.riot = riot
        # 고른 뒤 이름만 다시 쓰려고 들고 있는다.
        self.by_id = {str(alias.id): alias for alias in aliases}

    async def callback(self, interaction: discord.Interaction) -> None:
        alias = self.by_id[self.values[0]]
        await interaction.response.edit_message(
            content=f"`{alias.riot_game_name}#{alias.riot_tagline}` 전적을 받아오는 중...",
            view=None,
        )

        # 부계정에는 puuid 가 없어 여기서 받아 넘긴다. 계정이 사라졌거나 이름이
        # 바뀌었으면 바꾸기 전에 여기서 걸린다.
        try:
            account = await self.riot.get_account(
                alias.riot_game_name, alias.riot_tagline
            )
        except RiotAPIError as error:
            await interaction.edit_original_response(content=str(error))
            return

        async with session_factory() as session:
            previous = await promote_alias(
                session, self.player_id, alias.id, account["puuid"]
            )
            if previous is None:
                await interaction.edit_original_response(
                    content="바꿀 수 없는 부계정입니다."
                )
                return

            player = await get_player(session, interaction.user.id)
            # 남아 있는 지표는 예전 계정 것이라 반드시 다시 받는다.
            await refresh_player_stats(session, self.riot, player, force=True)
            aliases = (await aliases_for(session, [self.player_id])).get(
                self.player_id, []
            )
            stats = player.stats

        rank = (
            f"{stats.tier} {stats.division} {stats.lp}LP"
            if stats and stats.tier
            else "언랭"
        )
        await interaction.edit_original_response(
            content=(
                f"본계정을 `{alias.riot_game_name}#{alias.riot_tagline}` 으로 "
                f"바꿨습니다. ({rank})\n"
                f"쓰던 `{previous[0]}#{previous[1]}` 은 부계정으로 남겼습니다. "
                "지난 전적 파일에서 알아보려면 필요합니다.\n"
                f"{alias_lines(aliases)}"
            )
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
            if player is None:
                await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
                return

            aliases = (await aliases_for(session, [player.id])).get(player.id, [])

        if not aliases:
            await interaction.response.send_message(alias_lines([]), ephemeral=True)
            return

        view = discord.ui.View(timeout=180)
        view.add_item(RemoveSelect(player.id, aliases))
        await interaction.response.send_message(
            alias_lines(aliases), view=view, ephemeral=True
        )

    @app_commands.command(
        name="본계정변경", description="부계정을 본계정으로 올립니다. 점수는 본계정으로 냅니다."
    )
    async def promote(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
                return

            aliases = (await aliases_for(session, [player.id])).get(player.id, [])

        if not aliases:
            await interaction.response.send_message(
                "등록한 부계정이 없습니다. `/부계정등록` 으로 먼저 등록해주세요.",
                ephemeral=True,
            )
            return

        view = discord.ui.View(timeout=180)
        view.add_item(PromoteSelect(player.id, aliases, self.riot))
        await interaction.response.send_message(
            f"지금 본계정은 `{player.riot_game_name}#{player.riot_tagline}` 입니다.\n"
            f"{alias_lines(aliases)}",
            view=view,
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Alias(bot))
