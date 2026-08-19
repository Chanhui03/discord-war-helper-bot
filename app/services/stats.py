"""Riot 응답을 플레이어 집계 지표로 변환한다."""

import asyncio
from typing import Any, Dict, List, Optional

from app.models.player import PlayerRole, PlayerStats
from app.roles import RIOT_POSITIONS
from app.services.matchmaking import PlayerProfile
from app.services.scoring import (
    base_score,
    custom_score,
    performance_score,
    role_score,
    tier_score,
)

SOLO_QUEUE = "RANKED_SOLO_5x5"
RECENT_MATCH_COUNT = 20

# 개발용 키 한도(초당 20회)에 여유를 두고 동시 호출을 제한한다.
MATCH_CONCURRENCY = 5

def pick_solo_entry(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """솔로랭크 항목을 고른다. 없으면 None(언랭)."""
    for entry in entries:
        if entry.get("queueType") == SOLO_QUEUE:
            return entry
    return None

def kda(kills: int, deaths: int, assists: int) -> float:
    return (kills + assists) / max(deaths, 1)

def aggregate_matches(matches: List[Dict[str, Any]], puuid: str) -> Dict[str, Any]:
    """최근 경기 목록에서 전체/라인별 지표를 집계한다.

    teamPosition 이 비어 있는 경기(ARAM 등)는 라인 집계에서 제외한다.
    """
    total_games = 0
    total_wins = 0
    kda_sum = 0.0
    per_role: Dict[str, Dict[str, float]] = {}

    for match in matches:
        participant = next(
            (
                p
                for p in match.get("info", {}).get("participants", [])
                if p.get("puuid") == puuid
            ),
            None,
        )
        if participant is None:
            continue

        won = bool(participant.get("win"))
        match_kda = kda(
            participant.get("kills", 0),
            participant.get("deaths", 0),
            participant.get("assists", 0),
        )

        total_games += 1
        total_wins += int(won)
        kda_sum += match_kda

        role = RIOT_POSITIONS.get(participant.get("teamPosition", ""))
        if role is None:
            continue

        bucket = per_role.setdefault(role, {"games": 0, "wins": 0, "kda_sum": 0.0})
        bucket["games"] += 1
        bucket["wins"] += int(won)
        bucket["kda_sum"] += match_kda

    roles = {}
    for role, bucket in per_role.items():
        games = int(bucket["games"])
        wins = int(bucket["wins"])
        win_rate = wins / games
        avg_kda = bucket["kda_sum"] / games
        roles[role] = {
            "games": games,
            "wins": wins,
            "win_rate": win_rate,
            "avg_kda": avg_kda,
            "role_score": role_score(games, win_rate, avg_kda),
        }

    return {
        "games": total_games,
        "wins": total_wins,
        "recent_win_rate": total_wins / total_games if total_games else 0.0,
        "avg_kda": kda_sum / total_games if total_games else 0.0,
        "roles": roles,
    }

def player_score(
    tier: Optional[str],
    division: Optional[str],
    lp: int,
    recent_win_rate: float,
    avg_kda: float,
    main_role_score: Optional[float] = None,
) -> float:
    """설계서 6장 가중합으로 플레이어의 기본 점수를 낸다."""
    return base_score(
        tier=tier_score(tier, division, lp),
        role=main_role_score,
        recent_form=recent_win_rate * 100,
        performance=performance_score(avg_kda),
    )

async def fetch_matches(riot, match_ids: List[str]) -> List[Dict[str, Any]]:
    """rate limit 을 넘기지 않도록 동시 호출 수를 제한해 경기 상세를 받는다."""
    limit = asyncio.Semaphore(MATCH_CONCURRENCY)

    async def fetch(match_id: str):
        async with limit:
            return await riot.get_match(match_id)

    return await asyncio.gather(*(fetch(match_id) for match_id in match_ids))

async def refresh_player_stats(session, riot, player) -> None:
    """Riot API에서 랭크와 최근 경기를 받아 집계 테이블을 갱신한다."""
    solo = pick_solo_entry(await riot.get_league_entries(player.puuid))

    match_ids = await riot.get_match_ids(player.puuid, RECENT_MATCH_COUNT)
    matches = await fetch_matches(riot, match_ids)
    aggregate = aggregate_matches(matches, player.puuid)

    wins = solo["wins"] if solo else 0
    losses = solo["losses"] if solo else 0
    total = wins + losses

    # 방금 만들어진 player 는 관계가 적재된 적이 없다. 그대로 대입하면
    # delete-orphan 정리 과정에서 lazy load 가 일어나 MissingGreenlet 이 난다.
    await session.refresh(player, ["stats", "roles"])

    player.stats = PlayerStats(
        tier=solo["tier"] if solo else None,
        division=solo["rank"] if solo else None,
        lp=solo["leaguePoints"] if solo else 0,
        wins=wins,
        losses=losses,
        win_rate=wins / total if total else 0.0,
        avg_kda=aggregate["avg_kda"],
        recent_win_rate=aggregate["recent_win_rate"],
    )
    player.roles = [
        PlayerRole(role=role, **values) for role, values in aggregate["roles"].items()
    ]
    await session.commit()

def build_profile(player, custom_games: int = 0, custom_wins: int = 0) -> PlayerProfile:
    """저장된 전적과 내전 기록에서 밸런싱용 스냅샷을 만든다."""
    stats = player.stats
    return PlayerProfile(
        player_id=player.id,
        display=f"{player.riot_game_name}#{player.riot_tagline}",
        tier=tier_score(stats.tier, stats.division, stats.lp) if stats else None,
        recent_form=stats.recent_win_rate * 100 if stats else None,
        performance=performance_score(stats.avg_kda) if stats else None,
        custom=custom_score(custom_games, custom_wins),
        win_rate=stats.win_rate if stats else 0.0,
        main_role=player.main_role,
        secondary_role=player.secondary_role,
        role_scores={row.role: row.role_score for row in player.roles},
    )
