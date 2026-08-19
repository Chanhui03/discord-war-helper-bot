"""설계서 6장의 설명 가능한 가중합 점수 모델."""

from typing import Optional

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
}

# 설계서 6.1 라인 적합도 배수.
ROLE_MULTIPLIERS = {
    "main": 1.00,
    "secondary": 0.85,
    "off": 0.70,
    "unknown": 0.60,
}

NEUTRAL = 50.0

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

def base_score(
    tier: Optional[float] = None,
    role: Optional[float] = None,
    recent_form: Optional[float] = None,
    performance: Optional[float] = None,
    custom: Optional[float] = None,
    mastery: Optional[float] = None,
) -> float:
    """제공된 요소만으로 가중 평균을 낸다. 없는 요소의 가중치는 나머지에 재분배된다."""
    components = {
        "tier": tier,
        "role": role,
        "recent_form": recent_form,
        "performance": performance,
        "custom": custom,
        "mastery": mastery,
    }
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return NEUTRAL

    total_weight = sum(WEIGHTS[k] for k in available)
    return sum(WEIGHTS[k] * v for k, v in available.items()) / total_weight

def role_affinity(role: str, main_role: Optional[str], secondary_role: Optional[str]) -> str:
    """해당 라인이 주라인/부라인/비선호/미지 중 무엇인지 판정한다."""
    if main_role is None and secondary_role is None:
        return "unknown"
    if role == main_role:
        return "main"
    if role == secondary_role:
        return "secondary"
    return "off"

def role_power(score: float, role: str, main_role: Optional[str], secondary_role: Optional[str]) -> float:
    """기본 점수에 라인 적합도 배수를 적용한다(설계서 6.1)."""
    return score * ROLE_MULTIPLIERS[role_affinity(role, main_role, secondary_role)]
