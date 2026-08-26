from types import SimpleNamespace

from app.bot.views.lobby import LobbyView, lobby_embed
from app.services.matchmaking import LOBBY_SIZE, TEAM_SIZE

def participant(n):
    return SimpleNamespace(
        player=SimpleNamespace(
            discord_id=1000 + n, riot_game_name=f"플레이어{n}", riot_tagline="KR1"
        )
    )

def fake_match(count, match_id=7, watching=0):
    return SimpleNamespace(
        id=match_id,
        participants=[participant(i) for i in range(count)],
        spectators=[SimpleNamespace(discord_id=2000 + i) for i in range(watching)],
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

def test_generate_button_starts_disabled():
    view = LobbyView(1)
    labels = {b.label: b for b in view.children}
    assert set(labels) == {"참가", "취소", "관전", "관전 취소", "팀 생성", "삭제"}
    assert labels["팀 생성"].disabled is True
    assert labels["참가"].disabled is False

def test_delete_button_sits_on_its_own_row():
    """실수로 누르지 않도록 다른 버튼과 같은 줄에 두지 않는다."""
    rows = LobbyView(1).to_components()
    assert [item["label"] for item in rows[-1]["components"]] == ["삭제"]

def test_lobby_hides_the_spectator_field_when_empty():
    embed = lobby_embed(fake_match(3))
    assert [field.name for field in embed.fields] == ["참가자"]

def test_lobby_lists_spectators():
    embed = lobby_embed(fake_match(3, watching=2))
    field = embed.fields[1]
    assert field.name == "관전 2명"
    assert field.value == "<@2000> <@2001>"

def test_spectators_do_not_count_toward_the_lobby():
    """관전자가 있어도 10명이 차야 모집이 끝난다."""
    embed = lobby_embed(fake_match(3, watching=5))
    assert f"3 / {LOBBY_SIZE}" in embed.description
    assert embed.footer.text is None
