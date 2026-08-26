import random
from types import SimpleNamespace

from app.bot.views.teams import TeamEditView, teams_embed
from app.roles import ROLE_LABELS, ROLES
from app.services.matchmaking import (
    LOBBY_SIZE,
    TEAM_SIZE,
    find_best_teams,
    score_assignment,
)
from tests.test_matchmaking import profile

def _rendered(players, seed=3, match_id=42):
    """팀을 배정해 임베드까지 만든다. (embed, result) 를 돌려준다."""
    result = find_best_teams(players, rng=random.Random(seed))
    match = SimpleNamespace(
        id=match_id,
        participants=[
            SimpleNamespace(player_id=i, player=SimpleNamespace(discord_id=900 + i))
            for i in range(LOBBY_SIZE)
        ],
        spectators=[],
    )
    return teams_embed(match, result), result

def test_teams_embed_lists_both_teams_in_role_order():
    players = [
        profile(i, tier=40.0 + i * 4, main=ROLES[i % 5]) for i in range(LOBBY_SIZE)
    ]
    embed, _ = _rendered(players)

    assert embed.title == "내전 #42 팀 구성"
    assert "126개 분할" in embed.description
    assert len(embed.fields) == 2
    for field in embed.fields:
        lines = field.value.split("\n")
        assert len(lines) == TEAM_SIZE
        labels = [line.split("`")[1].strip() for line in lines]
        assert labels == [ROLE_LABELS[r] for r in ROLES]

def test_no_warning_when_bans_are_honoured():
    embed, result = _rendered([profile(i, main=ROLES[i % 5]) for i in range(LOBBY_SIZE)])
    assert result.bans_honoured
    assert all("기피 라인 금지" not in field.name for field in embed.fields)

def test_warning_shown_when_bans_cannot_be_honoured():
    players = [
        profile(i, main="MID", avoid="JUNGLE", must_avoid=i < 9)
        for i in range(LOBBY_SIZE)
    ]
    embed, result = _rendered(players, seed=1)
    assert result.bans_honoured is False
    assert any("기피 라인 금지" in field.name for field in embed.fields)

def staged_match(players, result, match_id=42):
    """팀 배정이 반영된 가짜 내전."""
    assignment = {
        member.player_id: (side, role)
        for side, team in (("A", result.team_a), ("B", result.team_b))
        for member, role in team.members
    }
    return SimpleNamespace(
        id=match_id,
        participants=[
            SimpleNamespace(
                player_id=player.player_id,
                team=assignment[player.player_id][0],
                role=assignment[player.player_id][1],
                player=SimpleNamespace(
                    discord_id=900 + player.player_id,
                    riot_game_name=f"플레이어{player.player_id}",
                    riot_tagline="KR1",
                ),
            )
            for player in players
        ],
        spectators=[],
    )

def staged(seed=3):
    players = [profile(i, tier=40.0 + i * 4, main=ROLES[i % 5]) for i in range(LOBBY_SIZE)]
    result = find_best_teams(players, rng=random.Random(seed))
    return players, result, staged_match(players, result)

def test_swap_menu_lists_every_participant_with_their_slot():
    players, result, match = staged()
    [select] = TeamEditView(match).children

    assert (select.min_values, select.max_values) == (2, 2)
    assert len(select.options) == LOBBY_SIZE
    assert select.custom_id == "teams:swap:42"

    first = match.participants[0]
    option = next(o for o in select.options if o.value == str(first.player_id))
    assert option.label == "플레이어0#KR1"
    assert option.description == f"{first.team}팀 · {ROLE_LABELS[first.role]}"

def test_edited_teams_embed_says_it_was_changed_by_hand():
    players, result, match = staged()
    assignment = {
        entry.player_id: (entry.team, entry.role) for entry in match.participants
    }
    embed = teams_embed(match, score_assignment(players, assignment))

    assert "직접 바꾼 구성" in embed.description
    assert "배정 평가" not in embed.description
    assert len(embed.fields) == 2
