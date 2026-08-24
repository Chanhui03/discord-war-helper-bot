"""LoL 클라이언트에서 받은 사설 전적 JSON 을 읽는다.

match-v5 는 사설 게임을 돌려주지 않아 내전의 개인 성적을 채울 방법이 없었다.
클라이언트가 뽑아주는 기록은 puuid / accountId / summonerName 이 모두 익명화되어
있어, 남아 있는 식별자인 게임이름#태그로 참가자를 맞춘다.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

# 중단된 경기는 스탯이 의미 없다. endOfGameResult 가 Abort_ 로 시작한다.
ABORTED_PREFIX = "Abort"

class ReplayError(Exception):
    pass

@dataclass(frozen=True)
class ParticipantRecord:
    riot_id: str
    team_id: int
    win: bool
    kills: int
    deaths: int
    assists: int
    cs: int
    damage: int
    gold: int

@dataclass(frozen=True)
class GameRecord:
    game_id: int
    created_at: int
    participants: Tuple[ParticipantRecord, ...]

    def by_riot_id(self) -> Dict[str, ParticipantRecord]:
        return {record.riot_id: record for record in self.participants}

def riot_id_key(game_name: str, tagline: str) -> str:
    """대소문자와 앞뒤 공백을 무시한 비교용 키."""
    return f"{game_name.strip().casefold()}#{tagline.strip().casefold()}"

def _participants(game: Dict[str, Any]) -> Tuple[ParticipantRecord, ...]:
    """participants 의 스탯과 participantIdentities 의 이름을 participantId 로 잇는다.

    이름이 비어 있는 참가자는 맞출 수 없으므로 버린다. 그러면 호출부의
    '누가 안 맞았는지' 안내에 그대로 드러난다.
    """
    identities = {
        identity["participantId"]: identity.get("player", {})
        for identity in game.get("participantIdentities", [])
    }

    records = []
    for participant in game.get("participants", []):
        player = identities.get(participant.get("participantId"), {})
        game_name = player.get("gameName") or ""
        tagline = player.get("tagLine") or ""
        if not game_name or not tagline:
            continue

        stats = participant.get("stats", {})
        records.append(
            ParticipantRecord(
                riot_id=riot_id_key(game_name, tagline),
                team_id=participant.get("teamId", 0),
                win=bool(stats.get("win")),
                kills=stats.get("kills", 0),
                deaths=stats.get("deaths", 0),
                assists=stats.get("assists", 0),
                # 정글 몫을 빼먹으면 정글러 CS 가 0 으로 남는다.
                cs=stats.get("totalMinionsKilled", 0)
                + stats.get("neutralMinionsKilled", 0),
                damage=stats.get("totalDamageDealtToChampions", 0),
                gold=stats.get("goldEarned", 0),
            )
        )
    return tuple(records)

def load_games(payload: Any) -> List[GameRecord]:
    """최신 경기가 앞에 오도록 정렬한 기록 목록. 중단된 경기는 뺀다."""
    games = payload if isinstance(payload, list) else [payload]
    records = [
        GameRecord(
            game_id=game.get("gameId", 0),
            created_at=game.get("gameCreation", 0),
            participants=_participants(game),
        )
        for game in games
        if not str(game.get("endOfGameResult", "")).startswith(ABORTED_PREFIX)
    ]
    return sorted(records, key=lambda record: record.created_at, reverse=True)

def find_game(raw: str, riot_ids: Sequence[str]) -> GameRecord:
    """참가자 전원이 들어 있는 가장 최근 경기를 고른다."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ReplayError("JSON 파일을 읽을 수 없습니다.")

    games = load_games(payload)
    if not games:
        raise ReplayError("기록할 수 있는 경기가 없습니다. 중단된 경기만 들어 있습니다.")

    wanted = set(riot_ids)
    for game in games:
        if wanted <= set(game.by_riot_id()):
            return game

    # 가장 많이 겹치는 경기를 근거로 누가 빠졌는지 알려준다.
    closest = max(games, key=lambda game: len(wanted & set(game.by_riot_id())))
    missing = sorted(wanted - set(closest.by_riot_id()))
    raise ReplayError(
        "참가자가 일치하는 경기를 찾지 못했습니다. "
        f"맞출 수 없는 사람: {', '.join(missing)}"
    )
