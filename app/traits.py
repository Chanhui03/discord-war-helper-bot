"""서버 인원이 서로 매기는 주관 지표.

랭크·KDA 로는 잡히지 않는 두 가지만 둔다. 표본이 적거나 내전 기록이 쌓이면
자동 지표에 자리를 넘기도록 scoring.trait_score 에서 힘을 줄인다.
"""

from app.services.scoring import TRAIT_MIN_VOTES

SHOTCALL = "SHOTCALL"
CHAMPS = "CHAMPS"

TRAIT_LABELS = {SHOTCALL: "오더능력", CHAMPS: "챔피언폭"}

# 아무도 평가하지 않았을 때 보여줄 중간값(1~10 척도).
NEUTRAL_TRAIT = 5.5

def summary(scores) -> str:
    """평가 값 한 줄. 인원이 모자라면 아직 반영되지 않는다고 알린다."""
    parts = []
    for trait, label in TRAIT_LABELS.items():
        average, votes = scores.get(trait, (None, 0))
        value = f"{average:.1f}" if average is not None else f"{NEUTRAL_TRAIT:.1f}"
        note = f"{votes}명" if votes >= TRAIT_MIN_VOTES else f"{votes}/{TRAIT_MIN_VOTES}명"
        parts.append(f"{label} **{value}** ({note})")
    return " · ".join(parts)
