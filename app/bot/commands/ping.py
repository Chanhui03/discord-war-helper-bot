import discord
from discord import app_commands
from discord.ext import commands

class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="봇 응답 속도를 확인합니다.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"pong! ({latency_ms}ms)")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ping(bot))
