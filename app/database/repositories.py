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
