"""재시작 후 버튼을 되살리는 custom_id 형식을 고정한다.

discord.py 는 custom_id 로 버튼을 다시 찾으므로, 이 문자열이 바뀌면 이미
올라가 있는 메시지의 버튼이 조용히 죽는다.
"""

from app.bot.views.lobby import LobbyView
from app.bot.views.rating import RatingView
from app.bot.views.result import ResultView


def ids(view):
    return [item.custom_id for item in view.children]


def test_lobby_buttons_carry_the_match_number():
    assert ids(LobbyView(42)) == [
        "lobby:join:42",
        "lobby:leave:42",
        "lobby:watch:42",
        "lobby:unwatch:42",
        "lobby:generate:42",
        "lobby:delete:42",
    ]


def test_result_buttons_carry_the_match_number():
    assert ids(ResultView(42)) == ["result:a:42", "result:b:42"]


def test_rating_buttons_carry_the_match_number():
    assert ids(RatingView(42)) == ["rating:rate:42", "rating:again:42", "rating:show:42"]


def test_the_match_number_is_kept_on_the_view():
    assert LobbyView(42).match_id == 42
    assert ResultView(42).match_id == 42
    assert RatingView(42).match_id == 42
