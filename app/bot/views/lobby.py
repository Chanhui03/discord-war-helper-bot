import asyncio
import logging

import discord

from app.bot.messages import NEED_REGISTER
from app.bot.views.persistent import PersistentView
from app.bot.views.teams import TeamEditView, match_profiles, teams_embed
from app.database.repositories import (
    delete_match,
    get_match,
    get_player,
    join_match,
    leave_match,
    save_teams,
    unwatch_match,
    watch_match,
)
from app.database.session import session_factory
from app.log import event
from app.services.matchmaking import LOBBY_SIZE, find_best_teams

log = logging.getLogger(__name__)

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
    if match.spectators:
        embed.add_field(
            name=f"관전 {len(match.spectators)}명",
            value=" ".join(f"<@{viewer.discord_id}>" for viewer in match.spectators),
            inline=False,
        )
    if count == LOBBY_SIZE:
        embed.set_footer(text="인원이 모두 찼습니다.")
    return embed

class LobbyView(PersistentView):
    PREFIX = "lobby"

    async def _update(self, interaction: discord.Interaction, action) -> None:
        async with session_factory() as session:
            player = await get_player(session, interaction.user.id)
            if player is None:
                await interaction.response.send_message(NEED_REGISTER, ephemeral=True)
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

        self.generate.disabled = len(match.participants) < LOBBY_SIZE
        await interaction.response.edit_message(embed=embed, view=self)

    async def _watch(self, interaction: discord.Interaction, action) -> None:
        """관전은 Riot 계정 등록을 요구하지 않아 참가와 경로가 다르다."""
        async with session_factory() as session:
            status, match = await action(session, self.match_id, interaction.user.id)
            embed = lobby_embed(match) if match else None

        messages = {
            "closed": "이미 종료된 내전입니다.",
            "already": "이미 관전 중입니다.",
            "playing": "참가 중입니다. 참가를 취소한 뒤 관전해주세요.",
            "absent": "관전 중이 아닙니다.",
        }
        if status in messages:
            await interaction.response.send_message(messages[status], ephemeral=True)
            return

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="참가", style=discord.ButtonStyle.success, custom_id="join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, join_match)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary, custom_id="leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update(interaction, leave_match)

    @discord.ui.button(label="관전", style=discord.ButtonStyle.secondary, custom_id="watch")
    async def watch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._watch(interaction, watch_match)

    @discord.ui.button(label="관전 취소", style=discord.ButtonStyle.secondary, custom_id="unwatch")
    async def unwatch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._watch(interaction, unwatch_match)

    @discord.ui.button(label="팀 생성", style=discord.ButtonStyle.primary, disabled=True, custom_id="generate")
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            match = await get_match(session, self.match_id)
            if match is None or len(match.participants) < LOBBY_SIZE:
                await interaction.response.send_message(
                    f"참가자가 {LOBBY_SIZE}명이어야 합니다.", ephemeral=True
                )
                return
            profiles = await match_profiles(session, match)

        # 조합 탐색은 1초 이상 걸릴 수 있어 이벤트 루프를 막지 않는다.
        await interaction.response.defer()
        result = await asyncio.to_thread(find_best_teams, profiles)

        async with session_factory() as session:
            match = await save_teams(session, self.match_id, result)
            embed = teams_embed(match, result)

        event(
            log,
            "teams_generated",
            match=self.match_id,
            score=round(result.score, 2),
            evaluated=result.evaluated,
            bans_honoured=result.bans_honoured,
            power_a=round(result.team_a.power, 1),
            power_b=round(result.team_b.power, 1),
        )
        self.stop()
        await interaction.edit_original_response(embed=embed, view=TeamEditView(match))

    @discord.ui.button(label="삭제", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with session_factory() as session:
            deleted = await delete_match(session, self.match_id)

        if not deleted:
            await interaction.response.send_message("이미 삭제된 내전입니다.", ephemeral=True)
            return

        event(log, "match_deleted", match=self.match_id, by=interaction.user.id)
        self.stop()
        await interaction.response.edit_message(
            content=f"내전 #{self.match_id} 모집이 삭제되었습니다.", embed=None, view=None
        )
