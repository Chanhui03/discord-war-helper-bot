import pytest

from app.database.repositories import (
    get_player,
    join_match,
    leave_match,
    save_teams,
    upsert_player,
)
from app.services.stats import refresh_player_stats

pytestmark = pytest.mark.asyncio

async def register(session, discord_id, puuid, name="테스터"):
    return await upsert_player(
        session, discord_id=discord_id, puuid=puuid, game_name=name, tagline="KR1"
    )

class FakeRiot:
    """league / match 응답을 흉내내는 최소 구현."""

    def __init__(self, tier="GOLD", division="II", lp=50, positions=("MIDDLE", "TOP")):
        self.tier, self.division, self.lp = tier, division, lp
        self.positions = positions

    async def get_league_entries(self, puuid):
        return [{
            "queueType": "RANKED_SOLO_5x5", "tier": self.tier, "rank": self.division,
            "leaguePoints": self.lp, "wins": 60, "losses": 40,
        }]

    async def get_match_ids(self, puuid, count):
        return [f"KR_{i}" for i in range(len(self.positions))]

    async def get_match(self, match_id):
        index = int(match_id.split("_")[1])
        return {"info": {"participants": [{
            "puuid": "p-1", "teamPosition": self.positions[index], "win": index % 2 == 0,
            "kills": 5, "deaths": 2, "assists": 5,
        }]}}

class TestRefreshPlayerStats:
    async def test_refresh_right_after_upsert(self, session):
        """갓 만든 player 는 관계가 적재된 적이 없어 lazy load 가 터졌었다."""
        player = await register(session, 1, "p-1")
        await refresh_player_stats(session, FakeRiot(), player)

        stored = await get_player(session, 1)
        assert stored.stats.tier == "GOLD"
        assert stored.stats.division == "II"
        assert {row.role for row in stored.roles} == {"MID", "TOP"}

    async def test_refresh_twice_does_not_duplicate_rows(self, session):
        player = await register(session, 1, "p-1")
        await refresh_player_stats(session, FakeRiot(), player)
        await refresh_player_stats(session, FakeRiot(tier="PLATINUM"), player)

        stored = await get_player(session, 1)
        assert stored.stats.tier == "PLATINUM"
        assert len(stored.roles) == 2, "delete-orphan 이 이전 라인 행을 지우지 않았다"

class TestUpsertPlayer:
    async def test_reregistering_keeps_the_same_row(self, session):
        first = await register(session, 1, "p-1", name="옛이름")
        second = await register(session, 1, "p-2", name="새이름")
        assert first.id == second.id
        assert second.riot_game_name == "새이름"
        assert second.puuid == "p-2"

class TestLobby:
    async def test_join_leave_and_capacity(self, session):
        from app.database.repositories import create_match
        from app.services.matchmaking import LOBBY_SIZE

        match = await create_match(session, server_id=1)
        players = [await register(session, i, f"p-{i}") for i in range(LOBBY_SIZE + 1)]

        for player in players[:LOBBY_SIZE]:
            status, _ = await join_match(session, match.id, player.id)
            assert status == "joined"

        assert (await join_match(session, match.id, players[0].id))[0] == "already"
        assert (await join_match(session, match.id, players[-1].id))[0] == "full"

        status, updated = await leave_match(session, match.id, players[0].id)
        assert status == "left"
        assert len(updated.participants) == LOBBY_SIZE - 1
        assert (await leave_match(session, match.id, players[0].id))[0] == "absent"

    async def test_save_teams_writes_every_assignment(self, session):
        import random

        from app.database.repositories import create_match
        from app.services.matchmaking import LOBBY_SIZE, find_best_teams
        from app.services.stats import build_profile

        match = await create_match(session, server_id=1)
        for i in range(LOBBY_SIZE):
            player = await register(session, i, f"p-{i}")
            await join_match(session, match.id, player.id)

        from app.database.repositories import get_match

        match = await get_match(session, match.id)
        result = find_best_teams(
            [build_profile(entry.player) for entry in match.participants],
            rng=random.Random(1),
        )
        saved = await save_teams(session, match.id, result)

        assert all(entry.team in ("A", "B") for entry in saved.participants)
        assert all(entry.role for entry in saved.participants)
        assert len([e for e in saved.participants if e.team == "A"]) == 5
