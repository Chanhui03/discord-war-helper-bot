import discord

from app.database.repositories import custom_records, finish_match, get_match
from app.database.session import session_factory
from app.roles import ROLE_LABELS, ROLES

def team_lines(match, team: str, records=None) -> str:
    rows = sorted(
        (entry for entry in match.participants if entry.team == team),
        key=lambda entry: ROLES.index(entry.role),
    )
    lines = []
    for entry in rows:
        line = f"`{ROLE_LABELS[entry.role]:<2}` <@{entry.player.discord_id}>"
        if records is not None:
            games, wins = records.get(entry.player_id, (0, 0))
            line += f" — 내전 {games}전 {wins}승 ({wins / games:.0%})" if games else " — 내전 첫 경기"
        lines.append(line)
    return "\n".join(lines)

def pending_embed(match) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 결과 입력",
        description="승리한 팀을 선택해주세요.",
        colour=discord.Colour.greyple(),
    )
    embed.add_field(name="A팀", value=team_lines(match, "A"))
    embed.add_field(name="B팀", value=team_lines(match, "B"))
    return embed

def result_embed(match, winner: str, records) -> discord.Embed:
    embed = discord.Embed(
        title=f"내전 #{match.id} 결과",
        description=f"**{winner}팀 승리**",
        colour=discord.Colour.gold(),
    )
    for team in ("A", "B"):
        mark = "승" if team == winner else "패"
        embed.add_field(
            name=f"{team}팀 ({mark})", value=team_lines(match, team, records), inline=False
        )
    return embed

class ResultView(discord.ui.View):
    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=600)
        self.match_id = match_id

    async def _finish(self, interaction: discord.Interaction, winner: str) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "결과 확정은 서버 관리 권한이 있는 사람만 할 수 있습니다.", ephemeral=True
            )
            return

        async with session_factory() as session:
            match = await finish_match(session, self.match_id, winner)
            if match is None:
                await interaction.response.send_message(
                    "이미 결과가 저장된 내전입니다.", ephemeral=True
                )
                return
            records = await custom_records(
                session,
                [entry.player_id for entry in match.participants],
                match.discord_server_id,
            )
            embed = result_embed(match, winner, records)

        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="A팀 승리", style=discord.ButtonStyle.success)
    async def team_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, "A")

    @discord.ui.button(label="B팀 승리", style=discord.ButtonStyle.success)
    async def team_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, "B")
