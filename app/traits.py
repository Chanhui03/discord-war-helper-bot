"""서버 인원이 서로 매기는 주관 지표.

랭크·KDA 로는 잡히지 않는 것만 둔다. 표본이 적거나 내전 기록이 쌓이면
자동 지표에 자리를 넘기도록 scoring.trait_score 에서 힘을 줄인다.

오더를 메인오더와 오더수행으로 나눈 이유는 둘의 성질이 다르기 때문이다.
메인오더는 팀당 한 명이면 되는 배타적 자원이라 나눠 놓아야 하고, 오더수행은
많을수록 좋은 가산 자원이라 점수에 그대로 더한다. 한 숫자로 묶으면 수행이
좋은 사람까지 갈라 놓게 되고, 매기는 사람도 무엇을 넣어야 할지 모른다.
"""

from app.services.scoring import TRAIT_MIN_VOTES

MAIN_CALL = "MAIN_CALL"
FOLLOW = "FOLLOW"
CHAMPS = "CHAMPS"

TRAIT_LABELS = {MAIN_CALL: "메인오더", FOLLOW: "오더수행", CHAMPS: "챔피언폭"}

# 아무도 평가하지 않았을 때 보여줄 기본값. 1 이 기본이고 위로만 올라간다.
NEUTRAL_TRAIT = 1.0

def summary(scores) -> str:
    """평가 값 한 줄. 인원이 모자라면 아직 반영되지 않는다고 알린다."""
    parts = []
    for trait, label in TRAIT_LABELS.items():
        average, votes = scores.get(trait, (None, 0))
        value = f"{average:.1f}" if average is not None else f"{NEUTRAL_TRAIT:.1f}"
        note = f"{votes}명" if votes >= TRAIT_MIN_VOTES else f"{votes}/{TRAIT_MIN_VOTES}명"
        parts.append(f"{label} **{value}** ({note})")
    return " · ".join(parts)
