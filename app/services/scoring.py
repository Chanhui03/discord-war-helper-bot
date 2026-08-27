"""설계서 6장의 설명 가능한 가중합 점수 모델."""

from typing import Optional, Sequence

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

# 설계서 6장 가중치.
WEIGHTS = {
    "tier": 0.40,
    "role": 0.20,
    "recent_form": 0.15,
    "performance": 0.10,
    "custom": 0.10,
    "mastery": 0.05,
    # 오더수행. 많을수록 좋은 가산 자원이라 그냥 더한다(메인오더와 반대).
    "follow": 0.05,
}

# 설계서 6.1 라인 적합도 배수. avoid 는 사용자가 명시한 기피 라인으로,
# 비선호(off)보다도 더 불리하게 본다.
ROLE_MULTIPLIERS = {
    "main": 1.00,
    "secondary": 0.85,
    "off": 0.70,
    "unknown": 0.60,
    "avoid": 0.55,
}

NEUTRAL = 50.0

# 주관 지표(오더능력·챔피언폭)를 반영하기 위한 최소 평가 인원. 서로 아는 인원이
# 많지 않아 한 명만 매겨도 초기값으로 쓴다.
TRAIT_MIN_VOTES = 1
# 내전을 이만큼 치르면 주관 지표는 힘을 잃고 실제 기록에 자리를 넘긴다.
TRAIT_FADE_GAMES = 10

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
# 표본이 모자랄 때 수축시킬 목표값. 중립(50)보다 낮게 잡아, 솔랭을 거의 안 한
# 사람의 넓은 숙련도가 실제로 검증된 폭과 같은 대우를 받지 않게 한다.
POOL_UNVERIFIED = 40.0
# 표본이 없어도 숙련도의 이만큼은 인정한다. 0 으로 두면 폭이 좁은 사람이
# 요소 하나뿐인 base_score 에서 최하점으로 굳는다.
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
    """1~10 척도를 0~100 으로 편다."""
    if average is None:
        return None

    return NEUTRAL + (average - 5.5) / 4.5 * NEUTRAL

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

    숙련도는 커리어 누적이라 지금도 그 폭이 유효한지는 알 수 없다. 그래서 시즌
    솔랭 판수가 POOL_SEASON_GAMES 에 못 미치면 POOL_UNVERIFIED 쪽으로 수축시켜,
    솔랭으로 확인된 폭보다 낮게 준다.
    """
    played = [value for value in points if value >= POOL_MIN_POINTS]
    if not played:
        return None

    best = max(played)
    pool = sum(1 for value in played if value >= best * POOL_RATIO)
    raw = min((pool - 1) / (POOL_FULL - 1), 1.0) * 100

    confidence = season_confidence(season_games)
    return POOL_UNVERIFIED + (raw - POOL_UNVERIFIED) * confidence

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
    custom: Optional[float] = None,
    mastery: Optional[float] = None,
    follow: Optional[float] = None,
) -> float:
    """제공된 요소만으로 가중 평균을 낸다. 없는 요소의 가중치는 나머지에 재분배된다.

    가중치는 합이 1 일 필요가 없다. 항상 있는 요소들끼리 다시 정규화하므로
    상대 비율만 의미가 있다.
    """
    components = {
        "tier": tier,
        "role": role,
        "recent_form": recent_form,
        "performance": performance,
        "custom": custom,
        "mastery": mastery,
        "follow": follow,
    }
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return NEUTRAL

    total_weight = sum(WEIGHTS[k] for k in available)
    return sum(WEIGHTS[k] * v for k, v in available.items()) / total_weight

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
    """기본 점수에 라인 적합도 배수를 적용한다(설계서 6.1)."""
    return score * ROLE_MULTIPLIERS[
        role_affinity(role, main_role, secondary_role, avoid_role)
    ]

def custom_score(games: int, wins: int) -> Optional[float]:
    """내전 성적을 0~100 으로 환산한다(설계서 6장 Custom Game Score).

    기록이 없으면 None 을 돌려 해당 가중치를 다른 요소에 재분배한다.
    """
    if games <= 0:
        return None

    win_rate = wins / games
    confidence = min(games / 10.0, 1.0)
    return NEUTRAL + (win_rate * 100 - NEUTRAL) * confidence
