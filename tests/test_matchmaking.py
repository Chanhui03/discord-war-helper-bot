import random
import time

import pytest

from app.roles import ROLES
from app.services.matchmaking import (
    LOBBY_SIZE,
    TEAM_SIZE,
    PlayerProfile,
    assignment_options,
    balance_breakdown,
    find_best_teams,
    fit_loss,
    make_plan,
    power_of,
    power_table,
)

def profile(pid, tier=60.0, main=None, secondary=None, win_rate=0.5,
            recent=50.0, performance=50.0, role_scores=None, custom=None,
            avoid=None, must_avoid=False):
    return PlayerProfile(
        player_id=pid,
        display=f"P{pid}",
        tier=tier,
        recent_form=recent,
        performance=performance,
        custom=custom,
        win_rate=win_rate,
        main_role=main,
        secondary_role=secondary,
        avoid_role=avoid,
        must_avoid=must_avoid,
        role_scores=role_scores or {},
    )

def ten(**kwargs):
    return [profile(i, **kwargs) for i in range(LOBBY_SIZE)]

SEED = random.Random(1234)

class TestPowerOf:
    def test_main_role_beats_off_role(self):
        p = profile(1, main="ADC", secondary="MID")
        assert power_of(p, "ADC") > power_of(p, "MID") > power_of(p, "TOP")

    def test_no_preference_uses_unknown_multiplier(self):
        p = profile(1)
        assert power_of(p, "TOP") == pytest.approx(power_of(p, "ADC"))

    def test_role_score_raises_power_in_that_role(self):
        weak = profile(1, main="MID", role_scores={"MID": 10.0})
        strong = profile(2, main="MID", role_scores={"MID": 90.0})
        assert power_of(strong, "MID") > power_of(weak, "MID")

class TestAssignmentOptions:
    def test_enumerates_every_permutation(self):
        team = [profile(i) for i in range(TEAM_SIZE)]
        options = assignment_options(team, power_table(team))
        assert len(options) == 120  # 5!
        assert len({order for _, _, order in options}) == 120
        for _, _, order in options:
            assert set(order) == set(ROLES)

    def test_totals_match_the_power_table(self):
        team = [profile(i, main=role) for i, role in enumerate(ROLES)]
        table = power_table(team)
        for total, powers, order in assignment_options(team, table):
            assert total == pytest.approx(sum(powers))
            assert total == pytest.approx(
                sum(table[m.player_id][r] for m, r in zip(team, order))
            )

class TestMakePlan:
    def test_power_equals_sum_of_assigned_roles(self):
        team = [profile(i, main=role) for i, role in enumerate(ROLES)]
        table = power_table(team)
        plan = make_plan(team, ROLES, table)
        assert plan.power == pytest.approx(
            sum(table[m.player_id][r] for m, r in plan.members)
        )
        assert {role for _, role in plan.members} == set(ROLES)

class TestFitLoss:
    def test_zero_when_everyone_is_on_their_best_role(self):
        team_a = [profile(i, main=role) for i, role in enumerate(ROLES)]
        team_b = [profile(i + 5, main=role) for i, role in enumerate(ROLES)]
        table = power_table(team_a + team_b)
        plan_a = make_plan(team_a, ROLES, table)
        plan_b = make_plan(team_b, ROLES, table)
        assert fit_loss(plan_a, plan_b, table) == pytest.approx(0.0)

    def test_positive_when_players_are_off_role(self):
        team_a = [profile(i, main=role) for i, role in enumerate(ROLES)]
        team_b = [profile(i + 5, main=role) for i, role in enumerate(ROLES)]
        table = power_table(team_a + team_b)
        shifted = ROLES[1:] + ROLES[:1]
        plan_a = make_plan(team_a, shifted, table)
        plan_b = make_plan(team_b, ROLES, table)
        assert fit_loss(plan_a, plan_b, table) > 0

class TestFindBestTeams:
    def test_rejects_wrong_player_count(self):
        with pytest.raises(ValueError, match="10명"):
            find_best_teams([profile(i) for i in range(9)])

    def test_searches_every_symmetric_split(self):
        result = find_best_teams(ten(), rng=SEED)
        assert result.splits == 126  # 252 / 2 (A·B 대칭 제거)
        assert 0 < result.evaluated <= 126 * 120 * 120

    def test_teams_partition_all_players(self):
        result = find_best_teams(ten(), rng=SEED)
        a = {m.player_id for m, _ in result.team_a.members}
        b = {m.player_id for m, _ in result.team_b.members}
        assert len(a) == len(b) == TEAM_SIZE
        assert not (a & b)
        assert a | b == set(range(LOBBY_SIZE))

    def test_every_team_covers_all_five_roles(self):
        result = find_best_teams(ten(), rng=SEED)
        for team in (result.team_a, result.team_b):
            assert {role for _, role in team.members} == set(ROLES)

    def test_identical_players_are_perfectly_balanced(self):
        result = find_best_teams(ten(), rng=SEED)
        assert result.score == pytest.approx(0.0)

    def test_strong_players_are_split_across_teams(self):
        players = [profile(i, tier=30.0) for i in range(LOBBY_SIZE)]
        players[0] = profile(0, tier=100.0)
        players[1] = profile(1, tier=100.0)
        result = find_best_teams(players, rng=random.Random(7))

        a = {m.player_id for m, _ in result.team_a.members}
        assert len({0, 1} & a) == 1, "고티어 두 명이 같은 팀에 몰렸다"

    def test_seeded_run_is_reproducible(self):
        players = ten()
        first = find_best_teams(players, rng=random.Random(99))
        second = find_best_teams(players, rng=random.Random(99))
        assert [m.player_id for m, _ in first.team_a.members] == [
            m.player_id for m, _ in second.team_a.members
        ]

    def test_tiebreaker_varies_across_seeds(self):
        players = ten()
        seen = {
            tuple(
                sorted(m.player_id for m, _ in find_best_teams(
                    players, rng=random.Random(seed)
                ).team_a.members)
            )
            for seed in range(8)
        }
        assert len(seen) > 1, "동점 조합인데 매번 같은 팀이 나온다"

    def test_breakdown_matches_reported_components(self):
        result = find_best_teams(ten(tier=70.0), rng=SEED)
        table = power_table(ten(tier=70.0))
        assert set(result.breakdown) == {
            "skill", "role", "win_rate", "recent_form", "fit",
        }
        assert result.breakdown == balance_breakdown(
            result.team_a, result.team_b, table
        )
        assert all(v >= -1e-9 for v in result.breakdown.values())

    def test_completes_quickly(self):
        players = [
            profile(i, tier=40.0 + i * 5, main=ROLES[i % 5],
                    secondary=ROLES[(i + 1) % 5],
                    role_scores={ROLES[i % 5]: 50.0 + i})
            for i in range(LOBBY_SIZE)
        ]
        started = time.perf_counter()
        find_best_teams(players, rng=SEED)
        assert time.perf_counter() - started < 10.0

class TestRoleFitPenalty:
    """차이 항만 최소화하면 전원이 비선호 라인에 배치되는 문제를 막는지 본다."""

    def test_specialists_keep_their_main_role(self):
        # 라인마다 주라인 지정자가 정확히 2명씩 있는 로비.
        players = [
            profile(i, main=ROLES[i % TEAM_SIZE], tier=60.0)
            for i in range(LOBBY_SIZE)
        ]
        result = find_best_teams(players, rng=random.Random(11))

        assigned = [
            (member.main_role, role)
            for team in (result.team_a, result.team_b)
            for member, role in team.members
        ]
        assert all(main == role for main, role in assigned)

    def test_keeps_most_of_the_available_power(self):
        players = [
            profile(i, tier=40.0 + i * 4, main=ROLES[i % TEAM_SIZE],
                    secondary=ROLES[(i + 2) % TEAM_SIZE])
            for i in range(LOBBY_SIZE)
        ]
        table = power_table(players)
        ceiling = sum(max(table[p.player_id].values()) for p in players)
        result = find_best_teams(players, rng=random.Random(5))

        used = result.team_a.power + result.team_b.power
        assert used / ceiling > 0.9, "적합도 손실이 너무 크다"

    def test_still_balances_the_two_teams(self):
        players = [
            profile(i, tier=30.0 + i * 7, main=ROLES[i % TEAM_SIZE])
            for i in range(LOBBY_SIZE)
        ]
        result = find_best_teams(players, rng=random.Random(5))
        gap = abs(result.team_a.power - result.team_b.power)
        assert gap < 5.0, f"팀 전투력 차이가 {gap:.1f}로 크다"


class TestPruningIsExact:
    """가지치기를 넣은 탐색이 전수 탐색과 같은 최소값을 찾는지 확인한다."""

    @staticmethod
    def brute_force_best(profiles):
        from itertools import combinations, permutations

        from app.roles import ROLES as R
        from app.services.matchmaking import (
            BALANCE_WEIGHTS,
            assignment_options,
            team_recent_form,
            team_win_rate,
        )

        table = power_table(profiles)
        total_best = sum(max(table[p.player_id].values()) for p in profiles)
        best = float("inf")

        for combo in combinations(range(1, LOBBY_SIZE), TEAM_SIZE - 1):
            a_index = (0,) + combo
            b_index = tuple(i for i in range(LOBBY_SIZE) if i not in a_index)
            team_a = [profiles[i] for i in a_index]
            team_b = [profiles[i] for i in b_index]
            constant = (
                BALANCE_WEIGHTS["win_rate"]
                * abs(team_win_rate(team_a) - team_win_rate(team_b)) * 100
                + BALANCE_WEIGHTS["recent_form"]
                * abs(team_recent_form(team_a) - team_recent_form(team_b))
                + BALANCE_WEIGHTS["fit"] * total_best
            )
            for sa, pa, _ in assignment_options(team_a, table):
                for sb, pb, _ in assignment_options(team_b, table):
                    score = (
                        BALANCE_WEIGHTS["skill"] * abs(sa - sb)
                        + BALANCE_WEIGHTS["role"] / len(R)
                        * sum(abs(x - y) for x, y in zip(pa, pb))
                        - BALANCE_WEIGHTS["fit"] * (sa + sb)
                        + constant
                    )
                    best = min(best, score)
        return best

    def test_matches_brute_force_on_a_varied_lobby(self):
        players = [
            profile(i, tier=35.0 + i * 6, main=ROLES[i % 5],
                    secondary=ROLES[(i + 3) % 5], win_rate=0.35 + i * 0.03,
                    recent=40.0 + i * 3, performance=30.0 + i * 5,
                    role_scores={ROLES[i % 5]: 45.0 + i * 4})
            for i in range(LOBBY_SIZE)
        ]
        result = find_best_teams(players, rng=random.Random(0))
        expected = self.brute_force_best(players)
        # 동점 구간에서 무작위로 고르므로 오차 허용치는 TIEBREAK_EPSILON.
        assert result.score == pytest.approx(expected, abs=0.5)


class TestAvoidRole:
    """기피 라인: 직전 내전에서 갔으면 이번에는 하드 금지."""

    def test_compensated_player_never_gets_the_avoided_role(self):
        players = [profile(i, main=ROLES[i % 5]) for i in range(LOBBY_SIZE)]
        players[0] = profile(0, main="MID", avoid="JUNGLE", must_avoid=True)

        for seed in range(10):
            result = find_best_teams(players, rng=random.Random(seed))
            assigned = {
                member.player_id: role
                for team in (result.team_a, result.team_b)
                for member, role in team.members
            }
            assert assigned[0] != "JUNGLE", f"seed={seed} 에서 기피 라인에 배정됨"
            assert result.bans_honoured

    def test_many_compensated_players_are_all_honoured(self):
        # 정글러가 부족해 매번 같은 사람들이 정글을 가는 상황.
        players = [
            profile(i, main=ROLES[i % 5], avoid="JUNGLE", must_avoid=i < 4)
            for i in range(LOBBY_SIZE)
        ]
        result = find_best_teams(players, rng=random.Random(3))
        for team in (result.team_a, result.team_b):
            for member, role in team.members:
                if member.must_avoid:
                    assert role != "JUNGLE"
        assert result.bans_honoured

    def test_uncompensated_player_may_still_take_the_avoided_role(self):
        """금지는 보상 대상자에게만 적용된다. 그 외에는 배수로만 불리하다."""
        players = [profile(i, main="MID", avoid="JUNGLE") for i in range(LOBBY_SIZE)]
        result = find_best_teams(players, rng=random.Random(1))
        roles = [role for team in (result.team_a, result.team_b)
                 for _, role in team.members]
        assert roles.count("JUNGLE") == 2  # 팀당 하나씩 반드시 채워진다
        assert result.bans_honoured

    def test_falls_back_when_the_ban_cannot_be_satisfied(self):
        # 9명이 정글을 금지당하면 정글 슬롯 2개를 채울 수 없다.
        players = [
            profile(i, main="MID", avoid="JUNGLE", must_avoid=i < 9)
            for i in range(LOBBY_SIZE)
        ]
        result = find_best_teams(players, rng=random.Random(1))
        assert result.bans_honoured is False, "불가능한데도 제약을 지켰다고 보고했다"
        assert len(result.team_a.members) == len(result.team_b.members) == TEAM_SIZE

    def test_avoided_role_lowers_power(self):
        player = profile(1, main="MID", secondary="TOP", avoid="JUNGLE")
        assert power_of(player, "JUNGLE") < power_of(player, "ADC")
        assert power_of(player, "ADC") < power_of(player, "TOP")
