from collections import Counter
from typing import Dict, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchPlayer, MatchRating, MatchSpectator
from app.models.player import Player, PlayerAlias, PlayerTrait
from app.services.matchmaking import LOBBY_SIZE
from app.services.replay import GameRecord, riot_id_key

# 재시작 때 평점 버튼을 되살릴 내전 수.
RECENT_MATCH_LIMIT = 20

def _finished_in(server_id: int):
    """집계는 모두 '그 서버에서 끝난 내전'만 본다."""
    return Match.completed.is_(True), Match.discord_server_id == server_id


def _count_true(column):
    """True 인 행만 센다. SQLite 에는 boolean 합계가 없어 case 로 편다."""
    return func.sum(case((column.is_(True), 1), else_=0))

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

async def all_players(session: AsyncSession, game: str = "lol") -> Sequence[Player]:
    """등록된 플레이어 전부. 서버별로 나누지 않고 봇 전체 기준이다."""
    result = await session.execute(select(Player).where(Player.game == game))
    return result.scalars().all()

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

async def _riot_id_owner(session: AsyncSession, riot_id: str) -> Optional[int]:
    """그 Riot ID 를 이미 쓰고 있는 플레이어. 본계정과 부계정을 모두 본다."""
    for player in await all_players(session):
        if riot_id_key(player.riot_game_name, player.riot_tagline) == riot_id:
            return player.id

    result = await session.execute(
        select(PlayerAlias.player_id).where(PlayerAlias.riot_id == riot_id)
    )
    return result.scalar_one_or_none()

async def add_alias(
    session: AsyncSession, player_id: int, game_name: str, tagline: str
) -> str:
    """부계정 Riot ID 를 등록한다.

    남의 성적을 가로챌 수 없도록, 이미 누가 쓰고 있는 ID 는 받지 않는다.
    """
    riot_id = riot_id_key(game_name, tagline)
    owner = await _riot_id_owner(session, riot_id)
    if owner is not None:
        return "mine" if owner == player_id else "taken"

    session.add(
        PlayerAlias(
            player_id=player_id,
            riot_id=riot_id,
            riot_game_name=game_name,
            riot_tagline=tagline,
        )
    )
    await session.commit()
    return "added"

async def remove_alias(session: AsyncSession, player_id: int, alias_id: int) -> bool:
    """본인 것만 지운다."""
    alias = await session.get(PlayerAlias, alias_id)
    if alias is None or alias.player_id != player_id:
        return False

    await session.delete(alias)
    await session.commit()
    return True

async def aliases_for(
    session: AsyncSession, player_ids: Sequence[int]
) -> Dict[int, list]:
    """플레이어별 부계정 목록."""
    if not player_ids:
        return {}

    result = await session.execute(
        select(PlayerAlias)
        .where(PlayerAlias.player_id.in_(player_ids))
        .order_by(PlayerAlias.id)
    )
    grouped: Dict[int, list] = {}
    for alias in result.scalars():
        grouped.setdefault(alias.player_id, []).append(alias)
    return grouped

async def match_riot_ids(session: AsyncSession, match: Match) -> Dict[int, list]:
    """참가자별로 인정할 Riot ID 키 목록. 본계정이 앞에 온다."""
    player_ids = [entry.player_id for entry in match.participants]
    aliases = await aliases_for(session, player_ids)
    return {
        entry.player_id: [
            riot_id_key(entry.player.riot_game_name, entry.player.riot_tagline),
            *(alias.riot_id for alias in aliases.get(entry.player_id, ())),
        ]
        for entry in match.participants
    }

async def save_trait(
    session: AsyncSession,
    target_id: int,
    rater_discord_id: int,
    trait: str,
    score: int,
) -> None:
    """주관 지표를 남긴다. 같은 사람이 다시 매기면 덮어쓴다."""
    result = await session.execute(
        select(PlayerTrait).where(
            PlayerTrait.target_id == target_id,
            PlayerTrait.rater_discord_id == rater_discord_id,
            PlayerTrait.trait == trait,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        session.add(
            PlayerTrait(
                target_id=target_id,
                rater_discord_id=rater_discord_id,
                trait=trait,
                score=score,
            )
        )
    else:
        row.score = score

    await session.commit()

async def trait_scores(
    session: AsyncSession, player_ids: Sequence[int]
) -> Dict[int, Dict[str, Tuple[float, int]]]:
    """플레이어별 {지표: (평균, 평가 인원)}."""
    if not player_ids:
        return {}

    result = await session.execute(
        select(
            PlayerTrait.target_id,
            PlayerTrait.trait,
            func.avg(PlayerTrait.score).label("average"),
            func.count().label("votes"),
        )
        .where(PlayerTrait.target_id.in_(player_ids))
        .group_by(PlayerTrait.target_id, PlayerTrait.trait)
    )

    scores: Dict[int, Dict[str, Tuple[float, int]]] = {}
    for target_id, trait, average, votes in result:
        scores.setdefault(target_id, {})[trait] = (float(average), votes)
    return scores

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

async def delete_match(session: AsyncSession, match_id: int) -> bool:
    """내전을 참가자·관전자와 함께 지운다."""
    match = await get_match(session, match_id)
    if match is None:
        return False

    await session.delete(match)
    await session.commit()
    return True

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

    # 관전 중이었다면 참가로 옮긴다. 관전 자리는 제한이 없어 조용히 바꿔도 된다.
    player = await session.get(Player, player_id)
    viewer = next(
        (v for v in match.spectators if v.discord_id == player.discord_id), None
    )
    if viewer is not None:
        match.spectators.remove(viewer)

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

async def watch_match(
    session: AsyncSession, match_id: int, discord_id: int
) -> Tuple[str, Optional[Match]]:
    """관전자로 등록한다. Riot 계정 등록은 요구하지 않는다."""
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return "closed", None
    if any(viewer.discord_id == discord_id for viewer in match.spectators):
        return "already", match
    # 10자리가 걸린 쪽이라 참가자는 스스로 취소하게 한다.
    if any(entry.player.discord_id == discord_id for entry in match.participants):
        return "playing", match

    session.add(MatchSpectator(match_id=match_id, discord_id=discord_id))
    return "watching", await _commit_and_reload(session, match)

async def unwatch_match(
    session: AsyncSession, match_id: int, discord_id: int
) -> Tuple[str, Optional[Match]]:
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return "closed", None

    viewer = next(
        (v for v in match.spectators if v.discord_id == discord_id), None
    )
    if viewer is None:
        return "absent", match

    match.spectators.remove(viewer)
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

async def swap_team_slots(
    session: AsyncSession, match_id: int, first_id: int, second_id: int
) -> Optional[Match]:
    """두 참가자의 팀과 라인을 통째로 맞바꾼다.

    자리를 교환하므로 팀별 라인 5개는 그대로 유지된다.
    """
    match = await get_match(session, match_id)
    if match is None or match.completed:
        return None

    by_id = {entry.player_id: entry for entry in match.participants}
    first, second = by_id.get(first_id), by_id.get(second_id)
    if first is None or second is None:
        return None

    first.team, second.team = second.team, first.team
    first.role, second.role = second.role, first.role
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

    wins = _count_true(MatchPlayer.win)
    result = await session.execute(
        select(MatchPlayer.player_id, func.count().label("games"), wins.label("wins"))
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(*_finished_in(server_id), MatchPlayer.player_id.in_(player_ids))
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
            *_finished_in(server_id),
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

async def custom_position_stats(
    session: AsyncSession, player_id: int, server_id: int
) -> Sequence:
    """사설 전적 파일로 기록된 내전의 라인별 합계. 많이 간 라인이 앞에 온다.

    평균·분당 지표를 여기서 내지 않고 합계만 돌려주는 이유는, 표시할 때 여러 라인을
    합친 '전체' 행도 같은 계산으로 만들기 위해서다.
    """
    position = func.coalesce(MatchPlayer.played_role, MatchPlayer.role).label("role")
    result = await session.execute(
        select(
            position,
            func.count().label("games"),
            _count_true(MatchPlayer.win).label("wins"),
            func.sum(MatchPlayer.kills).label("kills"),
            func.sum(MatchPlayer.deaths).label("deaths"),
            func.sum(MatchPlayer.assists).label("assists"),
            _count_true(MatchPlayer.first_blood).label("first_blood"),
            _count_true(MatchPlayer.first_tower).label("first_tower"),
            func.sum(MatchPlayer.damage).label("damage"),
            func.sum(MatchPlayer.damage_taken).label("damage_taken"),
            func.sum(MatchPlayer.gold).label("gold"),
            func.sum(MatchPlayer.cs).label("cs"),
            func.sum(MatchPlayer.wards).label("wards"),
            func.sum(Match.duration).label("seconds"),
        )
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(
            *_finished_in(server_id),
            MatchPlayer.player_id == player_id,
            # 경기 시간이 없는 기록(버튼으로만 확정한 내전)은 분당 지표를 낼 수 없다.
            Match.duration.isnot(None),
        )
        .group_by(position)
        .order_by(func.count().desc())
    )
    return result.all()

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
    keys = await match_riot_ids(session, match)
    paired = [
        (
            entry,
            next(
                (records[key] for key in keys[entry.player_id] if key in records), None
            ),
        )
        for entry in match.participants
    ]

    # 로비에서 진영을 바꿔 들어갔다면 우리 A/B 와 실제 승패가 어긋난다. 틀린 승리
    # 팀은 custom_records 집계까지 오염시키므로, 쓰기 전에 확인하고 아무것도 남기지
    # 않는다. (여기서 rollback 을 하면 호출자가 든 객체까지 만료된다)
    # 한쪽 팀이 통째로 안 맞으면 승패를 알 수 없어 같은 길로 보낸다.
    a_won = {r.win for entry, r in paired if r and entry.team == "A"}
    b_won = {r.win for entry, r in paired if r and entry.team == "B"}
    if len(a_won) != 1 or len(b_won) != 1 or a_won == b_won:
        return "mismatch", None

    winner = "A" if a_won == {True} else "B"
    # 사설 게임은 클라이언트가 라인을 제대로 매기지 못해 탑 라이너가 정글로 온다.
    # 한 팀에 같은 라인이 둘이면 그 라인은 믿을 수 없으니 배정한 라인을 쓴다.
    duplicated = Counter(
        (entry.team, record.position)
        for entry, record in paired
        if record and record.position
    )
    for entry, record in paired:
        # 못 맞춘 참가자도 팀 승패는 남긴다. 개인 성적만 비워 둔다.
        entry.win = entry.team == winner
        if record is None:
            continue

        entry.kills = record.kills
        entry.deaths = record.deaths
        entry.assists = record.assists
        entry.cs = record.cs
        entry.damage = record.damage
        entry.damage_taken = record.damage_taken
        entry.gold = record.gold
        entry.wards = record.wards
        entry.first_blood = record.first_blood
        entry.first_tower = record.first_tower
        entry.played_role = (
            entry.role
            if duplicated[(entry.team, record.position)] > 1
            else record.position
        )

    match.duration = game.duration
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
        select(MatchPlayer.player_id, MatchPlayer.role)
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
    for player_id, role in await session.execute(statement):
        latest.setdefault(player_id, role)
    return latest

async def save_rating(
    session: AsyncSession,
    match_id: int,
    rater_discord_id: int,
    target_id: int,
    score: int,
) -> None:
    """평점을 남긴다. 같은 대상에 다시 매기면 덮어쓴다."""
    result = await session.execute(
        select(MatchRating).where(
            MatchRating.match_id == match_id,
            MatchRating.rater_discord_id == rater_discord_id,
            MatchRating.target_id == target_id,
        )
    )
    rating = result.scalar_one_or_none()

    if rating is None:
        session.add(
            MatchRating(
                match_id=match_id,
                rater_discord_id=rater_discord_id,
                target_id=target_id,
                score=score,
            )
        )
    else:
        rating.score = score

    await session.commit()

async def ratings_by_rater(
    session: AsyncSession, match_id: int, rater_discord_id: int
) -> Dict[int, int]:
    """한 사람이 이 내전에서 남긴 평점. 평점 창에 이미 매긴 값을 표시하는 데 쓴다."""
    result = await session.execute(
        select(MatchRating.target_id, MatchRating.score).where(
            MatchRating.match_id == match_id,
            MatchRating.rater_discord_id == rater_discord_id,
        )
    )
    return {row.target_id: row.score for row in result}

async def match_ratings(
    session: AsyncSession, match_id: int
) -> Dict[int, Tuple[float, int]]:
    """이 내전에서 플레이어별 (평균 평점, 받은 표 수)."""
    result = await session.execute(
        select(
            MatchRating.target_id,
            func.avg(MatchRating.score).label("average"),
            func.count().label("votes"),
        )
        .where(MatchRating.match_id == match_id)
        .group_by(MatchRating.target_id)
    )
    return {row.target_id: (float(row.average), row.votes) for row in result}

def pick_mvp(ratings: Dict[int, Tuple[float, int]]) -> Optional[int]:
    """평균이 가장 높은 플레이어. 동점이면 표를 더 많이 받은 쪽이 이긴다."""
    if not ratings:
        return None
    return max(ratings, key=lambda player_id: ratings[player_id])

async def mvp_counts(
    session: AsyncSession, player_ids: Sequence[int], server_id: int
) -> Dict[int, int]:
    """해당 서버에서 각자 MVP 를 몇 번 했는지.

    custom_records 와 같은 이유로 컬럼에 저장하지 않는다. 평점은 결과 확정 뒤에도
    계속 들어올 수 있어서, 저장해 두면 최신 평점과 어긋난다.
    """
    if not player_ids:
        return {}

    result = await session.execute(
        select(
            MatchRating.match_id,
            MatchRating.target_id,
            func.avg(MatchRating.score),
            func.count(),
        )
        .join(Match, Match.id == MatchRating.match_id)
        .where(*_finished_in(server_id))
        .group_by(MatchRating.match_id, MatchRating.target_id)
    )

    per_match: Dict[int, Dict[int, Tuple[float, int]]] = {}
    for match_id, target_id, average, votes in result:
        per_match.setdefault(match_id, {})[target_id] = (float(average), votes)

    counts = {player_id: 0 for player_id in player_ids}
    for ratings in per_match.values():
        winner = pick_mvp(ratings)
        if winner in counts:
            counts[winner] += 1
    return counts

async def open_matches(session: AsyncSession) -> Sequence[Match]:
    """아직 끝나지 않은 내전 전부. 재시작 시 버튼을 다시 등록하는 데 쓴다."""
    result = await session.execute(select(Match).where(Match.completed.is_(False)))
    return result.scalars().all()

async def recently_completed(
    session: AsyncSession, limit: int = RECENT_MATCH_LIMIT
) -> Sequence[Match]:
    """끝난 내전 중 최근 것들. 평점 버튼을 다시 등록하는 데 쓴다.

    평점은 경기 직후에 몰리므로 전부 복구할 필요가 없다.
    """
    result = await session.execute(
        select(Match)
        .where(Match.completed.is_(True))
        .order_by(Match.id.desc())
        .limit(limit)
    )
    return result.scalars().all()
