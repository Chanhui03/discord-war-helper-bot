import random

import pytest

from app.bot.commands.ability import status_embed
from app.bot.messages import LIST_LIMIT
from app.bot.commands.customs import trait_field
from app.services.matchmaking import (
    LOBBY_SIZE,
    find_best_teams,
    power_of,
    top_callers,
)
from app.services.scoring import (
    NEUTRAL,
    POOL_FULL,
    POOL_MIN_POINTS,
    POOL_SEASON_GAMES,
    TRAIT_FADE_GAMES,
    TRAIT_MIN_VOTES,
    champion_pool_score,
    mastery_score,
    trait_score,
    trait_value,
)

def pool(points, season_games=POOL_SEASON_GAMES):
    """따로 말하지 않으면 솔랭 표본이 충분한 사람으로 본다."""
    return champion_pool_score(points, season_games)
from app.traits import CHAMPS, FOLLOW, MAIN_CALL, summary
from tests.test_matchmaking import profile

class TestTraitScore:
    def test_votes_below_the_threshold_are_ignored(self):
        assert trait_score(10.0, TRAIT_MIN_VOTES - 1, 0) is None
        assert trait_score(10.0, TRAIT_MIN_VOTES, 0) is not None

    def test_one_is_the_baseline_not_the_worst(self):
        """매기는 사람이 '기본 1점, 잘하면 더'로 쓴다. 1 을 0 으로 읽으면
        기본값을 준 사람이 최하점이 된다."""
        assert trait_score(1.0, 3, 0) == pytest.approx(NEUTRAL)
        assert trait_score(10.0, 3, 0) == pytest.approx(100.0)

    def test_it_only_ever_adds(self):
        scores = [trait_score(n, 3, 0) for n in range(1, 11)]
        assert scores == sorted(scores)
        assert min(scores) == pytest.approx(NEUTRAL), "평가가 감점으로 작용했다"

    def test_it_fades_as_custom_games_pile_up(self):
        full = trait_score(10.0, 3, 0)
        half = trait_score(10.0, 3, TRAIT_FADE_GAMES // 2)

        assert half == pytest.approx(50.0 + (full - 50.0) / 2)
        assert trait_score(10.0, 3, TRAIT_FADE_GAMES) is None

    def test_no_rating_at_all(self):
        assert trait_score(None, 0, 0) is None

class TestChampionPoolScore:
    def test_no_data_returns_none(self):
        assert pool([]) is None

    def test_champions_below_the_floor_are_ignored(self):
        """갓 만든 계정의 1~2천 점이 폭으로 잡히면 안 된다."""
        assert pool([1_200, 700]) is None
        assert pool([POOL_MIN_POINTS, POOL_MIN_POINTS]) is not None

    def test_a_one_trick_gets_no_bonus_but_no_penalty(self):
        # 주력 대비 절반에 못 미치는 챔피언은 저격밴을 맞으면 대신 못 꺼낸다.
        # 그래도 깎지는 않는다. 가산 전용이다.
        assert pool([500_000, 20_000, 15_000]) == pytest.approx(NEUTRAL)

    def test_score_rises_with_each_comparable_champion(self):
        one = pool([100_000])
        two = pool([100_000, 60_000])
        three = pool([100_000, 60_000, 55_000])
        assert one == pytest.approx(NEUTRAL) and NEUTRAL < two < three < 100.0

    def test_full_marks_at_the_saturation_point(self):
        wide = [100_000] * POOL_FULL
        assert pool(wide) == 100.0
        assert pool(wide + [100_000] * 5) == 100.0

    def test_it_measures_ratio_not_volume(self):
        """총 플레이량이 적어도 고르게 했으면 폭은 넓다."""
        light = pool([12_000, 11_000, 10_000])
        heavy = pool([1_200_000, 1_100_000, 1_000_000])
        assert light == heavy

    def test_an_overwhelming_main_hides_a_deep_second(self):
        """알려진 한계: 비율로만 보면 800k/300k 가 원트릭으로 잡힌다."""
        assert pool([800_000, 300_000]) == pytest.approx(NEUTRAL)

    def test_it_never_drops_below_neutral(self):
        """가산 전용이라 어떤 구성도 감점이 되지 않는다."""
        구성 = ([500_000, 20_000], [100_000], [100_000] * 4, [12_000, 11_000])
        for points in 구성:
            for games in (0, 10, POOL_SEASON_GAMES, 200):
                assert pool(points, games) >= NEUTRAL

class TestSeasonConfidence:
    wide = [100_000] * POOL_FULL
    narrow = [500_000, 20_000]

    def test_a_full_season_uses_the_raw_pool(self):
        assert pool(self.wide, POOL_SEASON_GAMES) == 100.0
        assert pool(self.wide, POOL_SEASON_GAMES * 3) == 100.0

    def test_a_thin_season_scores_lower_than_a_verified_pool(self):
        """솔랭을 거의 안 한 사람의 넓은 숙련도는 검증된 폭만큼 쳐주지 않는다."""
        verified = pool(self.wide, POOL_SEASON_GAMES)
        unverified = pool(self.wide, 0)
        assert unverified < verified
        assert unverified == pytest.approx(75.0)  # 50 + 50 * 0.5

    def test_it_ramps_up_with_games_played(self):
        scores = [pool(self.wide, games) for games in (0, 10, 20, 30, 40)]
        assert scores == sorted(scores)
        assert scores[0] < scores[-1] == 100.0

    def test_no_cliff_at_the_threshold(self):
        just_under = pool(self.wide, POOL_SEASON_GAMES - 1)
        assert abs(just_under - 100.0) < 1.0

    def test_a_narrow_pool_is_neutral_regardless_of_games(self):
        """깎을 것이 없으므로 솔랭 판수와 무관하게 중립이다."""
        assert pool(self.narrow, 0) == pytest.approx(NEUTRAL)
        assert pool(self.narrow, POOL_SEASON_GAMES) == pytest.approx(NEUTRAL)

    def test_a_thin_season_halves_the_bonus(self):
        thin = pool(self.wide, 0) - NEUTRAL
        full = pool(self.wide, POOL_SEASON_GAMES) - NEUTRAL
        assert thin == pytest.approx(full / 2)

class TestMasteryScore:
    def test_no_data_at_all(self):
        assert mastery_score(None, None, 0, 0) is None

    def test_it_averages_the_two_sources(self):
        blended = mastery_score(100.0, 1.0, TRAIT_MIN_VOTES, 0)
        # 계정 숙련도 100 과 동료평가 기본값 1점(=50) 의 평균
        assert blended == pytest.approx(75.0)

    def test_one_source_alone_is_used_as_is(self):
        only_pool = mastery_score(80.0, None, 0, 0)
        only_votes = mastery_score(None, 10.0, TRAIT_MIN_VOTES, 0)
        assert only_pool == pytest.approx(80.0)
        assert only_votes == pytest.approx(trait_value(10.0, TRAIT_MIN_VOTES))

    def test_a_missing_source_is_not_filled_with_neutral(self):
        """없는 쪽을 중립으로 메우면 값이 실제보다 평평해진다."""
        assert mastery_score(100.0, None, 0, 0) == pytest.approx(100.0)
        assert mastery_score(100.0, 1.0, TRAIT_MIN_VOTES, 0) == pytest.approx(75.0)

    def test_votes_below_the_threshold_leave_only_the_account(self):
        assert mastery_score(80.0, 10.0, TRAIT_MIN_VOTES - 1, 0) == pytest.approx(80.0)

    def test_it_fades_as_custom_games_pile_up(self):
        full = mastery_score(100.0, None, 0, 0)
        half = mastery_score(100.0, None, 0, TRAIT_FADE_GAMES // 2)

        assert half == pytest.approx(NEUTRAL + (full - NEUTRAL) / 2)
        assert mastery_score(100.0, None, 0, TRAIT_FADE_GAMES) is None

class TestMainCallSplit:
    def players(self, main_calls, follows=None):
        follows = follows or {}
        return [
            profile(
                i, tier=50.0, main=None,
                main_call=main_calls.get(i), follow=follows.get(i),
            )
            for i in range(LOBBY_SIZE)
        ]

    def test_top_two_are_picked(self):
        players = self.players({0: 90.0, 1: 30.0, 2: 80.0, 3: 70.0})
        assert top_callers(players) == (0, 2)

    def test_one_rating_is_not_enough_to_constrain(self):
        assert top_callers(self.players({4: 90.0})) == ()

    def test_the_two_leaders_land_on_different_teams(self):
        players = self.players({0: 95.0, 7: 90.0})
        for seed in range(10):
            result = find_best_teams(players, rng=random.Random(seed))
            team_a = {member.player_id for member, _ in result.team_a.members}

            assert len({0, 7} & team_a) == 1, f"seed={seed} 에서 메인오더가 같은 팀"
            assert result.leaders_split is True

    def test_no_ratings_means_no_warning(self):
        result = find_best_teams(self.players({}), rng=random.Random(1))
        assert result.leaders_split is True

    def test_follow_does_not_constrain_the_split(self):
        """오더수행은 가산 자원이라 잘하는 사람끼리 갈라 놓을 이유가 없다."""
        assert top_callers(self.players({}, {0: 95.0, 7: 90.0})) == ()

class TestFollowIsAdditive:
    def test_it_raises_the_score(self):
        from app.services.scoring import base_score

        without = base_score(tier=50.0)
        with_follow = base_score(tier=50.0, follow=100.0)
        assert with_follow > without

    # 전투력을 나머지와 같게 맞춘 오더수행 만점자. 이렇게 해야 밸런스 압력이
    # 사라져서 '제약이 있는지'만 남는다. (0.40*43.75 + 0.05*100) / 0.45 = 50
    EQUAL_TIER = 43.75

    def balanced_pair(self, **trait):
        players = [
            profile(i, tier=50.0, main=None) for i in range(LOBBY_SIZE)
        ]
        for i in (0, 1):
            players[i] = profile(i, tier=self.EQUAL_TIER, main=None, **trait)
        return players

    def test_the_setup_really_is_balanced(self):
        """전제 확인: 트레잇 보유자와 나머지의 전투력이 같아야 한다."""
        players = self.balanced_pair(follow=100.0)
        assert power_of(players[0], "MID") == pytest.approx(power_of(players[2], "MID"))

    def test_follow_has_no_hard_constraint(self):
        """전투력이 같으면 오더수행이 좋은 둘도 한 팀이 될 수 있다."""
        together = sum(
            len({0, 1} & {m.player_id for m, _ in
                 find_best_teams(self.balanced_pair(follow=100.0),
                                 rng=random.Random(seed)).team_a.members}) != 1
            for seed in range(20)
        )
        assert together > 0, "오더수행에 분리 제약이 걸려 있다"

    def test_main_call_splits_even_when_balance_does_not_care(self):
        """같은 조건이라도 메인오더는 항상 갈라진다. 이게 둘의 차이다."""
        for seed in range(20):
            result = find_best_teams(
                self.balanced_pair(main_call=100.0), rng=random.Random(seed)
            )
            team_a = {m.player_id for m, _ in result.team_a.members}
            assert len({0, 1} & team_a) == 1, f"seed={seed} 에서 메인오더가 같은 팀"

class TestDisplay:
    def test_summary_shows_how_many_more_votes_are_needed(self):
        line = summary({MAIN_CALL: (7.5, TRAIT_MIN_VOTES), CHAMPS: (4.0, 0)})

        assert f"메인오더 **7.5** ({TRAIT_MIN_VOTES}명)" in line
        assert f"오더수행 **1.0** (0/{TRAIT_MIN_VOTES}명)" in line
        assert f"챔피언폭 **4.0** (0/{TRAIT_MIN_VOTES}명)" in line

    def test_unrated_players_show_the_middle_value(self):
        assert "메인오더 **1.0** (0/" in summary({})

    def test_trait_field_counts_down_the_remaining_games(self):
        from types import SimpleNamespace

        rows = [SimpleNamespace(games=4)]
        assert f"{TRAIT_FADE_GAMES - 4}판 더" in trait_field(rows, {})
        assert "실제 기록만" in trait_field([SimpleNamespace(games=TRAIT_FADE_GAMES)], {})


class TestStatusEmbed:
    def player(self, n):
        from types import SimpleNamespace

        return SimpleNamespace(id=n, discord_id=1000 + n, riot_game_name=f"이름{n}")

    def test_it_lists_everyone_with_their_scores(self):
        embed = status_embed(
            [self.player(0), self.player(1)],
            {1: {MAIN_CALL: (8.0, 2), CHAMPS: (6.0, 2)}},
        )
        lines = embed.description.split("\n")

        assert embed.title == "능력평가 현황 2명"
        assert lines[0].startswith("1. <@1000> —")
        assert "메인오더 **8.0** (2명)" in lines[1]

    def test_unrated_players_come_first(self):
        embed = status_embed(
            [self.player(0), self.player(1)],
            {0: {MAIN_CALL: (8.0, 3)}},
        )
        lines = embed.description.split("\n")

        assert lines[0].startswith("1. <@1001>")
        assert "메인오더 **1.0** (0/" in lines[0]

    def test_long_list_is_truncated(self):
        embed = status_embed([self.player(i) for i in range(LIST_LIMIT + 2)], {})
        lines = embed.description.split("\n")

        assert len(lines) == LIST_LIMIT + 1
        assert lines[-1] == "-# 외 2명"

    def test_nobody_registered(self):
        assert status_embed([], {}).description == "아직 등록한 사람이 없습니다."
