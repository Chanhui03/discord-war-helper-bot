from types import SimpleNamespace

import pytest

from app.services.scoring import NEUTRAL, TRAIT_FADE_GAMES, TRAIT_MIN_VOTES, call_score
from app.services.transcript import (
    MIN_CONFIDENCE,
    CallReport,
    PlayerCall,
    build_prompt,
    parse,
    ranked,
    usable,
)

SAMPLE = """[00:12:03] S1: 드래곤 버리고 탑 밀자
쓰레기 줄 - 형식에 안 맞음
[00:12:05] S3: ㅇㅇ
[01:02:07] S2: 나 정글인데 궁 없어
"""

def entry(player_id, name, role, win=True, **stats):
    """전적이 채워진 참가자. 기록이 없는 판은 stats 를 비워 둔다."""
    blank = dict(
        kills=None, deaths=None, assists=None, cs=None, damage=None,
        damage_taken=None, gold=None, wards=None, first_blood=None, first_tower=None,
    )
    return SimpleNamespace(
        player_id=player_id,
        role=role,
        team="A" if win else "B",
        win=win,
        player=SimpleNamespace(
            riot_game_name=name, riot_tagline="KR1", discord_id=player_id
        ),
        **{**blank, **stats},
    )

class TestParse:
    def test_it_reads_timestamps_and_speakers(self):
        lines = parse(SAMPLE)
        assert [u.speaker for u in lines] == ["S1", "S3", "S2"]
        assert lines[0].at == 12 * 60 + 3
        assert lines[0].text == "드래곤 버리고 탑 밀자"

    def test_it_skips_malformed_lines(self):
        assert len(parse(SAMPLE)) == 3

    def test_hours_roll_into_seconds(self):
        assert parse(SAMPLE)[2].at == 3600 + 2 * 60 + 7

    def test_empty_input(self):
        assert parse("") == []

class TestPrompt:
    def test_roster_carries_the_binding_clues(self):
        """배정 라인이 있어야 '나 정글인데' 같은 대사로 사람을 묶을 수 있다."""
        prompt = build_prompt(
            [entry(1, "권찬희", "JUNGLE")],
            [entry(2, "아무개", "MID", win=False)],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "player_id=1" in prompt
        assert "권찬희" in prompt
        assert "정글" in prompt
        assert "드래곤 버리고 탑 밀자" in prompt

    def test_the_scoreboard_is_included(self):
        """숫자와 말을 함께 봐야 나오는 판단이 목적이다."""
        prompt = build_prompt(
            [entry(1, "권찬희", "MID", kills=2, deaths=7, assists=14, cs=180,
                   damage=18000, damage_taken=24000, gold=11000, wards=22)],
            [entry(2, "아무개", "TOP", win=False)],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "2/7/14" in prompt
        assert "와드 22" in prompt

    def test_a_match_without_a_replay_file_says_so(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP", win=False)],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "개인 기록 없음" in prompt

    def test_which_team_won_is_marked(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP", win=False)],
            {"A팀": "", "B팀": ""},
        )
        assert "A팀 (승)" in prompt
        assert "B팀 (패)" in prompt

    def test_spectators_are_marked_as_context_only(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP", win=False)],
            {"A팀": SAMPLE, "B팀": ""}, spectators=SAMPLE,
        )
        assert "순위 대상 아님" in prompt

    def test_it_tells_the_model_not_to_guess(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP", win=False)],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "identified=false" in prompt

    def test_it_asks_for_ranks_not_absolute_scores(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP", win=False)],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "순위" in prompt
        assert "판마다 기준이 흔들린다" in prompt

class TestUsable:
    def call(self, player_id, **kwargs):
        base = dict(
            identified=True, confidence=0.9, rank=1, main_call=7, evidence="근거"
        )
        return PlayerCall(player_id=player_id, **{**base, **kwargs})

    def test_it_keeps_confident_identifications(self):
        report = CallReport(players=[self.call(1), self.call(2, rank=2)])
        assert [c.player_id for c in usable(report, [1, 2])] == [1, 2]

    def test_unidentified_speakers_are_dropped(self):
        """화자를 잘못 붙이면 남의 콜이 내 점수가 되어 없느니만 못하다."""
        report = CallReport(
            players=[
                self.call(1, identified=False, rank=None, main_call=None),
                self.call(2, rank=2),
            ]
        )
        assert [c.player_id for c in usable(report, [1, 2])] == [2]

    def test_low_confidence_is_dropped(self):
        report = CallReport(players=[self.call(1, confidence=MIN_CONFIDENCE - 0.01)])
        assert usable(report, [1]) == []

    def test_players_outside_the_roster_are_dropped(self):
        """모델이 지어낸 player_id 를 저장하면 안 된다."""
        report = CallReport(players=[self.call(1), self.call(999, rank=2)])
        assert [c.player_id for c in usable(report, [1, 2])] == [1]

    def test_a_score_is_required(self):
        assert usable(CallReport(players=[self.call(1, main_call=None)]), [1]) == []

    def test_a_rank_is_required(self):
        assert usable(CallReport(players=[self.call(1, rank=None)]), [1]) == []

class TestRanked:
    def call(self, player_id, rank):
        return PlayerCall(
            player_id=player_id, identified=True, confidence=0.9,
            rank=rank, main_call=7, evidence="근거",
        )

    def test_a_clean_ranking_is_kept(self):
        calls = [self.call(1, 1), self.call(2, 2), self.call(3, 3)]
        assert len(ranked(calls, [1, 2, 3])) == 3

    def test_duplicate_ranks_void_the_whole_team(self):
        """2등이 둘이면 나머지 등수의 의미도 무너진다."""
        calls = [self.call(1, 2), self.call(2, 2), self.call(3, 3)]
        assert ranked(calls, [1, 2, 3]) == []

    def test_a_missing_player_is_fine(self):
        """식별 실패로 한 명이 빠지는 건 괜찮다. 겹치는 것만 안 된다."""
        calls = [self.call(1, 1), self.call(2, 3)]
        assert len(ranked(calls, [1, 2, 3])) == 2

    def test_teams_are_judged_separately(self):
        calls = [self.call(1, 1), self.call(2, 1)]
        assert len(ranked(calls, [1])) == 1
        assert len(ranked(calls, [2])) == 1

class TestSchema:
    def test_scores_outside_one_to_ten_are_rejected(self):
        with pytest.raises(Exception):
            PlayerCall(
                player_id=1, identified=True, confidence=0.9, rank=1,
                main_call=11, evidence="",
            )

    def test_ranks_outside_the_team_size_are_rejected(self):
        with pytest.raises(Exception):
            PlayerCall(
                player_id=1, identified=True, confidence=0.9, rank=6,
                main_call=5, evidence="",
            )

    def test_confidence_must_be_a_probability(self):
        with pytest.raises(Exception):
            PlayerCall(
                player_id=1, identified=True, confidence=1.5, rank=1,
                main_call=5, evidence="",
            )

class TestCallScore:
    def test_transcript_alone(self):
        assert call_score(8.0, None, 0, 0) == pytest.approx(88.9, abs=0.1)

    def test_peers_alone(self):
        assert call_score(None, 8.0, TRAIT_MIN_VOTES, 0) == pytest.approx(88.9, abs=0.1)

    def test_the_two_sources_carry_equal_weight(self):
        """대본은 콜의 좋고 나쁨을 못 봐서 사람 평가를 대체하지 않는다."""
        high = call_score(10.0, 1.0, TRAIT_MIN_VOTES, 0)
        assert high == pytest.approx((100.0 + NEUTRAL) / 2)

    def test_the_baseline_rating_does_not_drag_anyone_down(self):
        """1 점은 기본값이라 감점이 아니다."""
        assert call_score(None, 1.0, TRAIT_MIN_VOTES, 0) == pytest.approx(NEUTRAL)

    def test_nothing_at_all(self):
        assert call_score(None, None, 0, 0) is None

    def test_it_fades_with_custom_games(self):
        assert call_score(10.0, None, 0, TRAIT_FADE_GAMES) is None
