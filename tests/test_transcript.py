from types import SimpleNamespace

import pytest

from app.services.scoring import NEUTRAL, TRAIT_FADE_GAMES, TRAIT_MIN_VOTES, call_score
from app.services.transcript import (
    MIN_CONFIDENCE,
    CallReport,
    PlayerCall,
    build_prompt,
    parse,
    usable,
)

SAMPLE = """[00:12:03] S1: 드래곤 버리고 탑 밀자
쓰레기 줄 - 형식에 안 맞음
[00:12:05] S3: ㅇㅇ
[01:02:07] S2: 나 정글인데 궁 없어
"""

def entry(player_id, name, role, discord_id=None):
    return SimpleNamespace(
        player_id=player_id,
        role=role,
        team="A",
        player=SimpleNamespace(
            riot_game_name=name, riot_tagline="KR1", discord_id=discord_id or player_id
        ),
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
            [entry(2, "아무개", "MID")],
            {"A팀": SAMPLE, "B팀": ""},
        )
        assert "player_id=1" in prompt
        assert "권찬희#KR1" in prompt
        assert "정글" in prompt
        assert "드래곤 버리고 탑 밀자" in prompt

    def test_spectators_are_marked_as_context_only(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP")],
            {"A팀": SAMPLE, "B팀": ""}, spectators=SAMPLE,
        )
        assert "점수 대상 아님" in prompt

    def test_it_tells_the_model_not_to_guess(self):
        prompt = build_prompt(
            [entry(1, "가", "MID")], [entry(2, "나", "TOP")], {"A팀": SAMPLE, "B팀": ""}
        )
        assert "identified=false" in prompt

class TestUsable:
    def call(self, player_id, **kwargs):
        base = dict(identified=True, confidence=0.9, main_call=7, evidence="근거")
        return PlayerCall(player_id=player_id, **{**base, **kwargs})

    def test_it_keeps_confident_identifications(self):
        report = CallReport(players=[self.call(1), self.call(2)])
        assert [c.player_id for c in usable(report, [1, 2])] == [1, 2]

    def test_unidentified_speakers_are_dropped(self):
        """화자를 잘못 붙이면 남의 콜이 내 점수가 되어 없느니만 못하다."""
        report = CallReport(
            players=[self.call(1, identified=False, main_call=None), self.call(2)]
        )
        assert [c.player_id for c in usable(report, [1, 2])] == [2]

    def test_low_confidence_is_dropped(self):
        report = CallReport(players=[self.call(1, confidence=MIN_CONFIDENCE - 0.01)])
        assert usable(report, [1]) == []

    def test_players_outside_the_roster_are_dropped(self):
        """모델이 지어낸 player_id 를 저장하면 안 된다."""
        report = CallReport(players=[self.call(1), self.call(999)])
        assert [c.player_id for c in usable(report, [1, 2])] == [1]

    def test_a_score_is_required(self):
        report = CallReport(players=[self.call(1, main_call=None)])
        assert usable(report, [1]) == []

class TestSchema:
    def test_scores_outside_one_to_ten_are_rejected(self):
        with pytest.raises(Exception):
            PlayerCall(
                player_id=1, identified=True, confidence=0.9, main_call=11, evidence=""
            )

    def test_confidence_must_be_a_probability(self):
        with pytest.raises(Exception):
            PlayerCall(
                player_id=1, identified=True, confidence=1.5, main_call=5, evidence=""
            )

class TestCallScore:
    def test_transcript_alone(self):
        assert call_score(8.0, None, 0, 0) == pytest.approx(77.8, abs=0.1)

    def test_peers_alone(self):
        assert call_score(None, 8.0, TRAIT_MIN_VOTES, 0) == pytest.approx(77.8, abs=0.1)

    def test_the_two_sources_carry_equal_weight(self):
        """대본은 콜의 좋고 나쁨을 못 봐서 사람 평가를 대체하지 않는다."""
        both = call_score(8.0, 3.0, TRAIT_MIN_VOTES, 0)
        assert both == pytest.approx(NEUTRAL)

    def test_nothing_at_all(self):
        assert call_score(None, None, 0, 0) is None

    def test_it_fades_with_custom_games(self):
        assert call_score(10.0, None, 0, TRAIT_FADE_GAMES) is None
