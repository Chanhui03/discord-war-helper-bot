import discord

from app.database.repositories import get_player, join_match, leave_match
from app.database.session import session_factory
from app.services.matchmaking import LOBBY_SIZE

def lobby_embed(match) -> discord.Embed:
    count = len(match.participants)
    lines = [
        f"{index}. <@{entry.player.discord_id}> "
        f"({entry.player.riot_game_name}#{entry.player.riot_tagline})"
        for index, entry in enumerate(match.participants, 1)
    ]

    embed = discord.Embed(
        title=f"내전 모집 #{match.id}",
        description=f"**{count} / {LOBBY_SIZE}명**",
        colour=discord.Colour.green() if count == LOBBY_SIZE else discord.Colour.greyple(),
    )
    embed.add_field(
        name="참가자",
        value="\n".join(lines) if lines else "아직 참가자가 없습니다.",
    )
    if count == LOBBY_SIZE:
        embed.set_footer(text="인원이 모두 찼습니다.")
    return embed

class LobbyView(discord.ui.View):
    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=1800)
        self.match_id = match_id

    async def _update(self, interaction: discord.Interaction, action) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.response.send_message(
                    "먼저 `/등록`으로 Riot 계정을 연결해주세요.", ephemeral=True
                )
                return

            status, match = await action(session, self.match_id, player.id)
            embed = lobby_embed(match) if match else None

        messages = {
            "closed": "이미 종료된 내전입니다.",
            "already": "이미 참가 중입니다.",
            "full": f"인원이 모두 찼습니다. ({LOBBY_SIZE}명)",
            "absent": "참가 중이 아닙니다.",
        }
        if status in messages:
            await interaction.response.send_message(messages[status], ephemeral=True)
            return

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="참가", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, join_match)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, leave_match)
