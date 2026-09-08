"""설계서 6장의 설명 가능한 가중합 점수 모델."""

from typing import Dict, Optional, Sequence, Tuple

# 티어별 누적 LP 환산. IRON~DIAMOND 는 4개 디비전 × 100LP 로 계산한다.
TIER_ORDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND",
]
DIVISION_ORDER = ["IV", "III", "II", "I"]
APEX_TIERS = ["MASTER", "GRANDMASTER", "CHALLENGER"]

APEX_BASE_POINTS = len(TIER_ORDER) * 400  # 2800
# 마스터 이상은 디비전 없이 LP 로만 나뉜다. 한국 서버 챌린저 컷이
# 1000~1500LP 대이므로 그 폭만큼 잡아야 apex 구간이 뭉개지지 않는다.
APEX_LP_RANGE = 1500
MAX_POINTS = APEX_BASE_POINTS + APEX_LP_RANGE

# 설계서 6장 가중치. 여기 있는 넷은 '실력의 절대 수준'을 재는 축이라 가중 평균을
# 낸다. 내전에서 온 지표(MMR·판별 순위·챔피언폭·오더수행)는 중립이 0 인 보정항이라
# 평균에 섞지 않고 결과에 더한다(MMR_ADJUST 주석 참고).
#
# 티어를 크게 잡는 이유: 솔랭 승률과 KDA 는 실력의 절대 수준을 재지 못한다.
# 랭크는 승률이 50% 근처로 수렴하도록 설계돼 있어서, 실버든 마스터든
# recent_form 은 50 근처에 몰린다. role 도 같은 승률·KDA 에서 나온다.
# 이 셋에 예전처럼 45% 를 주면 티어 차이가 묻혀 골드가 플래티넘보다 높게
# 나오는 일이 생긴다. 승률·KDA 는 '자기 티어 안에서의 지금 폼'을 보는
# 보정으로만 쓰고, 실력의 수준 자체는 티어가 말하게 한다.
WEIGHTS = {
    "tier": 0.55,
    "role": 0.10,
    "recent_form": 0.07,
    "performance": 0.03,
}

# 티어를 모를 때(언랭) 쓸 값. 가중치를 재분배해 빼 버리면 남는 요소가
# 승률·KDA·동료평가뿐이라, 랭크를 안 돌린 사람이 KDA 하나로 마스터와 같은
# 점수를 받는다. 모르는 것은 빼는 게 아니라 평균으로 둔다.
UNRANKED_TIER = 50.0

# 설계서 6.1 라인 적합도 감점. 티어 축에서 한 티어가 약 9점이고 종합 점수에는
# 그 절반쯤 반영되므로, off 8점은 '부라인은 대략 한 티어 반 아래로 본다'는 뜻이다.
#
# 배수(×0.70)가 아니라 감점인 이유: 배수는 점수가 높을수록 더 많이 깎는다.
# 마스터가 부라인에 가면 24점, 실버는 13점이 빠져서, 부라인 마스터가 주라인
# 플래티넘보다 낮게 나왔다. 라인이 안 맞아 잃는 것은 실력에 비례하지 않는다.
ROLE_PENALTIES = {
    "main": 0.0,
    "secondary": 3.0,
    "off": 8.0,
    "unknown": 10.0,
    "avoid": 12.0,
}

NEUTRAL = 50.0

# 내전 MMR(설계서 6장 Custom Game Score). Elo 방식이다.
#
# 이 값은 '실력'이 아니라 '모델이 틀린 만큼'을 재는 보정항이다. 밸런서가 추정
# 전투력으로 팀을 맞추므로, 추정이 맞으면 모두 승률 50% 근처에 머물러 MMR 이
# 시작값에서 안 움직인다(= 고칠 게 없다). 반대로 저평가된 사람은 모델이
# '비슷하다'고 본 팀을 실제로는 이겨서 MMR 이 올라간다. 그래서 시작값을 티어에서
# 끌어오지 않고 전원 같은 값에서 출발시킨다. 티어를 섞으면 티어를 두 번 세는 꼴이다.
MMR_START = 1200.0
# 한 판에 팀 평균이 같을 때 ±MMR_K/2 만큼 움직인다.
MMR_K = 32.0
# Elo 에서 400 은 기대 승률 10:1 이 되는 차이다. 그만큼 벌리면 최대로 민다.
MMR_SPAN = 400.0
# MMR 이 종합 점수를 밀 수 있는 최대 폭(점). 티어 축에서 한 티어가 약 9점이니
# 15점이면 '내전에서 증명하면 한 티어 반까지 뒤집을 수 있다'는 뜻이다.
#
# 가중 평균 항이 아니라 더하는 값인 이유: MMR 은 중립이 1200 인 보정항이고
# 티어는 절대 수준이다. 축이 다른 둘을 평균내면 기록과 무관하게 잘하는 사람은
# 50 쪽으로 내려가고 못하는 사람은 올라간다. 실제로 5연승한 마스터의 점수가
# 72.8 에서 70.6 으로 내려갔다.
MMR_ADJUST = 15.0
# 내전 판별 평가 순위의 가산폭. 팀에서 늘 1등이면 +12, 늘 꼴찌면 -12 다.
# 승패보다 한 단계 낮게 잡은 것은 MMR 이 '이겼다'는 사실에서 오는 반면 이쪽은
# AI 판단이기 때문이다. 대신 밸런서가 팀을 잘 맞출수록 사라지는 MMR 과 달리
# 이 신호는 팀이 아무리 균형 잡혀도 사람을 계속 가른다. 둘이 서로를 메운다.
INTERNAL_ADJUST = 12.0
# 챔피언폭과 오더수행의 가산폭. 둘 다 깎이지 않고 위로만 붙는 가산 자원이다.
MASTERY_ADJUST = 5.0
FOLLOW_ADJUST = 5.0

# 주관 지표(오더능력·챔피언폭)를 반영하기 위한 최소 평가 인원. 서로 아는 인원이
# 많지 않아 한 명만 매겨도 초기값으로 쓴다.
TRAIT_MIN_VOTES = 1
# 내전을 이만큼 치르면 주관 지표는 힘을 잃고 실제 기록에 자리를 넘긴다.
TRAIT_FADE_GAMES = 10
# 내전 판수가 쌓이면 솔랭 지표가 물러나야 하지만, 따로 전환 장치를 두지 않는다.
# 가산항이 알아서 그 일을 한다. 판이 쌓일수록 MMR 은 시작값에서 멀어지고 판별
# 평가의 신뢰도가 차올라 보정폭이 커지는 반면, 솔랭 평균은 제자리에 있다.

# 챔피언폭을 셀 때 주력으로 인정할 숙련도 비율. 가장 많이 판 챔피언의 이만큼은
# 되어야 저격밴을 맞았을 때 대신 꺼낼 수 있다고 본다.
POOL_RATIO = 0.5
# 이보다 적게 판 챔피언은 비율이 맞아도 세지 않는다. 갓 만든 계정에서 1200점과
# 700점이 폭 2로 잡히는 것을 막는다.
POOL_MIN_POINTS = 10_000
# 저격밴 2개를 버티려면 3개, 4개면 여유가 있다. 그 위로는 더 세지 않는다.
POOL_FULL = 4
# 챔피언폭을 온전히 인정할 시즌 솔랭 판수. 이보다 적으면 숙련도가 지금 실력을
# 얼마나 반영하는지 확인할 길이 없다.
POOL_SEASON_GAMES = 40
# 표본이 없어도 가산분의 이만큼은 인정한다. 0 으로 두면 솔랭을 안 하는 사람은
# 폭이 아무리 넓어도 한 푼도 못 받는다.
POOL_MIN_CONFIDENCE = 0.5

def tier_score(tier: Optional[str], division: Optional[str], lp: int) -> Optional[float]:
    """티어/디비전/LP 를 0~100 으로 정규화한다. 언랭이면 None."""
    if not tier:
        return None

    tier = tier.upper()
    if tier in APEX_TIERS:
        points = APEX_BASE_POINTS + lp
    elif tier in TIER_ORDER:
        division_index = DIVISION_ORDER.index(division.upper()) if division else 0
        points = TIER_ORDER.index(tier) * 400 + division_index * 100 + lp
    else:
        return None

    return min(points / MAX_POINTS, 1.0) * 100

def role_score(games: int, win_rate: float, avg_kda: float) -> float:
    """라인별 성적을 0~100 으로 환산한다. 표본이 적으면 평균(50)으로 수축시킨다."""
    if games <= 0:
        return NEUTRAL

    raw = 0.6 * (win_rate * 100) + 0.4 * min(avg_kda / 5.0, 1.0) * 100
    confidence = min(games / 10.0, 1.0)
    return NEUTRAL + (raw - NEUTRAL) * confidence

def performance_score(avg_kda: float) -> float:
    """KDA 를 0~100 으로 환산한다. KDA 5 이상을 만점으로 본다."""
    return min(avg_kda / 5.0, 1.0) * 100

def from_ten(average: Optional[float]) -> Optional[float]:
    """1~10 평가를 0~100 으로 편다. 1 이 기본값이고 위로만 올라가는 가산점이다.

    매기는 사람이 '기본 1점, 잘하면 더 준다'로 쓰고 있어 그 뜻에 맞춘다.
    1 을 0 으로 읽으면 기본값을 준 사람이 최하점 처리되어, 평가를 안 받은
    사람보다 크게 불리해진다.
    """
    if average is None:
        return None

    return NEUTRAL + (average - 1.0) / 9.0 * NEUTRAL

def trait_value(average: Optional[float], votes: int) -> Optional[float]:
    """동료평가 1~10 평균을 0~100 으로. 표가 모자라면 None."""
    if votes < TRAIT_MIN_VOTES:
        return None

    return from_ten(average)

def faded(value: float, custom_games: int) -> Optional[float]:
    """내전 기록이 쌓일수록 중립(50)으로 끌어당긴다. 다 빠지면 None."""
    weight = 1.0 - min(custom_games / TRAIT_FADE_GAMES, 1.0)
    if weight <= 0:
        return None

    return NEUTRAL + (value - NEUTRAL) * weight

def trait_score(
    average: Optional[float], votes: int, custom_games: int
) -> Optional[float]:
    """주관 지표 한 가지를 반영할 값으로 바꾼다. 못 쓰면 None(가중치 재분배).

    표가 적으면 아예 쓰지 않고, 내전 기록이 쌓일수록 힘을 잃어
    TRAIT_FADE_GAMES 판에서 완전히 사라진다.
    """
    value = trait_value(average, votes)
    return None if value is None else faded(value, custom_games)

def season_confidence(season_games: int) -> float:
    """시즌 솔랭 판수로 본 숙련도의 신뢰도. 판수가 없어도 절반은 남는다."""
    return POOL_MIN_CONFIDENCE + (1.0 - POOL_MIN_CONFIDENCE) * min(
        season_games / POOL_SEASON_GAMES, 1.0
    )

def champion_pool_score(
    points: Sequence[int], season_games: int = 0
) -> Optional[float]:
    """숙련도 포인트 목록을 0~100 의 챔피언폭으로 바꾼다. 없으면 None.

    절대량이 아니라 '가장 많이 판 챔피언 대비 비율'로 센다. 내전에서는 한 사람에게
    1~2챔프를 저격밴하므로, 폭의 실질적인 의미는 주력이 잘렸을 때 대신 꺼낼 카드가
    몇 장 있느냐다. 비율로 보면 총 플레이량이 적은 사람도 불리해지지 않는다.

    동료평가와 마찬가지로 가산 전용이다. 폭이 좁다고 깎지 않고, 넓으면 더 준다.
    원트릭은 중립(50)이고 4챔프 이상이 만점이다.

    숙련도는 커리어 누적이라 지금도 그 폭이 유효한지는 알 수 없다. 그래서 시즌
    솔랭 판수가 POOL_SEASON_GAMES 에 못 미치면 가산분을 깎아, 솔랭으로 확인된
    폭보다 적게 준다.
    """
    played = [value for value in points if value >= POOL_MIN_POINTS]
    if not played:
        return None

    best = max(played)
    pool = sum(1 for value in played if value >= best * POOL_RATIO)
    bonus = min((pool - 1) / (POOL_FULL - 1), 1.0) * NEUTRAL

    return NEUTRAL + bonus * season_confidence(season_games)

def blend(values: Sequence[Optional[float]], custom_games: int) -> Optional[float]:
    """서로 다른 출처의 0~100 값을 평균내고 판수만큼 힘을 줄인다.

    한쪽만 있으면 그 값을 그대로 쓴다. 없는 쪽을 중립으로 메우면 값이 실제보다
    평평해져, 잘하는 사람과 못하는 사람이 같아 보인다.
    """
    parts = [value for value in values if value is not None]
    if not parts:
        return None

    return faded(sum(parts) / len(parts), custom_games)

def mastery_score(
    pool: Optional[float],
    average: Optional[float],
    votes: int,
    custom_games: int,
) -> Optional[float]:
    """챔피언폭. 계정 숙련도와 동료평가를 평균낸다."""
    return blend((pool, trait_value(average, votes)), custom_games)

def call_score(
    recorded: Optional[float],
    average: Optional[float],
    votes: int,
    custom_games: int,
) -> Optional[float]:
    """메인오더. 음성 대본 채점과 동료평가를 평균낸다.

    대본은 '누가 지시를 내렸나'는 잘 보지만 '그 콜이 좋았나'는 못 본다. 게임
    상황을 볼 수 없어서다. 그래서 사람 평가를 대체하지 않고 같은 무게로 섞는다.
    """
    return blend((from_ten(recorded), trait_value(average, votes)), custom_games)

def base_score(
    tier: Optional[float] = None,
    role: Optional[float] = None,
    recent_form: Optional[float] = None,
    performance: Optional[float] = None,
    internal: Optional[float] = None,
    mastery: Optional[float] = None,
    follow: Optional[float] = None,
    mmr: Optional[float] = None,
) -> float:
    """솔랭 지표로 가중 평균을 내고, 내전에서 온 보정을 더한다.

    앞의 넷(티어·라인·최근폼·KDA)만 평균에 들어간다. 없는 요소의 가중치는
    나머지에 재분배되며, 가중치는 합이 1 일 필요 없이 상대 비율만 의미가 있다.

    뒤의 넷(판별 순위·챔피언폭·오더수행·MMR)은 중립이 0 인 보정항이라 더한다.
    이것들은 '실력의 절대 수준'이 아니라 '솔랭 지표가 틀린 만큼'을 재기 때문에,
    평균에 섞으면 기록과 무관하게 잘하는 사람을 끌어내리고 못하는 사람을 올린다.
    """
    components = {
        # 언랭이어도 가중치를 재분배하지 않는다(UNRANKED_TIER 주석 참고).
        "tier": UNRANKED_TIER if tier is None else tier,
        "role": role,
        "recent_form": recent_form,
        "performance": performance,
    }
    # 티어는 언랭이어도 값이 있으므로 available 이 비는 일은 없다.
    available = {k: v for k, v in components.items() if v is not None}
    average = sum(WEIGHTS[k] * v for k, v in available.items()) / sum(
        WEIGHTS[key] for key in available
    )

    return min(
        max(
            average
            + adjustment(internal, INTERNAL_ADJUST)
            + adjustment(mastery, MASTERY_ADJUST)
            + adjustment(follow, FOLLOW_ADJUST)
            + mmr_adjustment(mmr),
            0.0,
        ),
        100.0,
    )

def role_affinity(
    role: str,
    main_role: Optional[str],
    secondary_role: Optional[str],
    avoid_role: Optional[str] = None,
) -> str:
    """해당 라인이 기피/주/부/비선호/미지 중 무엇인지 판정한다."""
    if avoid_role is not None and role == avoid_role:
        return "avoid"
    if main_role is None and secondary_role is None:
        return "unknown"
    if role == main_role:
        return "main"
    if role == secondary_role:
        return "secondary"
    return "off"

def role_power(
    score: float,
    role: str,
    main_role: Optional[str],
    secondary_role: Optional[str],
    avoid_role: Optional[str] = None,
) -> float:
    """기본 점수에서 라인 적합도만큼 깎는다(설계서 6.1)."""
    penalty = ROLE_PENALTIES[
        role_affinity(role, main_role, secondary_role, avoid_role)
    ]
    return max(score - penalty, 0.0)

def adjustment(value: Optional[float], span: float) -> float:
    """0~100 짜리 보정 지표를 중립(50) 기준 ±span 점의 가산분으로 바꾼다.

    쓸 수 없으면(None) 0 이다. 예전에는 가중치를 재분배해 뺐는데, 그러면 값이
    없는 사람과 정확히 중립인 사람이 다르게 취급됐다. 지금은 둘 다 0 이다.
    """
    if value is None:
        return 0.0

    return (value - NEUTRAL) / NEUTRAL * span

def rank_score(average: Optional[float], games: int, team_size: int = 5) -> Optional[float]:
    """내전 판별 평가의 평균 순위를 0~100 으로. 기록이 없으면 None.

    1 등이 100, 꼴찌가 0 이다. 표본이 적으면 중립으로 수축시킨다.
    승률과 달리 밸런서가 팀을 잘 맞출수록 사라지는 신호가 아니라서,
    내전 판수가 쌓인 뒤에도 사람을 계속 가른다.
    """
    if average is None or games <= 0:
        return None

    raw = (team_size - average) / (team_size - 1) * 100
    confidence = min(games / 10.0, 1.0)
    return NEUTRAL + (raw - NEUTRAL) * confidence

def expected_win(team: float, opponent: float) -> float:
    """Elo 기대 승률. 400 차이면 10:1 로 이긴다는 뜻이다."""
    return 1.0 / (1.0 + 10 ** ((opponent - team) / MMR_SPAN))

def rate_matches(
    matches: Sequence[Tuple[Sequence[int], Sequence[int]]]
) -> Dict[int, float]:
    """끝난 내전을 오래된 것부터 훑어 플레이어별 내전 MMR 을 낸다.

    matches 는 (이긴 사람들, 진 사람들) 순서다. 팀 평균끼리 Elo 를 계산해
    이긴 쪽에 더하고 진 쪽에서 같은 값을 뺀다(합이 0).

    단순 승률과 다른 점은 '누구를 상대로' 이겼는지가 들어간다는 것이다.
    강해 보이는 팀을 이기면 많이 오르고, 약한 팀에 지면 많이 떨어진다.
    """
    ratings: Dict[int, float] = {}
    for winners, losers in matches:
        for player_id in (*winners, *losers):
            ratings.setdefault(player_id, MMR_START)
        if not winners or not losers:
            continue

        gain = MMR_K * (
            1.0
            - expected_win(
                sum(ratings[p] for p in winners) / len(winners),
                sum(ratings[p] for p in losers) / len(losers),
            )
        )
        for player_id in winners:
            ratings[player_id] += gain
        for player_id in losers:
            ratings[player_id] -= gain
    return ratings

def mmr_adjustment(mmr: Optional[float]) -> float:
    """내전 MMR 이 종합 점수를 몇 점 밀어 올리는지(설계서 6장 Custom Game Score).

    기록이 없으면 0 이다. 시작값(MMR_START)에서 움직인 만큼만 밀고,
    MMR_SPAN 을 벌리면 ±MMR_ADJUST 로 멈춘다.

    판수가 적다고 따로 수축시키지 않는다. Elo 는 한 판에 최대 MMR_K/2 만
    움직여서 표본이 적으면 알아서 시작값 근처에 머무른다.
    """
    if mmr is None:
        return 0.0

    return max(min((mmr - MMR_START) / MMR_SPAN, 1.0), -1.0) * MMR_ADJUST
