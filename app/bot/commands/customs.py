import discord
from discord import app_commands
from discord.ext import commands

from app.bot.messages import NEED_REGISTER
from app.database.repositories import custom_position_stats, get_player
from app.database.session import session_factory
from app.roles import ROLE_LABELS

# 합계 컬럼. 전체 행은 라인별 행을 이 항목들로 더해서 만든다.
SUMS = (
    "games", "wins", "kills", "deaths", "assists", "first_blood", "first_tower",
    "damage", "damage_taken", "gold", "cs", "wards", "seconds",
)

BASIC = (("라인", 4), ("경기", 6), ("승", 4), ("패", 4), ("승률", 8), ("KDA", 6),
         ("킬", 6), ("데스", 6), ("어시", 6))
DETAIL = (("라인", 4), ("DPM", 8), ("DTPM", 8), ("GPM", 8), ("CSPM", 6),
          ("DPGR", 6), ("첫킬", 7), ("첫포탑", 8), ("와드", 6))

def width(text: str) -> int:
    """코드블록은 고정폭이지만 한글은 두 칸을 차지한다."""
    return sum(2 if ord(char) > 0x2E7F else 1 for char in text)

def table(columns, rows) -> str:
    header = "".join(name.rjust(size - width(name) + len(name)) for name, size in columns)
    lines = [
        "".join(
            cell.rjust(size - width(cell) + len(cell))
            for cell, (_, size) in zip(row, columns)
        )
        for row in rows
    ]
    return "```\n" + "\n".join([header, *lines]) + "\n```"

def combine(rows) -> dict:
    return {field: sum(getattr(row, field) for row in rows) for field in SUMS}

def basic_cells(label: str, total: dict):
    games = total["games"]
    kda = (total["kills"] + total["assists"]) / max(total["deaths"], 1)
    return [
        label,
        f"{games}",
        f"{total['wins']}",
        f"{games - total['wins']}",
        f"{total['wins'] / games:.1%}",
        f"{kda:.2f}",
        f"{total['kills'] / games:.1f}",
        f"{total['deaths'] / games:.1f}",
        f"{total['assists'] / games:.1f}",
    ]

def detail_cells(label: str, total: dict):
    minutes = total["seconds"] / 60
    dpm = total["damage"] / minutes
    gpm = total["gold"] / minutes
    return [
        label,
        f"{dpm:,.1f}",
        f"{total['damage_taken'] / minutes:,.1f}",
        f"{gpm:,.1f}",
        f"{total['cs'] / minutes:.2f}",
        # DPGR: 먹은 골드 대비 얼마나 딜을 넣었는지(가성비).
        f"{dpm / gpm:.2f}",
        f"{total['first_blood'] / total['games']:.1%}",
        f"{total['first_tower'] / total['games']:.1%}",
        f"{total['wards'] / total['games']:.1f}",
    ]

def stats_embed(player, rows) -> discord.Embed:
    """전체 한 줄 + 많이 간 라인 순서로 라인별 한 줄."""
    lines = [("전체", combine(rows))] + [
        (ROLE_LABELS.get(row.role, "기타"), combine([row])) for row in rows
    ]
    embed = discord.Embed(
        title=f"{player.riot_game_name}#{player.riot_tagline} 내전 전적",
        colour=discord.Colour.blurple(),
    )
    embed.add_field(
        name="기본",
        value=table(BASIC, [basic_cells(label, total) for label, total in lines]),
        inline=False,
    )
    embed.add_field(
        name="세부",
        value=table(DETAIL, [detail_cells(label, total) for label, total in lines]),
        inline=False,
    )
    embed.set_footer(text="사설 전적 파일로 확정한 내전만 집계합니다.")
    return embed

class Customs(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="내전전적", description="내전 라인별 지표를 봅니다.")
    @app_commands.guild_only()
    async def customs(self, interaction: discord.Interaction) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            rows = (
                await custom_position_stats(session, player.id, interaction.guild_id)
                if player
                else []
            )

        if player is None:
            await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
            return
        if not rows:
            await interaction.response.send_message(
                "집계할 내전 기록이 없습니다. `/결과`에 사설 전적 파일을 첨부하면 쌓입니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=stats_embed(player, rows), ephemeral=True
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Customs(bot))
