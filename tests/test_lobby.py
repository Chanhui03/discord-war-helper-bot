from types import SimpleNamespace

from app.bot.views.lobby import lobby_embed
from app.services.matchmaking import LOBBY_SIZE, TEAM_SIZE

def participant(n):
    return SimpleNamespace(
        player=SimpleNamespace(
            discord_id=1000 + n, riot_game_name=f"플레이어{n}", riot_tagline="KR1"
        )
    )

def fake_match(count, match_id=7):
    return SimpleNamespace(
        id=match_id, participants=[participant(i) for i in range(count)]
    )

def test_lobby_size_is_two_teams():
    assert LOBBY_SIZE == TEAM_SIZE * 2 == 10

def test_empty_lobby():
    embed = lobby_embed(fake_match(0))
    assert embed.title == "내전 모집 #7"
    assert f"0 / {LOBBY_SIZE}" in embed.description
    assert embed.fields[0].value == "아직 참가자가 없습니다."
    assert embed.footer.text is None

def test_partial_lobby_lists_everyone_in_order():
    embed = lobby_embed(fake_match(3))
    lines = embed.fields[0].value.split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("1. <@1000>")
    assert lines[2].startswith("3. <@1002>")
    assert "플레이어0#KR1" in lines[0]

def test_full_lobby_is_marked():
    embed = lobby_embed(fake_match(LOBBY_SIZE))
    assert f"{LOBBY_SIZE} / {LOBBY_SIZE}" in embed.description
    assert embed.footer.text == "인원이 모두 찼습니다."
