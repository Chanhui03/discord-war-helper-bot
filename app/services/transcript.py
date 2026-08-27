"""내전 음성 대본과 전적을 함께 읽어 판별 평가를 만든다.

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
from app.services.matchmaking import TEAM_SIZE

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
    # 대본에서 이 사람의 목소리를 특정했는지. 못 했으면 평가하지 않는다.
    identified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    # 자기 팀 5명 안에서의 순위. 절대 점수는 판마다 기준이 흔들려 순위로 받는다.
    rank: Optional[int] = Field(default=None, ge=1, le=TEAM_SIZE)
    main_call: Optional[int] = Field(default=None, ge=1, le=10)
    # 근거가 된 실제 대사와 기록. 헛소리를 잡아내고 본인에게 보여줄 수 있어야 한다.
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

def scoreboard(entries) -> str:
    """전적 파일로 채워진 기록. 대본만으로는 안 보이는 것을 메운다.

    콜은 잘 냈지만 지표가 나쁜 경우와 그 반대를 가르려면 둘 다 필요하다.
    파일 없이 버튼으로만 확정한 내전은 기록이 비어 있어 대본만 남는다.
    """
    lines = []
    for entry in entries:
        head = (
            f"- player_id={entry.player_id} · {entry.player.riot_game_name} · "
            f"{ROLE_LABELS[entry.role]}"
        )
        if entry.kills is None:
            lines.append(f"{head} · (개인 기록 없음)")
            continue
        lines.append(
            f"{head} · {entry.kills}/{entry.deaths}/{entry.assists} · "
            f"CS {entry.cs} · 딜 {entry.damage:,} · 받은딜 {entry.damage_taken:,} · "
            f"골드 {entry.gold:,} · 와드 {entry.wards}"
            + (" · 첫킬" if entry.first_blood else "")
            + (" · 첫포탑" if entry.first_tower else "")
        )
    return "\n".join(lines)

def render(utterances: Sequence[Utterance]) -> str:
    return "\n".join(
        f"[{u.at // 60:02d}:{u.at % 60:02d}] {u.speaker}: {u.text}" for u in utterances
    )

INSTRUCTIONS = """당신은 롤 내전의 음성 대본과 전적 기록을 함께 읽고, 각 팀 안에서
누가 잘했는지 **순위**를 매긴다.

## 왜 점수가 아니라 순위인가
"7점"은 판마다 기준이 흔들린다. "5명 중 2등"은 그 판 안에서만 비교하므로
흔들리지 않는다. 팀별로 1~5 위를 빠짐없이, 중복 없이 매겨라.

## 무엇을 보고 매기는가
숫자와 말을 **함께** 봐야 나오는 판단을 하라. 어느 한쪽만으로는 안 되는 것들이다.
- 지표는 나쁘지만 콜을 계속 내서 팀을 움직인 사람은 위로
- 지표는 좋지만 이미 기운 뒤에 딴 것이거나 정작 한타에 없던 사람은 아래로
- 죽음이 무의미했는지 팀을 살린 것인지
- 오브젝트·교전 타이밍을 먼저 부르고 팀이 실제로 따랐는지

## 메인오더
순위와 별개로, 판을 읽고 지시를 내리는 능력을 1~10 으로 매겨라.
먼저 부르고 팀을 움직인 사람이 높다. 반응만 하거나 자기 라인 상황만
말하거나 조용한 사람은 낮다. **말을 많이 한 것과 잘한 것은 다르다.**

## 화자 식별
대본의 화자 이름이 로스터와 다를 수 있다. 대사에 나오는 이름과 라인으로 맞춰라.
- **확신이 없으면 identified=false 로 두고 rank 와 main_call 을 비워라.**
  잘못 붙이면 남의 플레이가 그 사람 기록이 되어 아무 데이터도 없는 것보다 나쁘다.
  억지로 5명을 다 채우지 마라.

## 규칙
- evidence 에는 **대본이나 전적에 실제로 있는 것만** 옮겨라. 지어내지 마라.
  identified=false 면 왜 못 가렸는지 적어라.
- 관전자 대본은 맥락 참고용이다. 관전자에게는 순위를 매기지 마라.
- 로스터에 있는 player_id 만 쓰고, 로스터의 모든 사람을 한 번씩 넣어라.
- 개인 기록이 없는 판은 대본만 보고 매겨라."""

def build_prompt(
    team_a, team_b, transcripts: Dict[str, str], spectators: Optional[str] = None
) -> str:
    """팀별 로스터·전적·대본을 한 프롬프트로 묶는다.

    과거 점수는 넣지 않는다. 알려주면 거기에 닻을 내려서 새 증거가 독립적인
    측정이 아니라 기존 점수의 메아리가 된다.
    """
    parts = [INSTRUCTIONS, ""]
    for label, entries in (("A팀", team_a), ("B팀", team_b)):
        won = entries and entries[0].win
        mark = " (승)" if won else " (패)" if won is False else ""
        parts += [
            f"## {label}{mark} 로스터와 전적",
            scoreboard(entries),
            "",
            f"## {label} 음성 대본",
            render(parse(transcripts.get(label, ""))) or "(대본 없음)",
            "",
        ]
    if spectators:
        parts += [
            "## 관전자 대본 (맥락 참고용 · 순위 대상 아님)",
            render(parse(spectators)) or "(없음)",
            "",
        ]
    return "\n".join(parts)

def usable(report: CallReport, allowed: Sequence[int]) -> List[PlayerCall]:
    """쓸 수 있는 결과만 남긴다.

    로스터에 없는 player_id 는 버린다(모델이 지어낸 것). 식별에 실패했거나 확신이
    낮으면 그 사람은 이번 판을 건너뛴다.
    """
    known = set(allowed)
    return [
        call
        for call in report.players
        if call.player_id in known
        and call.identified
        and call.rank is not None
        and call.main_call is not None
        and call.confidence >= MIN_CONFIDENCE
    ]

def ranked(calls: Sequence[PlayerCall], roster: Sequence[int]) -> List[PlayerCall]:
    """한 팀의 순위가 성립하는지 본다. 중복이 있으면 그 팀은 통째로 버린다.

    순위는 팀 안의 상대 비교라, 2등이 둘이면 나머지 등수의 의미도 무너진다.
    한 명이 빠진 것(식별 실패)은 괜찮지만 겹치는 것은 괜찮지 않다.
    """
    team = [call for call in calls if call.player_id in set(roster)]
    ranks = [call.rank for call in team]
    return [] if len(ranks) != len(set(ranks)) else team

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
    calls = usable(response.parsed_output, allowed)
    # 순위는 팀별로 성립해야 한다. 한 팀이 깨져도 다른 팀은 살린다.
    return ranked(calls, [e.player_id for e in team_a]) + ranked(
        calls, [e.player_id for e in team_b]
    )
