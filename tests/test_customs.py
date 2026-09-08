from types import SimpleNamespace

from app.bot.commands.customs import SUMS, stats_embed

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
        vision_score=30 * games,
        wards_killed=6 * games,
        objective_damage=12_000 * games,
        cc_time=25 * games,
        # 우리 팀 킬 합. 내 킬 4 + 어시 5 = 9 이므로 관여율 60% 가 된다.
        team_kills=15 * games,
        seconds=1800 * games,
    )
    base.update(overrides)
    return SimpleNamespace(role=role, **base)

def blocks(embed):
    """코드블록으로 된 칸만 각각 줄 목록으로 돌려준다."""
    return [
        field.value.strip("`").strip("\n").split("\n")
        for field in embed.fields
        if field.value.startswith("```")
    ]

def test_header_comes_first_then_the_total_then_each_line():
    embed = stats_embed(PLAYER, [row("MID", 6), row("TOP", 2)], {})
    basic, detail, support = blocks(embed)

    assert basic[0].split() == [
        "라인", "G", "W", "L", "WR", "KDA", "KP", "K", "D", "A"
    ]
    assert [line.split()[0] for line in basic] == ["라인", "전체", "미드", "탑"]
    assert detail[0].split() == ["라인", "DPM", "DTPM", "GPM", "CSPM", "DPGR", "FB", "FT", "WARD"]
    assert [line.split()[0] for line in detail] == ["라인", "전체", "미드", "탑"]
    assert support[0].split() == ["라인", "VS", "VS/M", "WK", "OBJ", "CC"]
    assert [line.split()[0] for line in support] == ["라인", "전체", "미드", "탑"]

def test_total_row_sums_every_line():
    embed = stats_embed(PLAYER, [row("MID", 6), row("TOP", 2)], {})
    basic = blocks(embed)[0]
    total = basic[1].split()

    assert total[1:5] == ["8", "4", "4", "50.0%"]

def test_kill_participation_uses_team_kills_not_games():
    """(킬+어시) / 우리 팀 총킬. 판수로 나누면 롱겜에서 100% 를 넘는다."""
    embed = stats_embed(PLAYER, [row("MID", 6), row("TOP", 2)], {})
    basic = blocks(embed)[0]
    assert basic[1].split()[6] == "60.0%"

def test_columns_line_up_in_the_monospace_block():
    """라인 칸은 한글 두 글자로 통일되고 나머지는 ASCII 라 글자 수가 곧 폭이다."""
    embed = stats_embed(PLAYER, [row("MID", 6), row("SUPPORT", 2), row("TOP", 2)], {})
    for block in blocks(embed):
        assert len({len(line) for line in block}) == 1
        assert all(not line[:2].isascii() and line[2:].isascii() for line in block)

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
        vision_score=1_320,
        wards_killed=264,
        objective_damage=528_000,
        cc_time=1_100,
        team_kills=580,
        seconds=1800 * 44,
    )
    basic, detail, support = blocks(stats_embed(PLAYER, [sample], {}))

    assert basic[2].split() == [
        "미드", "44", "16", "28", "36.4%", "3.79", "70.0%", "4.3", "2.4", "5.0"
    ]
    # DPGR 은 DPM / GPM (골드 대비 딜 가성비).
    assert detail[2].split() == ["미드", "708.3", "602.4", "424.7", "9.18", "1.67", "13.6%", "20.5%", "12.8"]
    # 시야는 판당, 시야/분은 경기 시간 합으로 나눈다.
    assert support[2].split() == ["미드", "30.0", "1.00", "6.0", "12,000", "25s"]

def test_support_block_reads_a_tank_apart_from_kda():
    """탱커·서폿 기여는 KDA 로 안 잡힌다. 킬은 적은데 시야와 CC 가 높은 경우."""
    tank = row("SUPPORT", 10, kills=5, assists=90, vision_score=800, cc_time=600)
    _, _, support = blocks(stats_embed(PLAYER, [tank], {}))
    assert support[2].split() == ["서폿", "80.0", "2.67", "6.0", "12,000", "60s"]

def test_old_records_without_the_new_columns_do_not_crash():
    """컬럼이 생기기 전 기록은 합이 0 으로 메워져 온다."""
    old = row("MID", 4, vision_score=0, wards_killed=0, objective_damage=0, cc_time=0)
    _, _, support = blocks(stats_embed(PLAYER, [old], {}))
    assert support[2].split() == ["미드", "0.0", "0.00", "0.0", "0", "0s"]

def test_every_summed_column_is_used():
    assert set(SUMS) == {
        "games", "wins", "kills", "deaths", "assists", "first_blood", "first_tower",
        "damage", "damage_taken", "gold", "cs", "wards", "vision_score",
        "wards_killed", "objective_damage", "cc_time", "team_kills", "seconds",
    }
