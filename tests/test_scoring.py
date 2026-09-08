import pytest

from app.services.scoring import (
    APEX_LP_RANGE,
    INTERNAL_ADJUST,
    MMR_ADJUST,
    MMR_K,
    MMR_SPAN,
    MMR_START,
    NEUTRAL,
    adjustment,
    base_score,
    mastery_score,
    mmr_adjustment,
    performance_score,
    rate_matches,
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
        # tier 55% + role 10% -> 재정규화하면 11:2 가중 평균
        assert base_score(tier=90.0, role=25.0) == pytest.approx(80.0)

    def test_all_equal_components_give_that_value(self):
        # 평균에 들어가는 넷만. 나머지는 더해지는 값이라 여기 오지 않는다.
        assert base_score(
            tier=70.0, role=70.0, recent_form=70.0, performance=70.0
        ) == pytest.approx(70.0)

    def test_tier_dominates_role(self):
        tier_heavy = base_score(tier=100.0, role=0.0)
        role_heavy = base_score(tier=0.0, role=100.0)
        assert tier_heavy > role_heavy

    def test_unranked_does_not_hand_its_weight_to_kda(self):
        """언랭이라고 티어 가중치를 빼면 KDA 하나로 마스터급 점수가 나온다."""
        unranked = base_score(performance=100.0, recent_form=60.0)
        assert unranked == pytest.approx(
            base_score(tier=NEUTRAL, performance=100.0, recent_form=60.0)
        )
        assert unranked < base_score(tier=75.0, performance=100.0, recent_form=60.0)

class TestInternalAdjustments:
    """내전에서 온 지표는 평균에 섞이지 않고 더해진다."""

    def test_no_record_changes_nothing(self):
        assert base_score(tier=80.0, internal=None, mastery=None, follow=None) == 80.0

    def test_being_neutral_is_the_same_as_having_no_record(self):
        assert base_score(tier=80.0, internal=NEUTRAL) == base_score(tier=80.0)

    def test_internal_rank_moves_both_ways(self):
        assert base_score(tier=80.0, internal=100.0) == pytest.approx(
            80.0 + INTERNAL_ADJUST
        )
        assert base_score(tier=80.0, internal=0.0) == pytest.approx(
            80.0 - INTERNAL_ADJUST
        )

    def test_it_lifts_every_tier_by_the_same_amount(self):
        """가중 평균에 섞었을 때는 잘하는 사람이 오히려 내려갔다."""
        gains = [
            base_score(tier=t, internal=100.0, mastery=100.0, follow=100.0)
            - base_score(tier=t)
            for t in (20.0, 40.0, 60.0)
        ]
        assert gains[0] == pytest.approx(gains[1]) == pytest.approx(gains[2])
        assert gains[0] > 0

    def test_champion_pool_and_follow_only_add(self):
        """둘은 1~10 평가라 중립 아래로 내려가지 않는다. 깎이지 않는다."""
        assert base_score(tier=60.0, mastery=100.0, follow=100.0) > 60.0
        assert mastery_score(50.0, None, 0, 0) == NEUTRAL
        assert adjustment(NEUTRAL, 5.0) == 0.0

    def test_the_score_stays_in_range(self):
        assert base_score(tier=99.0, internal=100.0, mastery=100.0, follow=100.0) == 100.0
        assert base_score(tier=1.0, internal=0.0, mmr=0.0) == 0.0

class TestRoleAffinity:
    def test_unset_preferences_are_unknown(self):
        assert role_affinity("MID", None, None) == "unknown"

    def test_avoid_beats_every_other_classification(self):
        # 기피 라인은 주라인으로도 지정돼 있어도 기피가 우선한다.
        assert role_affinity("MID", "MID", "TOP", "MID") == "avoid"
        assert role_affinity("JUNGLE", "MID", "TOP", "JUNGLE") == "avoid"
        assert role_affinity("JUNGLE", None, None, "JUNGLE") == "avoid"

    def test_avoid_unset_keeps_previous_behaviour(self):
        assert role_affinity("JUNGLE", "MID", "TOP", None) == "off"

    def test_main_secondary_and_off(self):
        assert role_affinity("ADC", "ADC", "MID") == "main"
        assert role_affinity("MID", "ADC", "MID") == "secondary"
        assert role_affinity("TOP", "ADC", "MID") == "off"

class TestRolePower:
    def test_design_document_worked_example(self):
        """설계서 6.1: 기본 80 -> 주라인 ADC 80, 부라인 MID 77, 비선호 TOP 72."""
        assert role_power(80.0, "ADC", "ADC", "MID") == pytest.approx(80.0)
        assert role_power(80.0, "MID", "ADC", "MID") == pytest.approx(77.0)
        assert role_power(80.0, "TOP", "ADC", "MID") == pytest.approx(72.0)

    def test_unknown_preference_is_penalised_more_than_off_role(self):
        assert role_power(80.0, "TOP", None, None) == pytest.approx(70.0)

    def test_avoided_role_is_worse_than_off_role(self):
        avoided = role_power(80.0, "JUNGLE", "MID", "TOP", "JUNGLE")
        off = role_power(80.0, "ADC", "MID", "TOP", "JUNGLE")
        assert avoided == pytest.approx(68.0)  # 80 - 12
        assert avoided < off == pytest.approx(72.0)

    def test_penalty_does_not_depend_on_how_good_you_are(self):
        """부라인에서 잃는 점수는 실력에 비례하지 않는다. 배수를 버린 이유다."""
        strong = role_power(80.0, "TOP", "MID", None) - role_power(80.0, "MID", "MID", None)
        weak = role_power(40.0, "TOP", "MID", None) - role_power(40.0, "MID", "MID", None)
        assert strong == pytest.approx(weak)

    def test_never_goes_below_zero(self):
        assert role_power(5.0, "TOP", "MID", "ADC", "TOP") == 0.0

class TestCustomMmr:
    SWEEP = ([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])

    def test_no_matches_means_no_rating(self):
        assert rate_matches([]) == {}
        assert mmr_adjustment(None) == 0.0

    def test_the_starting_value_moves_nothing(self):
        assert mmr_adjustment(MMR_START) == 0.0

    def test_it_is_zero_sum(self):
        rated = rate_matches([self.SWEEP] * 3)
        assert sum(rated.values()) == pytest.approx(MMR_START * len(rated))

    def test_winning_raises_and_losing_lowers(self):
        rated = rate_matches([self.SWEEP])
        assert mmr_adjustment(rated[1]) > 0.0 > mmr_adjustment(rated[6])
        # 팀 평균이 같으면 한 판에 K/2 만큼 움직인다.
        assert rated[1] - MMR_START == pytest.approx(MMR_K / 2)

    def test_beating_a_weak_team_is_worth_less(self):
        """같은 1승이어도 상대가 누구였는지에 따라 오르는 폭이 다르다."""
        first = rate_matches([self.SWEEP])[1] - MMR_START
        fourth = rate_matches([self.SWEEP] * 4)[1] - rate_matches([self.SWEEP] * 3)[1]
        assert fourth < first

    def test_losing_to_a_weak_team_hurts_more(self):
        upset = rate_matches([self.SWEEP] * 3 + [(self.SWEEP[1], self.SWEEP[0])])
        even = rate_matches([self.SWEEP] * 3)
        assert even[1] - upset[1] > MMR_K / 2

    def test_a_newcomer_starts_neutral(self):
        """중간에 합류한 사람은 기록이 없으니 중립에서 시작한다."""
        assert rate_matches([self.SWEEP]).get(11) is None
        rated = rate_matches([self.SWEEP, ([1, 2, 3, 4, 11], [6, 7, 8, 9, 12])])
        assert mmr_adjustment(rated[11]) > 0.0  # 첫 판을 이겼다

    def test_adjustment_is_capped(self):
        assert mmr_adjustment(MMR_START + MMR_SPAN) == pytest.approx(MMR_ADJUST)
        assert mmr_adjustment(MMR_START + MMR_SPAN * 5) == pytest.approx(MMR_ADJUST)
        assert mmr_adjustment(MMR_START - MMR_SPAN * 5) == pytest.approx(-MMR_ADJUST)

    def test_it_lifts_everyone_who_wins_regardless_of_tier(self):
        """가중 평균에 섞으면 5연승한 마스터의 점수가 오히려 내려갔다."""
        rated = rate_matches([self.SWEEP] * 5)
        for tier in (24.2, 60.0, 72.8):
            assert base_score(tier=tier, mmr=rated[1]) > base_score(tier=tier)
            assert base_score(tier=tier, mmr=rated[6]) < base_score(tier=tier)

    def test_the_score_stays_in_range(self):
        assert base_score(tier=100.0, mmr=MMR_START + MMR_SPAN) == 100.0
        assert base_score(tier=0.0, mmr=MMR_START - MMR_SPAN) == 0.0
