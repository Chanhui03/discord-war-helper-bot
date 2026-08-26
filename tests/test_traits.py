import random

import pytest

from app.bot.commands.ability import LIST_LIMIT, status_embed
from app.bot.commands.customs import trait_field
from app.services.matchmaking import LOBBY_SIZE, find_best_teams, top_shotcallers
from app.services.scoring import TRAIT_FADE_GAMES, TRAIT_MIN_VOTES, trait_score
from app.traits import CHAMPS, SHOTCALL, summary
from tests.test_matchmaking import profile

class TestTraitScore:
    def test_votes_below_the_threshold_are_ignored(self):
        assert trait_score(10.0, TRAIT_MIN_VOTES - 1, 0) is None
        assert trait_score(10.0, TRAIT_MIN_VOTES, 0) is not None

    def test_scale_runs_from_zero_to_a_hundred(self):
        assert trait_score(1.0, 3, 0) == pytest.approx(0.0)
        assert trait_score(5.5, 3, 0) == pytest.approx(50.0)
        assert trait_score(10.0, 3, 0) == pytest.approx(100.0)

    def test_it_fades_as_custom_games_pile_up(self):
        full = trait_score(10.0, 3, 0)
        half = trait_score(10.0, 3, TRAIT_FADE_GAMES // 2)

        assert half == pytest.approx(50.0 + (full - 50.0) / 2)
        assert trait_score(10.0, 3, TRAIT_FADE_GAMES) is None

    def test_no_rating_at_all(self):
        assert trait_score(None, 0, 0) is None

class TestShotcallSplit:
    def players(self, shotcalls):
        return [
            profile(i, tier=50.0, main=None, shotcall=shotcalls.get(i))
            for i in range(LOBBY_SIZE)
        ]

    def test_top_two_are_picked(self):
        players = self.players({0: 90.0, 1: 30.0, 2: 80.0, 3: 70.0})
        assert top_shotcallers(players) == (0, 2)

    def test_one_rating_is_not_enough_to_constrain(self):
        assert top_shotcallers(self.players({4: 90.0})) == ()

    def test_the_two_leaders_land_on_different_teams(self):
        players = self.players({0: 95.0, 7: 90.0})
        for seed in range(10):
            result = find_best_teams(players, rng=random.Random(seed))
            team_a = {member.player_id for member, _ in result.team_a.members}

            assert len({0, 7} & team_a) == 1, f"seed={seed} 에서 오더가 같은 팀"
            assert result.leaders_split is True

    def test_no_ratings_means_no_warning(self):
        result = find_best_teams(self.players({}), rng=random.Random(1))
        assert result.leaders_split is True

class TestDisplay:
    def test_summary_shows_how_many_more_votes_are_needed(self):
        line = summary({SHOTCALL: (7.5, TRAIT_MIN_VOTES), CHAMPS: (4.0, 0)})

        assert f"오더능력 **7.5** ({TRAIT_MIN_VOTES}명)" in line
        assert f"챔피언폭 **4.0** (0/{TRAIT_MIN_VOTES}명)" in line

    def test_unrated_players_show_the_middle_value(self):
        assert "오더능력 **5.5** (0/" in summary({})

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
            {1: {SHOTCALL: (8.0, 2), CHAMPS: (6.0, 2)}},
        )
        lines = embed.description.split("\n")

        assert embed.title == "능력평가 현황 2명"
        assert lines[0].startswith("1. <@1000> —")
        assert "오더능력 **8.0** (2명)" in lines[1]

    def test_unrated_players_come_first(self):
        embed = status_embed(
            [self.player(0), self.player(1)],
            {0: {SHOTCALL: (8.0, 3)}},
        )
        lines = embed.description.split("\n")

        assert lines[0].startswith("1. <@1001>")
        assert "오더능력 **5.5** (0/" in lines[0]

    def test_long_list_is_truncated(self):
        embed = status_embed([self.player(i) for i in range(LIST_LIMIT + 2)], {})
        lines = embed.description.split("\n")

        assert len(lines) == LIST_LIMIT + 1
        assert lines[-1] == "-# 외 2명"

    def test_nobody_registered(self):
        assert status_embed([], {}).description == "아직 등록한 사람이 없습니다."
