"""내전에서 사용하는 5개 라인 정의."""

ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

ROLE_LABELS = {
    "TOP": "탑",
    "JUNGLE": "정글",
    "MID": "미드",
    "ADC": "원딜",
    "SUPPORT": "서폿",
}

# match-v5 의 teamPosition 값을 내부 라인 코드로 변환한다.
RIOT_POSITIONS = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
    "UTILITY": "SUPPORT",
}
