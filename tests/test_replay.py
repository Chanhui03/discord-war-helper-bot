import json

import pytest

from app.services.replay import ReplayError, find_game, load_games, riot_id_key

def participant(
    participant_id, name, tag, team_id, win, lane="MIDDLE", role="SOLO", **stats
):
    """샘플 파일과 같은 구조로 참가자 한 명을 만든다."""
    base = {
        "kills": 0, "deaths": 0, "assists": 0,
        "totalMinionsKilled": 0, "neutralMinionsKilled": 0,
        "totalDamageDealtToChampions": 0, "totalDamageTaken": 0,
        "goldEarned": 0, "wardsPlaced": 0,
        "firstBloodKill": False, "firstTowerKill": False,
    }
    base.update(stats)
    return (
        {
            "participantId": participant_id,
            "player": {
                "accountId": 0,
                "gameName": name,
                "puuid": "068565b9-146e-57b0-9433-9c228aee4e73",
                "summonerName": "",
                "tagLine": tag,
            },
        },
        {
            "participantId": participant_id,
            "teamId": team_id,
            "stats": {"participantId": participant_id, "win": win, **base},
            "timeline": {"participantId": participant_id, "lane": lane, "role": role},
        },
    )

def game(pairs, game_id=1, created_at=1000, aborted=False):
    identities, participants = zip(*pairs)
    return {
        "endOfGameResult": "Abort_TooFewPlayers" if aborted else "GameComplete",
        "gameCreation": created_at,
        "gameDuration": 1800,
        "gameId": game_id,
        "gameType": "CUSTOM_GAME",
        "participantIdentities": list(identities),
        "participants": list(participants),
    }

def ten_players(game_id=1, created_at=1000):
    """A팀(100) 승리, B팀(200) 패배인 10인 사설 경기."""
    return game(
        [
            participant(i + 1, f"플레이어{i}", "KR1", 100 if i < 5 else 200, i < 5)
            for i in range(10)
        ],
        game_id=game_id,
        created_at=created_at,
    )

def keys(count=10):
    return [riot_id_key(f"플레이어{i}", "KR1") for i in range(count)]

def test_riot_id_key_ignores_case_and_padding():
    assert riot_id_key(" 겨 울 ", "Chani") == riot_id_key("겨 울", "chani")

def test_aborted_games_are_dropped():
    payload = [ten_players(), game([participant(2, "겨 울", "chani", 200, False)], aborted=True)]
    assert [record.game_id for record in load_games(payload)] == [1]

def test_cs_includes_jungle_camps():
    payload = [game([participant(1, "정글", "KR1", 100, True,
                                 totalMinionsKilled=30, neutralMinionsKilled=120)])]
    assert load_games(payload)[0].participants[0].cs == 150

def test_anonymised_participants_are_dropped():
    pairs = [participant(1, "이름있음", "KR1", 100, True), participant(2, "", "", 200, False)]
    assert len(load_games([game(pairs)])[0].participants) == 1

def test_find_game_picks_most_recent_full_match():
    payload = [ten_players(game_id=7, created_at=500), ten_players(game_id=9, created_at=900)]
    assert find_game(json.dumps(payload), keys()).game_id == 9

def test_find_game_skips_games_missing_a_participant():
    partial = game(
        [participant(i + 1, f"플레이어{i}", "KR1", 100, True) for i in range(9)],
        game_id=3,
        created_at=9999,
    )
    payload = [partial, ten_players(game_id=4, created_at=100)]
    assert find_game(json.dumps(payload), keys()).game_id == 4

def test_find_game_names_who_could_not_be_matched():
    payload = [game([participant(i + 1, f"플레이어{i}", "KR1", 100, True) for i in range(9)])]
    with pytest.raises(ReplayError) as error:
        find_game(json.dumps(payload), keys())
    assert "플레이어9#kr1" in str(error.value)

def test_find_game_rejects_only_aborted_games():
    payload = [ten_players()]
    payload[0]["endOfGameResult"] = "Abort_Unexpected"
    with pytest.raises(ReplayError, match="중단된 경기"):
        find_game(json.dumps(payload), keys())

def test_find_game_rejects_broken_json():
    with pytest.raises(ReplayError, match="읽을 수 없습니다"):
        find_game("{not json", keys())

def one_record(**kwargs):
    """참가자 한 명짜리 경기를 만들어 그 기록을 돌려준다."""
    [parsed] = load_games(game([participant(1, "겨 울", "chani", 100, True, **kwargs)]))
    [record] = parsed.participants
    return parsed, record

def test_detailed_stats_are_read():
    _, record = one_record(
        totalDamageDealtToChampions=21249,
        totalDamageTaken=18072,
        goldEarned=12741,
        wardsPlaced=13,
        firstBloodKill=True,
        firstTowerKill=False,
    )

    assert (record.damage, record.damage_taken, record.gold) == (21249, 18072, 12741)
    assert record.wards == 13
    assert (record.first_blood, record.first_tower) == (True, False)

def test_game_duration_is_kept():
    parsed, _ = one_record()
    assert parsed.duration == 1800

@pytest.mark.parametrize(
    "lane, role, expected",
    [
        ("TOP", "SOLO", "TOP"),
        ("JUNGLE", "NONE", "JUNGLE"),
        ("MIDDLE", "SOLO", "MID"),
        ("BOTTOM", "DUO_CARRY", "ADC"),
        ("BOTTOM", "DUO_SUPPORT", "SUPPORT"),
        ("NONE", "NONE", None),
    ],
)
def test_position_comes_from_the_timeline(lane, role, expected):
    _, record = one_record(lane=lane, role=role)
    assert record.position == expected
