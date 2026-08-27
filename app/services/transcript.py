"""내전 음성 대본에서 메인오더 점수를 뽑는다.

오더는 텍스트 지표로는 잡히지 않고 음성에서만 드러난다. 팀 채널이 나뉘어 있어
파일 자체가 팀의 정답지이고, 후보는 그 팀 5명으로 좁혀진다.

다만 전사 모델이 주는 것은 '목소리가 몇 종류인가'까지다. 2번 목소리가 누구인지는
음성만으로 알 수 없다. 그래서 배정 라인이 담긴 로스터를 함께 넘겨, 대사에 나오는
이름과 라인으로 묶게 한다. 그래도 못 가리는 사람이 남는데, 화자를 잘못 붙이면
남의 콜이 내 점수가 되어 없느니만 못하므로 확신이 낮으면 버린다.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.config.settings import settings
from app.roles import ROLE_LABELS

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

# 이보다 확신이 낮은 화자 식별은 쓰지 않는다. 틀리게 쓰느니 안 쓴다.
MIN_CONFIDENCE = 0.6

# [00:12:03] S1: 드래곤 버리고 탑 밀자
LINE = re.compile(r"^\[(\d+):(\d{2}):(\d{2})\]\s*([^:]+?):\s*(.+)$")

class TranscriptError(Exception):
    pass

@dataclass(frozen=True)
class Utterance:
    at: int  # 초
    speaker: str  # 목소리 군집 번호(S1...). 누구인지는 아직 모른다.
    text: str

class PlayerCall(BaseModel):
    player_id: int
    # 대본에서 이 사람의 목소리를 특정했는지. 못 했으면 점수를 매기지 않는다.
    identified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    main_call: Optional[int] = Field(default=None, ge=1, le=10)
    # 점수 근거가 된 실제 대사. 헛소리를 잡아내고 본인에게 보여줄 수 있어야 한다.
    evidence: str

class CallReport(BaseModel):
    players: List[PlayerCall]

def parse(raw: str) -> List[Utterance]:
    """대본 한 편을 발화 목록으로. 형식에 맞지 않는 줄은 건너뛴다."""
    utterances = []
    for line in raw.splitlines():
        match = LINE.match(line.strip())
        if match is None:
            continue
        hours, minutes, seconds, speaker, text = match.groups()
        utterances.append(
            Utterance(
                at=int(hours) * 3600 + int(minutes) * 60 + int(seconds),
                speaker=speaker.strip(),
                text=text.strip(),
            )
        )
    return utterances

def roster_lines(entries) -> str:
    """모델이 목소리를 사람에 붙일 단서. 배정 라인이 대사에 자주 등장한다."""
    return "\n".join(
        f"- player_id={entry.player_id} · {entry.player.riot_game_name}"
        f"#{entry.player.riot_tagline} · {ROLE_LABELS[entry.role]}"
        for entry in entries
    )

def render(utterances: Sequence[Utterance]) -> str:
    return "\n".join(
        f"[{u.at // 60:02d}:{u.at % 60:02d}] {u.speaker}: {u.text}" for u in utterances
    )

INSTRUCTIONS = """당신은 롤 내전 음성 대본을 읽고 참가자의 **메인오더 능력**을 매긴다.

메인오더란 판을 읽고 팀에게 무엇을 할지 지시하는 능력이다. 오브젝트를 언제 칠지,
누구를 물지, 언제 빠질지를 먼저 말하고 팀을 움직이는 사람이 높다.
남의 콜에 반응만 하거나, 자기 라인 상황만 말하거나, 조용한 사람은 낮다.

대본의 S1, S2 ... 는 목소리 군집 번호일 뿐 누구인지 모른다. 아래 단서로 사람에 붙여라.
- 서로 이름을 부른다 ("찬희야 백")
- 자기 라인을 말한다 ("나 정글인데") — 로스터의 배정 라인과 맞춰라
- 라인 상황을 말하는 위치로 역할이 드러난다

중요한 규칙:
- **확신이 없으면 identified=false 로 두고 점수를 비워라.** 화자를 잘못 붙이면
  남의 콜이 그 사람 점수가 되어 아무 데이터도 없는 것보다 나쁘다. 억지로 5명을
  다 채우지 마라. 못 가리겠으면 못 가리겠다고 하라.
- evidence 에는 **대본에 실제로 있는 대사를 그대로** 옮겨라. 지어내지 마라.
  identified=false 면 왜 못 가렸는지 적어라.
- 말을 많이 한 것과 오더를 잘한 것은 다르다. 짧아도 팀을 실제로 움직인 지시가
  중요하고, 길게 떠들기만 한 것은 높지 않다.
- 관전자 대본은 맥락 참고용이다. 관전자에게는 점수를 매기지 마라.
- 로스터에 있는 player_id 만 쓰고, 로스터의 모든 사람을 한 번씩 넣어라."""

def build_prompt(
    team_a, team_b, transcripts: Dict[str, str], spectators: Optional[str] = None
) -> str:
    """팀별 로스터와 대본을 한 프롬프트로 묶는다."""
    parts = [INSTRUCTIONS, ""]
    for label, entries in (("A팀", team_a), ("B팀", team_b)):
        parts += [
            f"## {label} 로스터",
            roster_lines(entries),
            "",
            f"## {label} 음성 대본",
            render(parse(transcripts[label])) or "(대본 없음)",
            "",
        ]
    if spectators:
        parts += [
            "## 관전자 대본 (맥락 참고용 · 점수 대상 아님)",
            render(parse(spectators)) or "(없음)",
            "",
        ]
    return "\n".join(parts)

def usable(report: CallReport, allowed: Sequence[int]) -> List[PlayerCall]:
    """쓸 수 있는 결과만 남긴다.

    로스터에 없는 player_id 는 버린다(모델이 지어낸 것). 식별에 실패했거나 확신이
    낮으면 그 사람은 이번 판 점수를 건너뛴다.
    """
    known = set(allowed)
    return [
        call
        for call in report.players
        if call.player_id in known
        and call.identified
        and call.main_call is not None
        and call.confidence >= MIN_CONFIDENCE
    ]

async def score_calls(
    team_a, team_b, transcripts: Dict[str, str], spectators: Optional[str] = None
) -> List[PlayerCall]:
    """대본을 읽고 메인오더 점수를 낸다. 확신이 낮은 사람은 빠진다."""
    import anthropic

    if not any(transcripts.get(label, "").strip() for label in ("A팀", "B팀")):
        raise TranscriptError("읽을 수 있는 대본이 없습니다.")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        messages=[
            {
                "role": "user",
                "content": build_prompt(team_a, team_b, transcripts, spectators),
            }
        ],
        output_format=CallReport,
    )

    allowed = [entry.player_id for entry in list(team_a) + list(team_b)]
    return usable(response.parsed_output, allowed)
