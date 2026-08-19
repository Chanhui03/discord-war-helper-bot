import pytest

from app.services.scoring import (
    APEX_LP_RANGE,
    NEUTRAL,
    base_score,
    performance_score,
    role_affinity,
    role_power,
    role_score,
    tier_score,
)

class TestTierScore:
    def test_unranked_returns_none(self):
        assert tier_score(None, None, 0) is None

    def test_unknown_tier_returns_none(self):
        assert tier_score("WOOD", "IV", 0) is None

    def test_lowest_rank_is_zero(self):
        assert tier_score("IRON", "IV", 0) == 0.0

    def test_challenger_is_capped_at_100(self):
        assert tier_score("CHALLENGER", None, APEX_LP_RANGE) == 100.0
        assert tier_score("CHALLENGER", None, 5000) == 100.0

    def test_apex_range_is_not_flattened(self):
        """마스터~챌린저가 한 점수로 뭉개지지 않아야 한다."""
        master = tier_score("MASTER", None, 0)
        grandmaster = tier_score("GRANDMASTER", None, 700)
        challenger = tier_score("CHALLENGER", None, 1400)
        assert master < grandmaster < challenger < 100.0
        assert challenger - master > 30.0

    def test_diamond_one_sits_just_below_master(self):
        assert tier_score("DIAMOND", "I", 99) < tier_score("MASTER", None, 0)

    def test_monotonic_across_tiers_divisions_and_lp(self):
        ladder = [
            tier_score("IRON", "IV", 0),
            tier_score("IRON", "IV", 50),
            tier_score("IRON", "III", 0),
            tier_score("IRON", "I", 99),
            tier_score("BRONZE", "IV", 0),
            tier_score("GOLD", "II", 50),
            tier_score("EMERALD", "I", 0),
            tier_score("DIAMOND", "I", 99),
            tier_score("MASTER", None, 0),
            tier_score("GRANDMASTER", None, 200),
        ]
        assert ladder == sorted(ladder)
        assert all(0 <= s <= 100 for s in ladder)

    def test_apex_tiers_share_one_lp_pool(self):
        # 마스터 이상은 디비전이 없고 LP 로만 구분된다.
        assert tier_score("MASTER", None, 300) == tier_score("CHALLENGER", None, 300)

class TestRoleScore:
    def test_no_games_returns_neutral(self):
        assert role_score(0, 0.0, 0.0) == NEUTRAL

    def test_small_sample_shrinks_toward_neutral(self):
        few = role_score(2, 1.0, 5.0)
        many = role_score(10, 1.0, 5.0)
        assert NEUTRAL < few < many == 100.0

    def test_bad_record_scores_below_neutral(self):
        assert role_score(20, 0.2, 1.0) < NEUTRAL

    def test_confidence_saturates_at_ten_games(self):
        assert role_score(10, 0.7, 3.0) == role_score(50, 0.7, 3.0)

class TestPerformanceScore:
    def test_kda_five_is_full_marks(self):
        assert performance_score(5.0) == 100.0
        assert performance_score(9.9) == 100.0

    def test_scales_linearly_below_five(self):
        assert performance_score(2.5) == 50.0

class TestBaseScore:
    def test_no_data_returns_neutral(self):
        assert base_score() == NEUTRAL

    def test_single_component_is_returned_as_is(self):
        # 가중치가 재분배되므로 티어 하나만 있으면 그 값이 그대로 나온다.
        assert base_score(tier=80.0) == 80.0

    def test_missing_weights_are_redistributed(self):
        # tier 40% + role 20% -> 재정규화하면 2:1 가중 평균
        assert base_score(tier=90.0, role=60.0) == pytest.approx(80.0)

    def test_all_equal_components_give_that_value(self):
        assert base_score(
            tier=70.0, role=70.0, recent_form=70.0,
            performance=70.0, custom=70.0, mastery=70.0,
        ) == pytest.approx(70.0)

    def test_tier_dominates_role(self):
        tier_heavy = base_score(tier=100.0, role=0.0)
        role_heavy = base_score(tier=0.0, role=100.0)
        assert tier_heavy > role_heavy

class TestRoleAffinity:
    def test_unset_preferences_are_unknown(self):
        assert role_affinity("MID", None, None) == "unknown"

    def test_main_secondary_and_off(self):
        assert role_affinity("ADC", "ADC", "MID") == "main"
        assert role_affinity("MID", "ADC", "MID") == "secondary"
        assert role_affinity("TOP", "ADC", "MID") == "off"

class TestRolePower:
    def test_design_document_worked_example(self):
        """설계서 6.1: 기본 80 -> 주라인 ADC 80, 부라인 MID 68, 비선호 TOP 56."""
        assert role_power(80.0, "ADC", "ADC", "MID") == pytest.approx(80.0)
        assert role_power(80.0, "MID", "ADC", "MID") == pytest.approx(68.0)
        assert role_power(80.0, "TOP", "ADC", "MID") == pytest.approx(56.0)

    def test_unknown_preference_uses_lowest_multiplier(self):
        assert role_power(80.0, "TOP", None, None) == pytest.approx(48.0)
