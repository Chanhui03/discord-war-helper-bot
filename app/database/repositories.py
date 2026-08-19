from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player

async def upsert_player(
    session: AsyncSession,
    *,
    discord_id: int,
    puuid: str,
    game_name: str,
    tagline: str,
    region: str = "kr",
    game: str = "lol",
) -> Player:
    """Discord 사용자의 게임 계정을 등록하거나 갱신한다."""
    result = await session.execute(
        select(Player).where(
            Player.discord_id == discord_id,
            Player.game == game,
        )
    )
    player = result.scalar_one_or_none()

    if player is None:
        player = Player(discord_id=discord_id, game=game)
        session.add(player)

    player.puuid = puuid
    player.riot_game_name = game_name
    player.riot_tagline = tagline
    player.region = region

    await session.commit()
    return player

async def get_player(
    session: AsyncSession,
    discord_id: int,
    game: str = "lol",
) -> Optional[Player]:
    result = await session.execute(
        select(Player).where(
            Player.discord_id == discord_id,
            Player.game == game,
        )
    )
    return result.scalar_one_or_none()

async def set_role_preference(
    session: AsyncSession,
    discord_id: int,
    field: str,
    role: str,
    game: str = "lol",
) -> None:
    """main_role 또는 secondary_role 한 칸만 갱신한다."""
    player = await get_player(session, discord_id, game)
    setattr(player, field, role)
    await session.commit()
