import random
from dataclasses import replace

import pytest

from app.database.repositories import (
    pick_vote_mvp,
    save_vote,
    vote_by,
    vote_counts,
    voted_mvp,
    call_averages,
    match_reviews,
    save_match_reviews,
    add_alias,
    aliases_for,
    create_match,
    create_rematch,
    custom_position_stats,
    custom_records,
    custom_stats,
    delete_match,
    finish_match,
    finish_match_with_records,
    get_match,
    get_open_match,
    get_player,
    join_match,
    last_assigned_roles,
    leave_match,
    mvp_counts,
    pick_mvp,
    remove_alias,
    save_trait,
    series_champions,
    swap_team_slots,
    trait_scores,
    unwatch_match,
    watch_match,
    save_teams,
    upsert_player,
)
from app.roles import ROLES
from app.traits import CHAMPS, MAIN_CALL
from app.services.matchmaking import LOBBY_SIZE, find_best_teams
from app.services.replay import GameRecord, ParticipantRecord, riot_id_key
from app.services.stats import SOLO_QUEUE_ID, build_profile, refresh_player_stats
from app.services.transcript import PlayerCall

pytestmark = pytest.mark.asyncio

async def register(session, discord_id, puuid, name="테스터"):
    return await upsert_player(
        session, discord_id=discord_id, puuid=puuid, game_name=name, tagline="KR1"
    )

class FakeRiot:
    """league / match 응답을 흉내내는 최소 구현."""

    def __init__(
        self,
        tier="GOLD",
        division="II",
        lp=50,
        positions=("MIDDLE", "TOP"),
        masteries=(200_000, 120_000, 15_000),
    ):
        self.tier, self.division, self.lp = tier, division, lp
        self.positions = positions
        self.masteries = masteries

    async def get_champion_masteries(self, puuid):
        return [{"championPoints": points} for points in self.masteries]

    async def get_league_entries(self, puuid):
        return [{
            "queueType": "RANKED_SOLO_5x5", "tier": self.tier, "rank": self.division,
            "leaguePoints": self.lp, "wins": 60, "losses": 40,
        }]

    async def get_match_ids(self, puuid, count, queue=None):
        self.queue = queue
        return [f"KR_{i}" for i in range(len(self.positions))]

    async def get_match(self, match_id):
        index = int(match_id.split("_")[1])
        return {"info": {"participants": [{
            "puuid": "p-1", "teamPosition": self.positions[index], "win": index % 2 == 0,
            "kills": 5, "deaths": 2, "assists": 5,
        }]}}

async def staged_match(session, server_id=1):
    """팀 배정까지 끝난 내전을 만든다."""
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

async def create_second(session, player_ids, server_id):
    """같은 참가자로 두 번째 내전을 만들어 팀까지 배정한다."""
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
        await refresh_player_stats(session, FakeRiot(tier="PLATINUM"), player, force=True)

        stored = await get_player(session, 1)
        assert stored.stats.tier == "PLATINUM"
        assert len(stored.roles) == 2, "delete-orphan 이 이전 라인 행을 지우지 않았다"

    async def test_recent_refresh_is_skipped(self, session):
        """설계서 12장: 최근에 받은 전적은 다시 요청하지 않는다."""
        player = await register(session, 1, "p-1")
        assert await refresh_player_stats(session, FakeRiot(), player) is True

        riot = FakeRiot(tier="PLATINUM")
        assert await refresh_player_stats(session, riot, player) is False

        stored = await get_player(session, 1)
        assert stored.stats.tier == "GOLD", "건너뛰었는데 값이 바뀌었다"

    async def test_force_bypasses_the_cache(self, session):
        player = await register(session, 1, "p-1")
        await refresh_player_stats(session, FakeRiot(), player)
        assert await refresh_player_stats(
            session, FakeRiot(tier="PLATINUM"), player, force=True
        ) is True

        stored = await get_player(session, 1)
        assert stored.stats.tier == "PLATINUM"

class TestSoloQueueOnly:
    async def test_only_solo_queue_matches_are_requested(self, session):
        """칼바람·일반이 섞이면 라인과 최근 폼 집계가 오염된다."""
        player = await register(session, 1, "p-1")
        riot = FakeRiot()
        await refresh_player_stats(session, riot, player)

        assert riot.queue == SOLO_QUEUE_ID

    async def test_a_player_with_no_ranked_games_has_no_recent_form(self, session):
        player = await register(session, 1, "p-1")
        await refresh_player_stats(session, FakeRiot(positions=()), player)

        stored = await get_player(session, 1)
        assert stored.stats.recent_games == 0

        # 표본이 없으면 0 이 아니라 '모름'이어야 가중치가 재분배된다.
        built = build_profile(stored)
        assert built.recent_form is None
        assert built.performance is None

    async def test_a_player_with_ranked_games_keeps_recent_form(self, session):
        player = await register(session, 1, "p-1")
        await refresh_player_stats(session, FakeRiot(), player)

        built = build_profile(await get_player(session, 1))
        assert built.recent_form is not None
        assert built.performance is not None

class TestMatchCalls:
    def call(self, player_id, score, confidence=0.9):
        return PlayerCall(
            player_id=player_id, identified=True, confidence=confidence,
            main_call=score, evidence=f"{player_id} 근거",
        )

    async def finished(self, session, server_id=1):
        match = await staged_match(session, server_id)
        return await finish_match(session, match.id, "A")

    async def test_it_saves_and_averages(self, session):
        match = await self.finished(session)
        ids = [entry.player_id for entry in match.participants][:2]
        await save_match_reviews(session, match.id, [self.call(ids[0], 8)])

        averages = await call_averages(session, ids, 1)
        assert averages[ids[0]] == (8.0, 1)
        assert ids[1] not in averages, "채점 안 된 사람이 집계에 들어갔다"

    async def test_rescoring_overwrites_rather_than_duplicating(self, session):
        match = await self.finished(session)
        player_id = match.participants[0].player_id

        await save_match_reviews(session, match.id, [self.call(player_id, 8)])
        await save_match_reviews(session, match.id, [self.call(player_id, 4)])

        assert (await call_averages(session, [player_id], 1))[player_id] == (4.0, 1)

    async def test_it_accumulates_across_matches(self, session):
        """판마다 한 표씩 쌓여야 한 판의 편차가 평균으로 눌린다."""
        first = await self.finished(session)
        player_id = first.participants[0].player_id
        await save_match_reviews(session, first.id, [self.call(player_id, 10)])

        second = await create_second(session, [player_id], server_id=1)
        second = await finish_match(session, second.id, "A")
        await save_match_reviews(session, second.id, [self.call(player_id, 4)])

        assert (await call_averages(session, [player_id], 1))[player_id] == (7.0, 2)

    async def test_unfinished_matches_are_not_counted(self, session):
        match = await staged_match(session)
        player_id = match.participants[0].player_id
        await save_match_reviews(session, match.id, [self.call(player_id, 9)])

        assert await call_averages(session, [player_id], 1) == {}

    async def test_other_servers_are_not_counted(self, session):
        match = await self.finished(session, server_id=1)
        player_id = match.participants[0].player_id
        await save_match_reviews(session, match.id, [self.call(player_id, 9)])

        assert await call_averages(session, [player_id], 2) == {}

    async def test_evidence_is_kept(self, session):
        match = await self.finished(session)
        player_id = match.participants[0].player_id
        await save_match_reviews(session, match.id, [self.call(player_id, 8)])

        rows = await match_reviews(session, match.id)
        assert rows[0].evidence == f"{player_id} 근거"

    async def test_it_feeds_the_balancing_profile(self, session):
        match = await self.finished(session)
        entry = match.participants[0]
        await save_match_reviews(session, match.id, [self.call(entry.player_id, 10)])

        averages = await call_averages(session, [entry.player_id], 1)
        built = build_profile(
            entry.player, recorded_call=averages[entry.player_id][0]
        )
        assert built.main_call is not None
        assert build_profile(entry.player).main_call is None

class TestUpsertPlayer:
    async def test_reregistering_keeps_the_same_row(self, session):
        first = await register(session, 1, "p-1", name="옛이름")
        second = await register(session, 1, "p-2", name="새이름")
        assert first.id == second.id
        assert second.riot_game_name == "새이름"
        assert second.puuid == "p-2"

class TestLobby:
    async def test_join_leave_and_capacity(self, session):
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

    async def test_delete_match_removes_participants_and_spectators(self, session):
        match = await create_match(session, server_id=1)
        player = await register(session, 1, "p-1")
        await join_match(session, match.id, player.id)
        await watch_match(session, match.id, discord_id=555)

        assert await delete_match(session, match.id) is True
        assert await get_match(session, match.id) is None
        assert await get_open_match(session, 1) is None

    async def test_deleting_twice_is_rejected(self, session):
        match = await create_match(session, server_id=1)
        assert await delete_match(session, match.id) is True
        assert await delete_match(session, match.id) is False

    async def test_save_teams_writes_every_assignment(self, session):
        match = await create_match(session, server_id=1)
        for i in range(LOBBY_SIZE):
            player = await register(session, i, f"p-{i}")
            await join_match(session, match.id, player.id)

        match = await get_match(session, match.id)
        result = find_best_teams(
            [build_profile(entry.player) for entry in match.participants],
            rng=random.Random(1),
        )
        saved = await save_teams(session, match.id, result)

        assert all(entry.team in ("A", "B") for entry in saved.participants)
        assert all(entry.role for entry in saved.participants)
        assert len([e for e in saved.participants if e.team == "A"]) == 5

class TestTeamEdit:
    async def sides(self, session):
        """팀 배정이 끝난 내전과 A팀·B팀 첫 참가자."""
        match = await staged_match(session)
        a = next(e for e in match.participants if e.team == "A")
        b = next(e for e in match.participants if e.team == "B")
        return match, a, b

    async def test_swap_exchanges_both_slots(self, session):
        match, a, b = await self.sides(session)
        before = ((a.team, a.role), (b.team, b.role))

        updated = await swap_team_slots(session, match.id, a.player_id, b.player_id)
        by_id = {entry.player_id: entry for entry in updated.participants}

        assert (by_id[a.player_id].team, by_id[a.player_id].role) == before[1]
        assert (by_id[b.player_id].team, by_id[b.player_id].role) == before[0]

    async def test_teams_keep_five_distinct_roles(self, session):
        match, a, b = await self.sides(session)
        updated = await swap_team_slots(session, match.id, a.player_id, b.player_id)

        for team in ("A", "B"):
            roles = [e.role for e in updated.participants if e.team == team]
            assert len(roles) == len(set(roles)) == 5

    async def test_swap_is_rejected_after_the_result(self, session):
        match, a, b = await self.sides(session)
        await finish_match(session, match.id, "A")

        assert await swap_team_slots(session, match.id, a.player_id, b.player_id) is None

    async def test_unknown_player_is_rejected(self, session):
        match, a, _ = await self.sides(session)
        assert await swap_team_slots(session, match.id, a.player_id, 99999) is None

class TestResults:
    async def test_finish_match_records_wins_and_scores(self, session):
        match = await staged_match(session)
        finished = await finish_match(session, match.id, "A")

        assert finished.completed is True
        assert (finished.team_a_score, finished.team_b_score) == (1, 0)
        for entry in finished.participants:
            assert entry.win is (entry.team == "A")

    async def test_finishing_twice_is_rejected(self, session):
        match = await staged_match(session)
        assert await finish_match(session, match.id, "A") is not None
        assert await finish_match(session, match.id, "B") is None

    async def test_custom_records_ignore_unfinished_matches(self, session):
        match = await staged_match(session)
        ids = [entry.player_id for entry in match.participants]
        assert await custom_records(session, ids, 1) == {}

        await finish_match(session, match.id, "A")
        records = await custom_records(session, ids, 1)
        assert len(records) == len(ids)
        assert sum(wins for _, wins in records.values()) == 5
        assert all(games == 1 for games, _ in records.values())

    async def test_custom_records_accumulate_within_a_server(self, session):
        first = await staged_match(session, server_id=1)
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
        first = await staged_match(session, server_id=1)
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
        match = await staged_match(session)
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
        assert await custom_records(session, [], 1) == {}

class TestLastAssignedRoles:
    async def test_returns_the_most_recent_role_per_player(self, session):
        first = await staged_match(session, server_id=1)
        await finish_match(session, first.id, "A")
        ids = [entry.player_id for entry in first.participants]
        expected = {entry.player_id: entry.role for entry in first.participants}

        assert await last_assigned_roles(session, ids, 1) == expected

    async def test_ignores_other_servers(self, session):
        match = await staged_match(session, server_id=1)
        ids = [entry.player_id for entry in match.participants]
        assert await last_assigned_roles(session, ids, 2) == {}

    async def test_can_exclude_the_current_match(self, session):
        match = await staged_match(session, server_id=1)
        ids = [entry.player_id for entry in match.participants]
        assert await last_assigned_roles(session, ids, 1, exclude_match_id=match.id) == {}

    async def test_empty_input(self, session):
        assert await last_assigned_roles(session, [], 1) == {}

    async def test_later_match_overrides_earlier_one(self, session):
        first = await staged_match(session, server_id=1)
        await finish_match(session, first.id, "A")
        ids = [entry.player_id for entry in first.participants]
        before = await last_assigned_roles(session, ids, 1)

        second = await create_second(session, ids[:5], server_id=1)
        after = await last_assigned_roles(session, ids, 1)

        # 2차전에는 인원 보충용 참가자도 있으므로 1차전 참가자만 확인한다.
        moved = {
            entry.player_id: entry.role
            for entry in second.participants
            if entry.player_id in ids
        }
        assert moved, "2차전에 1차전 참가자가 한 명도 없다"
        for player_id, role in moved.items():
            assert after[player_id] == role
        assert any(after[pid] != before[pid] for pid in moved)

async def named_match(session, server_id=5):
    """참가자마다 게임이름이 다른, 팀 배정까지 끝난 내전.

    사설 전적은 게임이름#태그로 맞추므로 이름이 겹치면 검증이 안 된다.
    """
    match = await create_match(session, server_id=server_id)
    for i in range(LOBBY_SIZE):
        player = await register(session, 2000 + i, f"named-{i}", name=f"플레이어{i}")
        await join_match(session, match.id, player.id)

    match = await get_match(session, match.id)
    result = find_best_teams(
        [build_profile(entry.player) for entry in match.participants],
        rng=random.Random(3),
    )
    return await save_teams(session, match.id, result)

def game_for(match, winner="A", swap=(), champions=0):
    """배정된 팀 그대로 winner 팀이 이긴 기록. swap 의 인덱스는 승패를 뒤집는다.

    champions 는 챔피언 번호의 시작점이다. 이어진 판마다 다르게 줘서 시리즈에
    쌓이는 챔피언을 구분한다.
    """
    return GameRecord(
        game_id=1,
        created_at=1,
        duration=1800,
        participants=tuple(
            ParticipantRecord(
                riot_id=riot_id_key(
                    entry.player.riot_game_name, entry.player.riot_tagline
                ),
                team_id=100 if entry.team == "A" else 200,
                win=(entry.team == winner) is (index not in swap),
                kills=index,
                deaths=1,
                assists=2,
                cs=100 + index,
                damage=1000 * index,
                damage_taken=800 * index,
                gold=500 * index,
                wards=index,
                first_blood=index == 0,
                first_tower=index == 1,
                position=ROLES[index % 5],
                champion_id=champions + index + 1,
            )
            for index, entry in enumerate(match.participants)
        ),
    )

class TestRecordedResults:
    async def test_every_participant_gets_their_stats(self, session):
        match = await named_match(session)
        status, saved = await finish_match_with_records(
            session, match.id, game_for(match)
        )

        assert status == "A"
        assert saved.completed is True
        assert (saved.team_a_score, saved.team_b_score) == (1, 0)
        for index, entry in enumerate(saved.participants):
            assert (entry.kills, entry.deaths, entry.assists) == (index, 1, 2)
            assert entry.cs == 100 + index
            assert entry.gold == 500 * index
            assert entry.win is (entry.team == "A")

    async def test_unmatched_players_still_get_the_team_result(self, session):
        """한 명이 다른 계정으로 뛰었어도 나머지 아홉 명의 성적은 남는다."""
        match = await named_match(session)
        record = game_for(match)
        dropped = record.participants[0]
        partial = replace(
            record,
            participants=tuple(
                one for one in record.participants if one is not dropped
            ),
        )

        status, saved = await finish_match_with_records(session, match.id, partial)
        by_id = {entry.player_id: entry for entry in saved.participants}
        left_out = by_id[match.participants[0].player_id]

        assert status == "A"
        assert left_out.win is (left_out.team == "A")
        assert left_out.kills is None
        assert sum(entry.kills is not None for entry in saved.participants) == 9

    async def test_duplicate_lanes_fall_back_to_the_assigned_role(self, session):
        """사설 게임 기록은 탑 라이너를 정글로 준다. 겹친 라인만 배정으로 되돌린다."""
        match = await named_match(session)
        record = game_for(match)
        broken = replace(
            record,
            participants=tuple(
                replace(one, position="JUNGLE" if entry.role == "TOP" else entry.role)
                for entry, one in zip(match.participants, record.participants)
            ),
        )

        _, saved = await finish_match_with_records(session, match.id, broken)

        # 탑·정글은 겹쳐서 배정 라인으로, 나머지는 파일 그대로.
        assert all(entry.played_role == entry.role for entry in saved.participants)
        assert sum(entry.played_role == "TOP" for entry in saved.participants) == 2

    async def test_the_lane_played_can_differ_from_the_assigned_one(self, session):
        """겹치지 않으면 파일에 적힌 라인을 그대로 남긴다."""
        match = await named_match(session)
        record = game_for(match)
        swapped = {"MID": "ADC", "ADC": "MID"}
        moved = replace(
            record,
            participants=tuple(
                replace(one, position=swapped.get(entry.role, entry.role))
                for entry, one in zip(match.participants, record.participants)
            ),
        )

        _, saved = await finish_match_with_records(session, match.id, moved)

        by_role = {entry.role: entry.played_role for entry in saved.participants}
        assert (by_role["MID"], by_role["ADC"]) == ("ADC", "MID")

    async def test_winner_comes_from_the_file(self, session):
        match = await named_match(session)
        status, saved = await finish_match_with_records(
            session, match.id, game_for(match, winner="B")
        )

        assert status == "B"
        assert (saved.team_a_score, saved.team_b_score) == (0, 1)

    async def test_sides_that_do_not_line_up_are_rejected(self, session):
        """로비에서 진영을 바꿔 들어가면 승리 팀을 특정할 수 없다."""
        match = await named_match(session)
        status, saved = await finish_match_with_records(
            session, match.id, game_for(match, swap=(0,))
        )

        assert (status, saved) == ("mismatch", None)
        assert (await get_match(session, match.id)).completed is False

    async def test_finishing_twice_is_rejected(self, session):
        match = await named_match(session)
        assert (await finish_match_with_records(session, match.id, game_for(match)))[0] == "A"
        status, _ = await finish_match_with_records(session, match.id, game_for(match))
        assert status == "closed"

    async def test_result_reaches_the_custom_record(self, session):
        match = await named_match(session)
        _, saved = await finish_match_with_records(session, match.id, game_for(match))

        records = await custom_records(
            session, [entry.player_id for entry in saved.participants], 5
        )
        for entry in saved.participants:
            assert records[entry.player_id] == (1, int(entry.team == "A"))

class TestCustomStats:
    async def test_averages_come_from_recorded_matches(self, session):
        match = await named_match(session)
        _, saved = await finish_match_with_records(session, match.id, game_for(match))
        entry = saved.participants[3]

        games, kda, cs, damage = await custom_stats(session, entry.player_id, 5)
        assert games == 1
        assert kda == pytest.approx((entry.kills + entry.assists) / entry.deaths)
        assert (cs, damage) == (entry.cs, entry.damage)

    async def test_button_only_results_are_excluded(self, session):
        """버튼으로 확정한 내전은 개인 성적이 비어 있어 평균에 넣을 수 없다."""
        match = await named_match(session)
        finished = await finish_match(session, match.id, "A")

        assert await custom_stats(session, finished.participants[0].player_id, 5) is None

    async def test_other_servers_are_excluded(self, session):
        match = await named_match(session)
        _, saved = await finish_match_with_records(session, match.id, game_for(match))

        assert await custom_stats(session, saved.participants[0].player_id, 99) is None

class TestPositionStats:
    """op.gg e스포츠 선수 기록과 같은 라인별 지표의 재료(합계)."""

    async def recorded(self, session, server_id=5):
        match = await named_match(session, server_id=server_id)
        _, saved = await finish_match_with_records(session, match.id, game_for(match))
        return saved

    async def test_sums_and_game_time_are_returned(self, session):
        saved = await self.recorded(session)
        # game_for: 30분 경기, index 번째 참가자는 딜 1000n / 받은 딜 800n /
        # 골드 500n / CS 100+n / 와드 n / 라인 ROLES[n % 5].
        entry = saved.participants[2]
        [row] = await custom_position_stats(session, entry.player_id, 5)

        assert row.role == ROLES[2]
        assert (row.games, row.wins) == (1, 1 if entry.win else 0)
        assert (row.damage, row.damage_taken, row.gold) == (2000, 1600, 1000)
        assert (row.cs, row.wards, row.seconds) == (102, 2, 1800)
        assert (row.kills, row.deaths, row.assists) == (2, 1, 2)

    async def test_first_blood_and_tower_are_counted(self, session):
        saved = await self.recorded(session)
        [head] = await custom_position_stats(session, saved.participants[0].player_id, 5)
        [tower] = await custom_position_stats(session, saved.participants[1].player_id, 5)

        assert (head.first_blood, head.first_tower) == (1, 0)
        assert (tower.first_blood, tower.first_tower) == (0, 1)

    async def test_positions_are_grouped_and_ordered_by_games(self, session):
        first = await self.recorded(session)
        player_id = first.participants[2].player_id

        # 같은 참가자들로 두 번째 내전을 치르되 라인을 한 칸씩 옮긴다.
        second = await named_match(session, server_id=5)
        record = game_for(second)
        moved = replace(
            record,
            participants=tuple(
                replace(one, position=ROLES[(ROLES.index(one.position) + 1) % 5])
                for one in record.participants
            ),
        )
        await finish_match_with_records(session, second.id, moved)

        # 세 번째 내전은 두 번째와 같은 라인이라 그 라인이 2경기가 된다.
        third = await named_match(session, server_id=5)
        await finish_match_with_records(
            session,
            third.id,
            replace(
                game_for(third),
                participants=tuple(
                    replace(one, position=ROLES[(ROLES.index(one.position) + 1) % 5])
                    for one in game_for(third).participants
                ),
            ),
        )

        rows = await custom_position_stats(session, player_id, 5)
        assert [(row.role, row.games) for row in rows] == [(ROLES[3], 2), (ROLES[2], 1)]

    async def test_button_only_results_are_excluded(self, session):
        """경기 시간이 없으면 분당 지표를 낼 수 없다."""
        match = await staged_match(session, server_id=6)
        await finish_match(session, match.id, "A")
        player_id = match.participants[0].player_id

        assert await custom_position_stats(session, player_id, 6) == []

    async def test_other_servers_are_excluded(self, session):
        saved = await self.recorded(session)
        player_id = saved.participants[0].player_id
        assert await custom_position_stats(session, player_id, 99) == []

class TestAliases:
    """부계정: 전적 파일에서 사람을 알아보는 데만 쓴다."""

    async def test_alias_is_stored_and_listed(self, session):
        player = await register(session, 1, "p-1", name="본계정")
        assert await add_alias(session, player.id, "부계정", "KR2") == "added"

        [alias] = (await aliases_for(session, [player.id]))[player.id]
        assert (alias.riot_game_name, alias.riot_tagline) == ("부계정", "KR2")

    async def test_someone_elses_main_cannot_be_claimed(self, session):
        mine = await register(session, 1, "p-1", name="내계정")
        await register(session, 2, "p-2", name="남의계정")

        assert await add_alias(session, mine.id, "남의계정", "KR1") == "taken"
        assert await aliases_for(session, [mine.id]) == {}

    async def test_the_same_alias_cannot_be_registered_twice(self, session):
        first = await register(session, 1, "p-1", name="첫번째")
        second = await register(session, 2, "p-2", name="두번째")
        await add_alias(session, first.id, "공용", "KR2")

        assert await add_alias(session, first.id, "공용", "KR2") == "mine"
        assert await add_alias(session, second.id, "공용", "KR2") == "taken"

    async def test_only_the_owner_can_remove_it(self, session):
        owner = await register(session, 1, "p-1", name="주인")
        other = await register(session, 2, "p-2", name="남")
        await add_alias(session, owner.id, "부계정", "KR2")
        [alias] = (await aliases_for(session, [owner.id]))[owner.id]

        assert await remove_alias(session, other.id, alias.id) is False
        assert await remove_alias(session, owner.id, alias.id) is True
        assert await aliases_for(session, [owner.id]) == {}

    async def test_records_are_matched_through_the_alias(self, session):
        match = await named_match(session)
        entry = match.participants[0]
        await add_alias(session, entry.player_id, "부계정", "KR2")

        # 그 사람만 부계정 이름으로 들어 있는 파일.
        record = game_for(match)
        renamed = replace(
            record,
            participants=tuple(
                replace(one, riot_id=riot_id_key("부계정", "KR2"))
                if index == 0
                else one
                for index, one in enumerate(record.participants)
            ),
        )

        status, saved = await finish_match_with_records(session, match.id, renamed)
        by_id = {row.player_id: row for row in saved.participants}

        assert status == "A"
        assert by_id[entry.player_id].kills == 0
        assert all(row.kills is not None for row in saved.participants)

class TestTraits:
    async def test_average_and_vote_count(self, session):
        target = await register(session, 1, "trait-target")
        for rater, score in ((10, 4), (11, 6), (12, 8)):
            await save_trait(session, target.id, rater, MAIN_CALL, score)

        scores = await trait_scores(session, [target.id])
        assert scores[target.id][MAIN_CALL] == (6.0, 3)

    async def test_rerating_overwrites_instead_of_adding(self, session):
        target = await register(session, 1, "trait-target")
        await save_trait(session, target.id, 10, CHAMPS, 3)
        await save_trait(session, target.id, 10, CHAMPS, 9)

        assert (await trait_scores(session, [target.id]))[target.id][CHAMPS] == (9.0, 1)

    async def test_traits_are_kept_apart(self, session):
        target = await register(session, 1, "trait-target")
        await save_trait(session, target.id, 10, MAIN_CALL, 2)
        await save_trait(session, target.id, 10, CHAMPS, 10)

        scores = (await trait_scores(session, [target.id]))[target.id]
        assert (scores[MAIN_CALL][0], scores[CHAMPS][0]) == (2.0, 10.0)

    async def test_unrated_players_are_absent(self, session):
        target = await register(session, 1, "trait-target")
        assert await trait_scores(session, [target.id]) == {}
        assert await trait_scores(session, []) == {}

class TestSpectators:
    async def test_watching_needs_no_riot_account(self, session):
        match = await create_match(session, server_id=7)
        status, updated = await watch_match(session, match.id, discord_id=555)

        assert status == "watching"
        assert [v.discord_id for v in updated.spectators] == [555]
        assert updated.participants == []

    async def test_watching_twice_is_rejected(self, session):
        match = await create_match(session, server_id=7)
        await watch_match(session, match.id, 555)
        assert (await watch_match(session, match.id, 555))[0] == "already"

    async def test_unwatch_removes_the_spectator(self, session):
        match = await create_match(session, server_id=7)
        await watch_match(session, match.id, 555)
        status, updated = await unwatch_match(session, match.id, 555)

        assert status == "left"
        assert updated.spectators == []

    async def test_unwatch_without_watching_is_rejected(self, session):
        match = await create_match(session, server_id=7)
        assert (await unwatch_match(session, match.id, 555))[0] == "absent"

    async def test_participants_cannot_also_spectate(self, session):
        match = await create_match(session, server_id=7)
        player = await register(session, 4242, "spectate-me")
        await join_match(session, match.id, player.id)

        assert (await watch_match(session, match.id, 4242))[0] == "playing"

    async def test_joining_moves_a_spectator_into_the_lobby(self, session):
        match = await create_match(session, server_id=7)
        player = await register(session, 4243, "switch-me")
        await watch_match(session, match.id, 4243)

        status, updated = await join_match(session, match.id, player.id)
        assert status == "joined"
        assert updated.spectators == []
        assert len(updated.participants) == 1

    async def test_spectators_do_not_fill_the_lobby(self, session):
        match = await create_match(session, server_id=7)
        for i in range(30):
            await watch_match(session, match.id, 6000 + i)

        player = await register(session, 4244, "still-room")
        assert (await join_match(session, match.id, player.id))[0] == "joined"

class TestMvpVotes:
    async def finished(self, session):
        match = await named_match(session)
        _, saved = await finish_match_with_records(session, match.id, game_for(match))
        return saved

    def winners(self, match):
        return [e.player_id for e in match.participants if e.win]

    async def test_a_vote_is_stored(self, session):
        match = await self.finished(session)
        target = self.winners(match)[0]

        await save_vote(session, match.id, 2000, target)
        counts, _ = await vote_counts(session, match.id)
        assert counts == {target: 1}

    async def test_one_vote_per_person_moves_instead_of_adding(self, session):
        """한 사람은 한 판에 한 표. 다시 고르면 옮겨진다."""
        match = await self.finished(session)
        first, second = self.winners(match)[:2]

        await save_vote(session, match.id, 2000, first)
        await save_vote(session, match.id, 2000, second)

        counts, _ = await vote_counts(session, match.id)
        assert counts == {second: 1}
        assert await vote_by(session, match.id, 2000) == second

    async def test_spectators_can_vote(self, session):
        # 관전 등록은 로비 단계에서만 된다. 끝난 내전에는 못 들어간다.
        match = await named_match(session)
        await watch_match(session, match.id, 8888)
        _, match = await finish_match_with_records(session, match.id, game_for(match))
        target = self.winners(match)[0]

        await save_vote(session, match.id, 8888, target)
        counts, by_spectator = await vote_counts(session, match.id)
        assert counts == {target: 1}
        assert by_spectator == {target: 1}, "관전자 표가 따로 세어지지 않았다"

    async def test_no_votes_means_no_mvp(self):
        assert pick_vote_mvp({}) is None

    async def test_clear_winner(self):
        assert pick_vote_mvp({1: 3, 2: 1}) == 1

    async def test_spectators_break_the_tie(self):
        assert pick_vote_mvp({1: 2, 2: 2}, {2: 1}) == 2

    async def test_an_unresolved_tie_gives_no_mvp(self):
        """임의로 하나를 고르면 AI 검증의 정답지가 오염된다."""
        assert pick_vote_mvp({1: 2, 2: 2}) is None
        assert pick_vote_mvp({1: 2, 2: 2}, {1: 1, 2: 1}) is None

    async def test_most_votes_wins(self, session):
        match = await self.finished(session)
        first, second = self.winners(match)[:2]

        await save_vote(session, match.id, 2000, first)
        await save_vote(session, match.id, 2001, first)
        await save_vote(session, match.id, 2002, second)

        assert await voted_mvp(session, match.id) == first

class TestMvpCounts:
    async def test_counts_only_completed_matches(self, session):
        match = await named_match(session)
        [a, b] = [e.player_id for e in match.participants[:2]]
        await save_vote(session, match.id, 2000, b)

        assert await mvp_counts(session, [a, b], 5) == {a: 0, b: 0}

        await finish_match_with_records(session, match.id, game_for(match))
        assert await mvp_counts(session, [a, b], 5) == {a: 0, b: 1}

    async def test_scoped_to_one_server(self, session):
        match = await named_match(session)
        [a, b] = [e.player_id for e in match.participants[:2]]
        await save_vote(session, match.id, 2000, b)
        await finish_match_with_records(session, match.id, game_for(match))

        assert await mvp_counts(session, [a, b], 99) == {a: 0, b: 0}

    async def test_empty_player_list(self, session):
        assert await mvp_counts(session, [], 5) == {}


class TestRematch:
    """「팀 그대로」로 이어지는 판과, 그 사슬에 쌓이는 챔피언."""

    async def played_match(self, session, champions=0):
        match = await named_match(session)
        _, saved = await finish_match_with_records(
            session, match.id, game_for(match, champions=champions)
        )
        return saved

    async def test_it_copies_every_team_and_lane(self, session):
        played = await self.played_match(session)

        status, again = await create_rematch(session, played.id)

        assert status == "created"
        assert again.previous_match_id == played.id
        assert again.completed is False
        assert {(e.player_id, e.team, e.role) for e in again.participants} == {
            (e.player_id, e.team, e.role) for e in played.participants
        }

    async def test_it_refuses_before_the_result_is_confirmed(self, session):
        match = await named_match(session)

        assert await create_rematch(session, match.id) == ("open", None)

    async def test_it_refuses_while_another_match_is_open(self, session):
        played = await self.played_match(session)
        await create_rematch(session, played.id)

        assert await create_rematch(session, played.id) == ("busy", None)

    async def test_champions_pile_up_along_the_chain(self, session):
        first = await self.played_match(session)
        _, opened = await create_rematch(session, first.id)
        _, second = await finish_match_with_records(
            session, opened.id, game_for(opened, champions=100)
        )
        _, third = await create_rematch(session, second.id)

        played, used = await series_champions(session, third)

        assert played == 2
        for index, entry in enumerate(first.participants):
            assert used[entry.player_id] == [index + 1, index + 101]

    async def test_a_fresh_match_has_no_pool(self, session):
        match = await named_match(session)

        assert await series_champions(session, match) == (0, {})
