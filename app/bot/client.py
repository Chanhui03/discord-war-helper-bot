import logging

import discord
from discord.ext import commands

from app.bot.views.lobby import LobbyView
from app.bot.views.teams import TeamEditView
from app.bot.views.rating import RatingView
from app.bot.views.result import ResultView
from app.config.settings import settings
from app.database.repositories import open_matches, recently_completed
from app.database.session import session_factory
from app.log import event

log = logging.getLogger(__name__)

EXTENSIONS = [
    "app.bot.commands.ping",
    "app.bot.commands.register",
    "app.bot.commands.alias",
    "app.bot.commands.profile",
    "app.bot.commands.customs",
    "app.bot.commands.roles",
    "app.bot.commands.ability",
    "app.bot.commands.roster",
    "app.bot.commands.war",
    "app.bot.commands.result",
    "app.bot.commands.callscore",
]

class WarBot(commands.Bot):
    def __init__(self) -> None:
        # 슬래시 명령만 쓰므로 접두사 명령은 멘션으로만 받는다.
        # (message_content 특권 인텐트 없이도 경고가 나지 않는다)
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
        )

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)

        await self.restore_views()

        if settings.discord_guild_ids:
            for guild_id in settings.discord_guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def restore_views(self) -> None:
        """재시작 전에 열려 있던 내전의 버튼을 다시 살린다."""
        async with session_factory() as session:
            matches = await open_matches(session)
            finished = await recently_completed(session)

        for match in matches:
            self.add_view(LobbyView(match.id))
            self.add_view(ResultView(match.id))
            # 팀이 이미 짜인 내전은 자리 교환 메뉴도 되살린다.
            if any(entry.team for entry in match.participants):
                self.add_view(TeamEditView(match))

        # 평점은 결과가 확정된 뒤에 붙으므로 끝난 내전에서 되살린다.
        for match in list(matches) + list(finished):
            self.add_view(RatingView(match.id))

        if matches:
            log.info(
                "진행 중인 내전 %d건의 버튼을 복구했습니다: %s",
                len(matches),
                [match.id for match in matches],
            )

    async def on_app_command_completion(self, interaction, command) -> None:
        event(
            log,
            "command",
            name=command.qualified_name,
            user=interaction.user.id,
            guild=interaction.guild_id,
        )

    async def on_ready(self) -> None:
        log.info("%s 로그인 완료", self.user)
