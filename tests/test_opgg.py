"""op.gg 최고 티어 파싱.

네트워크를 타지 않는다. 실제 응답에서 시즌 조각만 잘라 둔 픽스처를 읽는다.
남의 사이트라 모양이 바뀌면 여기가 먼저 깨져야 봇보다 먼저 알 수 있다.
"""

from pathlib import Path

from app.services.opgg import parse_peak, unescape

SAMPLE = (Path(__file__).parent / "data" / "opgg_seasons.html").read_text(
    encoding="utf-8"
)

def test_it_reads_the_highest_season_from_a_real_response():
    assert parse_peak(SAMPLE) == ("CHALLENGER", "I", 1255)

def entry(key, value, division, lp):
    """실제 응답과 같은 모양의 시즌 조각 하나."""
    return (
        f'\\"{key}\\":{{\\"tier\\":\\"이름은 못 믿는다\\",'
        f'\\"value\\":\\"{value}\\",\\"division\\":{division},\\"lp\\":{lp}}}'
    )

def test_it_picks_the_best_season_not_the_latest():
    """시즌이 여러 개면 가장 높은 것을 고른다. 목록 순서에 기대지 않는다."""
    payload = (
        entry("high_rank_info", "GOLD", 2, '\\"30\\"')
        + entry("high_rank_info", "DIAMOND", 1, '\\"80\\"')
        + entry("high_rank_info", "SILVER", 4, '\\"0\\"')
    )
    assert parse_peak(payload) == ("DIAMOND", "I", 80)

def test_it_falls_back_to_the_season_end_tier():
    """최고 티어가 비어 있고 최종 티어에만 값이 있는 시즌이 실제로 있다."""
    payload = (
        entry("high_rank_info", "Unranked", '\\"$undefined\\"', "null")
        + entry("rank_info", "EMERALD", 4, '\\"1\\"')
    )
    assert parse_peak(payload) == ("EMERALD", "IV", 1)

def test_unplayed_seasons_are_skipped():
    payload = entry("high_rank_info", "Unranked", '\\"$undefined\\"', "null")
    assert parse_peak(payload) is None

def test_apex_tiers_have_no_division():
    """마스터 이상은 division 이 $undefined 로 온다."""
    payload = entry("high_rank_info", "MASTER", '\\"$undefined\\"', '\\"1,255\\"')
    assert parse_peak(payload) == ("MASTER", None, 1255)

def test_nothing_found_is_not_an_error():
    """페이지 모양이 바뀌면 None 이다. 최고 티어는 없어도 되는 보조 지표다."""
    assert parse_peak("<html>바뀐 페이지</html>") is None
    assert parse_peak("") is None

def test_unknown_tier_names_are_ignored():
    assert parse_peak(entry("high_rank_info", "WOOD", 1, '\\"0\\"')) is None

def test_unescape_unwraps_one_layer():
    assert unescape('\\"tier\\":\\"GOLD\\"') == '"tier":"GOLD"'
