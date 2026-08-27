import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.scoring import TAKEOVER_GAMES
from app.services.stats import (
    MATCH_CONCURRENCY,
    STATS_TTL,
    aggregate_matches,
    fetch_matches,
    is_fresh,
    kda,
    pick_solo_entry,
    profile_score,
)

PUUID = "me"

def match(position, win, k, d, a, puuid=PUUID):
    return {
        "info": {
            "participants": [
                {"puuid": "someone-else", "teamPosition": "TOP", "win": True,
                 "kills": 0, "deaths": 0, "assists": 0},
                {"puuid": puuid, "teamPosition": position, "win": win,
                 "kills": k, "deaths": d, "assists": a},
            ]
        }
    }

class TestPickSoloEntry:
    def test_picks_solo_queue_over_flex(self):
        entries = [
            {"queueType": "RANKED_FLEX_SR", "tier": "GOLD"},
            {"queueType": "RANKED_SOLO_5x5", "tier": "PLATINUM"},
        ]
        assert pick_solo_entry(entries)["tier"] == "PLATINUM"

    def test_unranked_returns_none(self):
        assert pick_solo_entry([]) is None
        assert pick_solo_entry([{"queueType": "RANKED_FLEX_SR"}]) is None

class TestKda:
    def test_deathless_game_does_not_divide_by_zero(self):
        assert kda(5, 0, 5) == 10.0

    def test_normal_game(self):
        assert kda(3, 2, 7) == 5.0

class TestAggregateMatches:
    def test_empty_history(self):
        result = aggregate_matches([], PUUID)
        assert result == {
            "games": 0, "wins": 0, "recent_win_rate": 0.0,
            "avg_kda": 0.0, "roles": {},
        }

    def test_ignores_matches_without_the_player(self):
        stranger = match("MIDDLE", True, 1, 1, 1, puuid="other")
        assert aggregate_matches([stranger], PUUID)["games"] == 0

    def test_overall_totals(self):
        matches = [
            match("MIDDLE", True, 4, 2, 6),   # kda 5.0
            match("MIDDLE", False, 1, 4, 3),  # kda 1.0
        ]
        result = aggregate_matches(matches, PUUID)
        assert result["games"] == 2
        assert result["wins"] == 1
        assert result["recent_win_rate"] == 0.5
        assert result["avg_kda"] == pytest.approx(3.0)

    def test_riot_positions_map_to_internal_roles(self):
        matches = [
            match("MIDDLE", True, 1, 1, 1),
            match("BOTTOM", True, 1, 1, 1),
            match("UTILITY", True, 1, 1, 1),
            match("JUNGLE", True, 1, 1, 1),
            match("TOP", True, 1, 1, 1),
        ]
        roles = aggregate_matches(matches, PUUID)["roles"]
        assert set(roles) == {"MID", "ADC", "SUPPORT", "JUNGLE", "TOP"}

    def test_aram_counts_overall_but_not_per_role(self):
        matches = [match("MIDDLE", True, 1, 1, 1), match("", True, 1, 1, 1)]
        result = aggregate_matches(matches, PUUID)
        assert result["games"] == 2
        assert list(result["roles"]) == ["MID"]
        assert result["roles"]["MID"]["games"] == 1

    def test_per_role_rates(self):
        matches = [
            match("MIDDLE", True, 4, 2, 6),
            match("MIDDLE", False, 1, 4, 3),
            match("TOP", True, 2, 1, 2),
        ]
        roles = aggregate_matches(matches, PUUID)["roles"]
        assert roles["MID"]["games"] == 2
        assert roles["MID"]["win_rate"] == 0.5
        assert roles["MID"]["avg_kda"] == pytest.approx(3.0)
        assert roles["TOP"]["win_rate"] == 1.0
        assert 0 <= roles["MID"]["role_score"] <= 100

class TestProfileScore:
    def profile(self, **kwargs):
        from tests.test_matchmaking import profile

        return profile(1, **kwargs)

    def test_unranked_player_still_gets_a_score(self):
        score = profile_score(self.profile(tier=None))
        assert 0 < score < 100

    def test_higher_tier_scores_higher(self):
        low = profile_score(self.profile(tier=20.0))
        high = profile_score(self.profile(tier=90.0))
        assert high > low

    def test_it_matches_what_balancing_uses(self):
        """화면에 뜬 점수와 팀을 가르는 점수가 같아야 한다."""
        from app.services.matchmaking import power_of

        built = self.profile(tier=70.0, main="MID")
        assert profile_score(built) == pytest.approx(power_of(built, "MID"))

    def test_custom_records_move_the_displayed_score(self):
        """예전에는 표시 점수가 내전 전적을 아예 빼고 계산했다."""
        without = profile_score(self.profile(tier=60.0))
        with_customs = profile_score(self.profile(tier=60.0, custom=100.0))
        assert with_customs > without

    def test_internal_rank_takes_over_after_enough_games(self):
        built = self.profile(tier=95.0, custom=50.0, internal=10.0)
        early = profile_score(built, custom_games=0)
        late = profile_score(built, custom_games=TAKEOVER_GAMES)
        assert late < early, "내전 판수가 쌓여도 솔랭 티어가 그대로 남았다"

class TestFetchMatches:
    def test_preserves_order_and_caps_concurrency(self):
        class FakeRiot:
            def __init__(self):
                self.active = 0
                self.peak = 0
                self.calls = 0

            async def get_match(self, match_id):
                self.calls += 1
                self.active += 1
                self.peak = max(self.peak, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                return {"id": match_id}

        riot = FakeRiot()
        ids = [f"KR_{i}" for i in range(20)]
        result = asyncio.run(fetch_matches(riot, ids))

        assert [item["id"] for item in result] == ids
        assert riot.calls == len(ids)
        assert riot.peak <= MATCH_CONCURRENCY
        assert riot.peak > 1, "동시 호출이 전혀 일어나지 않았다"

class TestIsFresh:
    def test_never_refreshed(self):
        assert is_fresh(None) is False

    def test_within_ttl(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_fresh(now - STATS_TTL + timedelta(seconds=1), now) is True
        assert is_fresh(now - STATS_TTL - timedelta(seconds=1), now) is False

    def test_naive_timestamps_are_treated_as_utc(self):
        """SQLite 는 타임존을 저장하지 않는다."""
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_fresh(datetime(2026, 1, 1) - timedelta(minutes=1), now) is True
        assert is_fresh(datetime(2026, 1, 1) - timedelta(hours=2), now) is False
