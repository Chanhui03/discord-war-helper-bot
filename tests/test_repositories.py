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

class TestResults:
    async def _staged_match(self, session, server_id=1):
        """팀 배정까지 끝난 내전을 만든다."""
        import random

        from app.database.repositories import create_match, get_match
        from app.services.matchmaking import LOBBY_SIZE, find_best_teams
        from app.services.stats import build_profile

        match = await create_match(session, server_id=server_id)
        for i in range(LOBBY_SIZE):
            player = await register(session, 1000 + i, f"p-{server_id}-{i}")
            await join_match(session, match.id, player.id)

        match = await get_match(session, match.id)
        result = find_best_teams(
            [build_profile(entry.player) for entry in match.participants],
            rng=random.Random(1),
        )
        return await save_teams(session, match.id, result)

    async def test_finish_match_records_wins_and_scores(self, session):
        from app.database.repositories import finish_match

        match = await self._staged_match(session)
        finished = await finish_match(session, match.id, "A")

        assert finished.completed is True
        assert (finished.team_a_score, finished.team_b_score) == (1, 0)
        for entry in finished.participants:
            assert entry.win is (entry.team == "A")

    async def test_finishing_twice_is_rejected(self, session):
        from app.database.repositories import finish_match

        match = await self._staged_match(session)
        assert await finish_match(session, match.id, "A") is not None
        assert await finish_match(session, match.id, "B") is None

    async def test_custom_records_ignore_unfinished_matches(self, session):
        from app.database.repositories import custom_records, finish_match

        match = await self._staged_match(session)
        ids = [entry.player_id for entry in match.participants]
        assert await custom_records(session, ids, 1) == {}

        await finish_match(session, match.id, "A")
        records = await custom_records(session, ids, 1)
        assert len(records) == len(ids)
        assert sum(wins for _, wins in records.values()) == 5
        assert all(games == 1 for games, _ in records.values())

    async def test_custom_records_accumulate_within_a_server(self, session):
        from app.database.repositories import custom_records, finish_match

        first = await self._staged_match(session, server_id=1)
        await finish_match(session, first.id, "A")
        winner_ids = [e.player_id for e in first.participants if e.team == "A"]

        second = await create_second(session, winner_ids, server_id=1)
        await finish_match(session, second.id, "A")

        records = await custom_records(session, winner_ids, 1)
        for player_id in winner_ids:
            games, wins = records[player_id]
            # 2차전에서 팀이 다시 섞이므로 2승일 수도 1승일 수도 있다.
            assert games == 2, f"{player_id}: {games}전으로 집계됨"
            assert 1 <= wins <= 2, f"{player_id}: {wins}승"

    async def test_custom_records_are_scoped_to_one_server(self, session):
        """설계서 5.2: 내전 성적은 해당 Discord 서버 기준으로 센다."""
        from app.database.repositories import custom_records, finish_match

        first = await self._staged_match(session, server_id=1)
        await finish_match(session, first.id, "A")
        winner_ids = [e.player_id for e in first.participants if e.team == "A"]

        elsewhere = await create_second(session, winner_ids, server_id=2)
        await finish_match(session, elsewhere.id, "A")

        here = await custom_records(session, winner_ids, 1)
        there = await custom_records(session, winner_ids, 2)
        assert all(games == 1 for games, _ in here.values())
        assert all(games == 1 for games, _ in there.values())
        assert await custom_records(session, winner_ids, 3) == {}

    async def test_custom_record_reaches_the_balancing_profile(self, session):
        from app.database.repositories import custom_records, finish_match
        from app.services.stats import build_profile

        match = await self._staged_match(session)
        await finish_match(session, match.id, "A")
        records = await custom_records(
            session, [e.player_id for e in match.participants], 1
        )

        winner = next(e for e in match.participants if e.team == "A")
        loser = next(e for e in match.participants if e.team == "B")
        won = build_profile(winner.player, *records[winner.player_id])
        lost = build_profile(loser.player, *records[loser.player_id])

        assert won.custom > lost.custom

    async def test_empty_player_list_returns_empty(self, session):
        from app.database.repositories import custom_records

        assert await custom_records(session, [], 1) == {}

async def create_second(session, player_ids, server_id):
    """같은 참가자로 두 번째 내전을 만들어 팀까지 배정한다."""
    import random

    from app.database.repositories import create_match, get_match
    from app.services.matchmaking import LOBBY_SIZE, find_best_teams
    from app.services.stats import build_profile

    match = await create_match(session, server_id=server_id)
    extra = [
        await register(session, 9000 + server_id * 100 + i, f"extra-{server_id}-{i}")
        for i in range(LOBBY_SIZE - len(player_ids))
    ]
    for player_id in player_ids:
        await join_match(session, match.id, player_id)
    for player in extra:
        await join_match(session, match.id, player.id)

    match = await get_match(session, match.id)
    result = find_best_teams(
        [build_profile(e.player) for e in match.participants], rng=random.Random(2)
    )
    return await save_teams(session, match.id, result)
