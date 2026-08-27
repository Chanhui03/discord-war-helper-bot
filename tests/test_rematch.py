"""「팀 그대로」가 보여주는 피어리스 목록의 표시 형식."""

from types import SimpleNamespace

from app.bot.views.teams import champion_lines
from app.roles import ROLES


def match_of(players=10):
    return SimpleNamespace(
        participants=[
            SimpleNamespace(
                player_id=i, team="A" if i < 5 else "B", role=ROLES[i % 5]
            )
            for i in range(players)
        ]
    )


def test_each_lane_shows_team_a_then_team_b():
    used = {0: [86, 24], 5: [122], 2: [103]}
    names = {86: "가렌", 24: "잭스", 122: "다리우스", 103: "아리"}

    lines = champion_lines(match_of(), used, names).split("\n")

    assert lines[0] == "`탑 ` 가렌, 잭스 / 다리우스"
    assert lines[2] == "`미드` 아리 / 없음"
    assert lines[4] == "`서폿` 없음 / 없음"


def test_an_unknown_champion_falls_back_to_its_number():
    lines = champion_lines(match_of(), {0: [999]}, {}).split("\n")

    assert lines[0] == "`탑 ` #999 / 없음"
