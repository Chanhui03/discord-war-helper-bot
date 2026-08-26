from types import SimpleNamespace

from app.bot.commands.customs import SUMS, stats_embed, width

PLAYER = SimpleNamespace(riot_game_name="겨 울", riot_tagline="chani")

def row(role, games, **overrides):
    """30분 경기 기준의 라인별 합계."""
    base = dict(
        games=games,
        wins=games // 2,
        kills=4 * games,
        deaths=2 * games,
        assists=5 * games,
        first_blood=0,
        first_tower=0,
        damage=600 * 30 * games,
        damage_taken=500 * 30 * games,
        gold=400 * 30 * games,
        cs=9 * 30 * games,
        wards=10 * games,
        seconds=1800 * games,
    )
    base.update(overrides)
    return SimpleNamespace(role=role, **base)

def blocks(embed):
    """코드블록 두 개를 각각 줄 목록으로 돌려준다."""
    return [
        field.value.strip("`").strip("\n").split("\n") for field in embed.fields
    ]

def test_header_comes_first_then_the_total_then_each_line():
    embed = stats_embed(PLAYER, [row("MID", 6), row("TOP", 2)])
    basic, detail = blocks(embed)

    assert basic[0].split() == ["라인", "경기", "승", "패", "승률", "KDA", "킬", "데스", "어시"]
    assert [line.split()[0] for line in basic] == ["라인", "전체", "미드", "탑"]
    assert detail[0].split() == ["라인", "DPM", "DTPM", "GPM", "CSPM", "DPGR", "첫킬", "첫포탑", "와드"]
    assert [line.split()[0] for line in detail] == ["라인", "전체", "미드", "탑"]

def test_total_row_sums_every_line():
    embed = stats_embed(PLAYER, [row("MID", 6), row("TOP", 2)])
    basic, _ = blocks(embed)
    total = basic[1].split()

    assert total[1:5] == ["8", "4", "4", "50.0%"]

def test_columns_line_up_in_the_monospace_block():
    embed = stats_embed(PLAYER, [row("MID", 6), row("SUPPORT", 2)])
    for block in blocks(embed):
        assert len({width(line) for line in block}) == 1

def test_numbers_match_the_opgg_style_row():
    """op.gg 선수 기록 한 줄과 같은 값이 나오는지 본다."""
    sample = row(
        "MID",
        44,
        wins=16,
        kills=188,
        deaths=107,
        assists=218,
        first_blood=6,
        first_tower=9,
        damage=934_956,
        damage_taken=795_168,
        gold=560_604,
        cs=12_118,
        wards=563,
        seconds=1800 * 44,
    )
    basic, detail = blocks(stats_embed(PLAYER, [sample]))

    assert basic[2].split() == ["미드", "44", "16", "28", "36.4%", "3.79", "4.3", "2.4", "5.0"]
    # DPGR 은 DPM / GPM (골드 대비 딜 가성비).
    assert detail[2].split() == ["미드", "708.3", "602.4", "424.7", "9.18", "1.67", "13.6%", "20.5%", "12.8"]

def test_every_summed_column_is_used():
    assert set(SUMS) == {
        "games", "wins", "kills", "deaths", "assists", "first_blood", "first_tower",
        "damage", "damage_taken", "gold", "cs", "wards", "seconds",
    }
