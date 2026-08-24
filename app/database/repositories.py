from typing import Dict, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchPlayer
from app.models.player import Player
from app.services.matchmaking import LOBBY_SIZE
from app.services.replay import GameRecord, riot_id_key

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
    player = await get_player(session, discord_id, game)

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

async def get_open_match(session: AsyncSession, server_id: int) -> Optional[Match]:
    """해당 서버에서 아직 끝나지 않은 내전을 찾는다."""
    result = await session.execute(
        select(Match)
        .where(Match.discord_server_id == server_id, Match.completed.is_(False))
        .order_by(Match.id.desc())
    )
    return result.scalars().first()

async def create_match(session: AsyncSession, server_id: int) -> Match:
    match = Match(discord_server_id=server_id)
    session.add(match)
    await session.commit()
    return match

async def get_match(session: AsyncSession, match_id: int) -> Optional[Match]:
    result = await session.execute(select(Match).where(Match.id == match_id))
    return result.scalar_one_or_none()

async def _commit_and_reload(
    session: AsyncSession, match: Match
) -> Optional[Match]:
    """커밋 후 관계를 다시 적재한 내전을 돌려준다.

    호출자가 들고 있는 다른 객체까지 만료시키지 않도록 대상을 좁힌다.
    """
    # expire 뒤에 match.id 를 읽으면 lazy load 가 일어나 MissingGreenlet 이 난다.
    match_id = match.id
    await session.commit()
    session.expire(match)
    return await get_match(session, match_id)

async def join_match(
    session: AsyncSession, match_id: int, player_id: int
) -> Tuple[str, Optional[Match]]:
    """참가 결과와 갱신된 내전을 돌려준다."""
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return "closed", None
    if any(p.player_id == player_id for p in match.participants):
        return "already", match
    if len(match.participants) >= LOBBY_SIZE:
        return "full", match

    session.add(MatchPlayer(match_id=match_id, player_id=player_id))
    return "joined", await _commit_and_reload(session, match)

async def leave_match(
    session: AsyncSession, match_id: int, player_id: int
) -> Tuple[str, Optional[Match]]:
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return "closed", None

    entry = next((p for p in match.participants if p.player_id == player_id), None)
    if entry is None:
        return "absent", match

    match.participants.remove(entry)
    return "left", await _commit_and_reload(session, match)

async def save_teams(session: AsyncSession, match_id: int, result) -> Optional[Match]:
    """밸런싱 결과를 참가자 스냅샷에 기록한다."""
    match = await get_match(session, match_id)
    if match is None:
        return None

    assignment = {}
    for member, role in result.team_a.members:
        assignment[member.player_id] = ("A", role)
    for member, role in result.team_b.members:
        assignment[member.player_id] = ("B", role)

    for entry in match.participants:
        entry.team, entry.role = assignment[entry.player_id]

    return await _commit_and_reload(session, match)

async def custom_records(
    session: AsyncSession, player_ids: Sequence[int], server_id: int
) -> Dict[int, Tuple[int, int]]:
    """해당 서버에서 끝난 내전 기준 (경기 수, 승 수)를 플레이어별로 집계한다.

    설계서 5.2 의 custom_games / custom_win_rate 에 해당한다. 컬럼으로 저장하지
    않고 match_players 에서 바로 세는 이유는, 전적 갱신과 결과 저장이 각각 같은
    값을 쓰면 어긋날 수 있기 때문이다.
    """
    if not player_ids:
        return {}

    wins = func.sum(case((MatchPlayer.win.is_(True), 1), else_=0))
    result = await session.execute(
        select(MatchPlayer.player_id, func.count().label("games"), wins.label("wins"))
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(
            Match.completed.is_(True),
            Match.discord_server_id == server_id,
            MatchPlayer.player_id.in_(player_ids),
        )
        .group_by(MatchPlayer.player_id)
    )
    return {row.player_id: (row.games, int(row.wins or 0)) for row in result}

async def custom_stats(
    session: AsyncSession, player_id: int, server_id: int
) -> Optional[Tuple[int, float, float, float]]:
    """사설 전적 파일로 기록된 내전의 (경기 수, KDA, 평균 CS, 평균 딜).

    버튼으로만 확정한 내전은 개인 성적이 비어 있으므로 집계에서 뺀다.
    """
    result = await session.execute(
        select(
            func.count().label("games"),
            func.sum(MatchPlayer.kills).label("kills"),
            func.sum(MatchPlayer.deaths).label("deaths"),
            func.sum(MatchPlayer.assists).label("assists"),
            func.avg(MatchPlayer.cs).label("cs"),
            func.avg(MatchPlayer.damage).label("damage"),
        )
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(
            Match.completed.is_(True),
            Match.discord_server_id == server_id,
            MatchPlayer.player_id == player_id,
            MatchPlayer.kills.isnot(None),
        )
    )
    row = result.one()
    if not row.games:
        return None

    return (
        row.games,
        (row.kills + row.assists) / max(row.deaths, 1),
        float(row.cs),
        float(row.damage),
    )

async def finish_match(
    session: AsyncSession, match_id: int, winner: str
) -> Optional[Match]:
    """승리 팀을 확정하고 참가자별 승패를 기록한다."""
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return None

    for entry in match.participants:
        entry.win = entry.team == winner

    match.team_a_score = int(winner == "A")
    match.team_b_score = int(winner == "B")
    match.completed = True

    return await _commit_and_reload(session, match)

async def finish_match_with_records(
    session: AsyncSession, match_id: int, game: GameRecord
) -> Tuple[str, Optional[Match]]:
    """사설 전적 기록으로 승패와 개인 성적을 함께 확정한다."""
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return "closed", None

    records = game.by_riot_id()
    paired = [
        (
            entry,
            records[
                riot_id_key(entry.player.riot_game_name, entry.player.riot_tagline)
            ],
        )
        for entry in match.participants
    ]

    # 로비에서 진영을 바꿔 들어갔다면 우리 A/B 와 실제 승패가 어긋난다. 틀린 승리
    # 팀은 custom_records 집계까지 오염시키므로, 쓰기 전에 확인하고 아무것도 남기지
    # 않는다. (여기서 rollback 을 하면 호출자가 든 객체까지 만료된다)
    a_won = {record.win for entry, record in paired if entry.team == "A"}
    b_won = {record.win for entry, record in paired if entry.team == "B"}
    if len(a_won) != 1 or len(b_won) != 1 or a_won == b_won:
        return "mismatch", None

    for entry, record in paired:
        entry.win = record.win
        entry.kills = record.kills
        entry.deaths = record.deaths
        entry.assists = record.assists
        entry.cs = record.cs
        entry.damage = record.damage
        entry.gold = record.gold

    winner = "A" if a_won == {True} else "B"
    match.team_a_score = int(winner == "A")
    match.team_b_score = int(winner == "B")
    match.completed = True

    return winner, await _commit_and_reload(session, match)

async def last_assigned_roles(
    session: AsyncSession,
    player_ids: Sequence[int],
    server_id: int,
    exclude_match_id: Optional[int] = None,
) -> Dict[int, str]:
    """해당 서버에서 각 플레이어가 가장 최근에 배정받은 라인을 찾는다."""
    if not player_ids:
        return {}

    statement = (
        select(MatchPlayer.player_id, MatchPlayer.role, Match.id)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(
            Match.discord_server_id == server_id,
            MatchPlayer.role.isnot(None),
            MatchPlayer.player_id.in_(player_ids),
        )
        .order_by(Match.id.desc())
    )
    if exclude_match_id is not None:
        statement = statement.where(Match.id != exclude_match_id)

    latest: Dict[int, str] = {}
    for player_id, role, _ in await session.execute(statement):
        latest.setdefault(player_id, role)
    return latest

async def open_matches(session: AsyncSession) -> Sequence[Match]:
    """아직 끝나지 않은 내전 전부. 재시작 시 버튼을 다시 등록하는 데 쓴다."""
    result = await session.execute(select(Match).where(Match.completed.is_(False)))
    return result.scalars().all()
