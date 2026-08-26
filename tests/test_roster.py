from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.bot.commands.roster import LIST_LIMIT, roster_embed
from app.database.repositories import all_players, upsert_player

NOW = datetime(2026, 8, 26, 21, 30)

def player(n, days_ago=None):
    """days_ago 가 None 이면 아직 전적을 받지 않은 등록자."""
    return SimpleNamespace(
        id=n,
        discord_id=1000 + n,
        riot_game_name=f"플레이어{n}",
        riot_tagline="KR1",
        stats=(
            None
            if days_ago is None
            else SimpleNamespace(updated_at=NOW - timedelta(days=days_ago))
        ),
    )

def test_empty_roster():
    embed = roster_embed([])
    assert embed.title == "등록된 게이머 0명"
    assert embed.description == "아직 등록한 사람이 없습니다."

def test_lists_the_most_recently_refreshed_first():
    embed = roster_embed([player(0, days_ago=3), player(1, days_ago=0)])
    lines = embed.description.split("\n")

    assert embed.title == "등록된 게이머 2명"
    assert lines[0] == "1. <@1001> `플레이어1#KR1` — 갱신 2026-08-26"
    assert lines[1] == "2. <@1000> `플레이어0#KR1` — 갱신 2026-08-23"

def test_players_without_stats_go_last():
    embed = roster_embed([player(0), player(1, days_ago=5)])
    lines = embed.description.split("\n")

    assert lines[0].startswith("1. <@1001>")
    assert lines[1] == "2. <@1000> `플레이어0#KR1` — 갱신 기록 없음"

def test_long_roster_is_truncated():
    embed = roster_embed([player(i, days_ago=i) for i in range(LIST_LIMIT + 3)])
    lines = embed.description.split("\n")

    assert embed.title == f"등록된 게이머 {LIST_LIMIT + 3}명"
    assert len(lines) == LIST_LIMIT + 1
    assert lines[-1] == "-# 외 3명"

@pytest.mark.asyncio
async def test_all_players_returns_everyone_registered(session):
    for i in range(3):
        await upsert_player(
            session, discord_id=i, puuid=f"p-{i}", game_name=f"이름{i}", tagline="KR1"
        )

    assert {p.discord_id for p in await all_players(session)} == {0, 1, 2}

def test_alias_count_is_shown_next_to_the_main_account():
    embed = roster_embed([player(0, days_ago=1), player(1, days_ago=2)], {0: ["a", "b"]})
    lines = embed.description.split("\n")

    assert "(+부계정 2)" in lines[0]
    assert "부계정" not in lines[1]
