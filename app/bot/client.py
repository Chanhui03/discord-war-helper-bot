import logging

import discord
from discord.ext import commands

from app.config.settings import settings

log = logging.getLogger(__name__)

EXTENSIONS = [
    "app.bot.commands.ping",
    "app.bot.commands.register",
    "app.bot.commands.profile",
    "app.bot.commands.roles",
    "app.bot.commands.war",
    "app.bot.commands.result",
]

class WarBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.default(),
        )

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)

        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("%s 로그인 완료", self.user)
