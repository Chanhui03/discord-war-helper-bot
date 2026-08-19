import pytest

from app.services.stats import (
    aggregate_matches,
    kda,
    pick_solo_entry,
    player_score,
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

class TestPlayerScore:
    def test_unranked_player_still_gets_a_score(self):
        score = player_score(None, None, 0, 0.5, 2.5)
        assert 0 < score < 100

    def test_higher_tier_scores_higher(self):
        low = player_score("SILVER", "IV", 0, 0.5, 2.5)
        high = player_score("DIAMOND", "I", 0, 0.5, 2.5)
        assert high > low

    def test_main_role_score_is_included(self):
        without = player_score("GOLD", "II", 50, 0.5, 2.5)
        with_bad_role = player_score("GOLD", "II", 50, 0.5, 2.5, main_role_score=0.0)
        assert with_bad_role < without

class TestFetchMatches:
    def test_preserves_order_and_caps_concurrency(self):
        import asyncio

        from app.services.stats import MATCH_CONCURRENCY, fetch_matches

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
        from app.services.stats import is_fresh

        assert is_fresh(None) is False

    def test_within_ttl(self):
        from datetime import datetime, timedelta, timezone

        from app.services.stats import STATS_TTL, is_fresh

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_fresh(now - STATS_TTL + timedelta(seconds=1), now) is True
        assert is_fresh(now - STATS_TTL - timedelta(seconds=1), now) is False

    def test_naive_timestamps_are_treated_as_utc(self):
        """SQLite 는 타임존을 저장하지 않는다."""
        from datetime import datetime, timedelta, timezone

        from app.services.stats import is_fresh

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_fresh(datetime(2026, 1, 1) - timedelta(minutes=1), now) is True
        assert is_fresh(datetime(2026, 1, 1) - timedelta(hours=2), now) is False
