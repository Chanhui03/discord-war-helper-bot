"""설계서 7장 팀 생성 알고리즘.

10명을 5:5로 나누는 방법은 10C5 = 252가지이고 A/B 팀은 대칭이므로
첫 번째 참가자를 항상 A팀에 고정해 126가지만 탐색한다.

분할마다 두 팀의 라인 배정(각 5! = 120가지)을 함께 평가한다.
126 x 120 x 120 = 1,814,400 쌍이며 파이썬에서 1~2초가 걸리므로
호출부에서는 이벤트 루프를 막지 않도록 별도 스레드에서 실행한다.

차이 항만으로 점수를 매기면 '양 팀을 똑같이 나쁘게' 만드는 해가 최적이 되어
전원이 비선호 라인에 배치된다. 그래서 설계서 7장의 '역할 우선 조건'을
라인 적합도 손실(fit) 항으로 넣어, 선호 라인에서 벗어난 만큼 벌점을 준다.
"""

import random
from dataclasses import dataclass
from itertools import combinations, permutations
from typing import Dict, List, Optional, Sequence, Tuple

from app.roles import ROLES
from app.services.scoring import NEUTRAL, base_score, role_power

TEAM_SIZE = 5
LOBBY_SIZE = TEAM_SIZE * 2

# Balance Score 구성 요소별 가중치(설계서 7.2). 운영 데이터를 보고 조정한다.
BALANCE_WEIGHTS = {
    "skill": 1.0,
    "role": 0.5,
    "win_rate": 0.3,
    "recent_form": 0.2,
    "fit": 0.25,
}

# 이 차이 안에 있는 조합들은 동점으로 보고 무작위로 고른다(설계서 7.2).
TIEBREAK_EPSILON = 0.5

@dataclass(frozen=True)
class PlayerProfile:
    """밸런싱에 필요한 값만 담은 스냅샷."""

    player_id: int
    display: str
    tier: Optional[float]
    recent_form: Optional[float]
    performance: Optional[float]
    win_rate: float
    main_role: Optional[str]
    secondary_role: Optional[str]
    role_scores: Dict[str, float]

@dataclass(frozen=True)
class TeamPlan:
    members: Tuple[Tuple[PlayerProfile, str], ...]
    power: float
    role_power: Dict[str, float]
    win_rate: float
    recent_form: float

@dataclass(frozen=True)
class BalanceResult:
    team_a: TeamPlan
    team_b: TeamPlan
    score: float
    breakdown: Dict[str, float]
    splits: int
    evaluated: int

def power_of(profile: PlayerProfile, role: str) -> float:
    """해당 라인에 배정했을 때의 전투력(설계서 6장 + 6.1)."""
    return role_power(
        base_score(
            tier=profile.tier,
            role=profile.role_scores.get(role),
            recent_form=profile.recent_form,
            performance=profile.performance,
        ),
        role,
        profile.main_role,
        profile.secondary_role,
    )

def power_table(profiles: Sequence[PlayerProfile]) -> Dict[int, Dict[str, float]]:
    return {
        profile.player_id: {role: power_of(profile, role) for role in ROLES}
        for profile in profiles
    }

def assignment_options(
    team: Sequence[PlayerProfile], table: Dict[int, Dict[str, float]]
) -> List[Tuple[float, Tuple[float, ...], Tuple[str, ...]]]:
    """120가지 라인 배정을 (전투력 합, ROLES 순 파워, 배정 순열)로 펼친다."""
    options = []
    for order in permutations(ROLES):
        by_role = {
            role: table[member.player_id][role] for member, role in zip(team, order)
        }
        options.append(
            (sum(by_role.values()), tuple(by_role[role] for role in ROLES), order)
        )
    return options

def team_win_rate(team: Sequence[PlayerProfile]) -> float:
    return sum(member.win_rate for member in team) / len(team)

def team_recent_form(team: Sequence[PlayerProfile]) -> float:
    # 전적이 없는 참가자는 평균(50)으로 본다.
    return sum(
        NEUTRAL if member.recent_form is None else member.recent_form
        for member in team
    ) / len(team)

def make_plan(
    team: Sequence[PlayerProfile],
    order: Sequence[str],
    table: Dict[int, Dict[str, float]],
) -> TeamPlan:
    members = tuple(zip(team, order))
    return TeamPlan(
        members=members,
        power=sum(table[member.player_id][role] for member, role in members),
        role_power={role: table[member.player_id][role] for member, role in members},
        win_rate=team_win_rate(team),
        recent_form=team_recent_form(team),
    )

def fit_loss(
    team_a: TeamPlan, team_b: TeamPlan, table: Dict[int, Dict[str, float]]
) -> float:
    """전원을 최적 라인에 두었을 때 대비 잃은 전투력. 0이면 모두 선호 라인."""
    best = sum(
        max(table[member.player_id].values())
        for team in (team_a, team_b)
        for member, _ in team.members
    )
    return best - team_a.power - team_b.power

def balance_breakdown(
    team_a: TeamPlan, team_b: TeamPlan, table: Dict[int, Dict[str, float]]
) -> Dict[str, float]:
    return {
        "skill": abs(team_a.power - team_b.power),
        "role": sum(
            abs(team_a.role_power[role] - team_b.role_power[role]) for role in ROLES
        )
        / len(ROLES),
        "win_rate": abs(team_a.win_rate - team_b.win_rate) * 100,
        "recent_form": abs(team_a.recent_form - team_b.recent_form),
        "fit": fit_loss(team_a, team_b, table),
    }

def balance_score(
    team_a: TeamPlan, team_b: TeamPlan, table: Dict[int, Dict[str, float]]
) -> float:
    """작을수록 좋은 조합(설계서 7.2 + 라인 적합도)."""
    breakdown = balance_breakdown(team_a, team_b, table)
    return sum(BALANCE_WEIGHTS[key] * value for key, value in breakdown.items())

def find_best_teams(
    profiles: Sequence[PlayerProfile],
    rng: Optional[random.Random] = None,
) -> BalanceResult:
    if len(profiles) != LOBBY_SIZE:
        raise ValueError(f"참가자는 {LOBBY_SIZE}명이어야 합니다. (현재 {len(profiles)}명)")

    rng = rng or random
    table = power_table(profiles)
    total_best = sum(max(table[p.player_id].values()) for p in profiles)

    w_skill = BALANCE_WEIGHTS["skill"]
    w_role = BALANCE_WEIGHTS["role"] / len(ROLES)
    w_fit = BALANCE_WEIGHTS["fit"]

    # 분할마다 최선의 배정을 하나씩 남긴다. 동점 변주는 팀 구성 단위로 준다.
    results: List[Tuple[float, tuple, tuple, tuple, tuple]] = []
    evaluated = 0

    # 0번 참가자를 A팀에 고정해 A/B 대칭 중복을 제거한다.
    for combo in combinations(range(1, LOBBY_SIZE), TEAM_SIZE - 1):
        a_index = (0,) + combo
        b_index = tuple(i for i in range(LOBBY_SIZE) if i not in a_index)
        team_a = [profiles[i] for i in a_index]
        team_b = [profiles[i] for i in b_index]

        # 라인 배정과 무관한 항은 분할마다 한 번만 계산한다.
        constant = (
            BALANCE_WEIGHTS["win_rate"]
            * abs(team_win_rate(team_a) - team_win_rate(team_b))
            * 100
            + BALANCE_WEIGHTS["recent_form"]
            * abs(team_recent_form(team_a) - team_recent_form(team_b))
            + w_fit * total_best
        )

        # 전투력 합이 큰 배정부터 본다. skill/role 항은 0 이상이므로
        # constant - w_fit * (sum_a + sum_b) 가 현재 최선보다 나쁘면
        # 그 아래로는 볼 필요가 없다(설계서 7장 가지치기).
        options_a = sorted(assignment_options(team_a, table), reverse=True)
        options_b = sorted(assignment_options(team_b, table), reverse=True)
        max_sum_b = options_b[0][0]

        split_best = float("inf")
        split_pick = None

        for sum_a, power_a, order_a in options_a:
            if constant - w_fit * (sum_a + max_sum_b) > split_best:
                break
            for sum_b, power_b, order_b in options_b:
                if constant - w_fit * (sum_a + sum_b) > split_best:
                    break
                evaluated += 1
                # 핫 루프라 라인 5개 차이를 펼쳐 쓴다.
                score = (
                    w_skill * abs(sum_a - sum_b)
                    + w_role
                    * (
                        abs(power_a[0] - power_b[0])
                        + abs(power_a[1] - power_b[1])
                        + abs(power_a[2] - power_b[2])
                        + abs(power_a[3] - power_b[3])
                        + abs(power_a[4] - power_b[4])
                    )
                    - w_fit * (sum_a + sum_b)
                    + constant
                )
                if score < split_best:
                    split_best = score
                    split_pick = (order_a, order_b)

        results.append((split_best, a_index, b_index, *split_pick))

    best = min(item[0] for item in results)
    candidates = [item for item in results if item[0] <= best + TIEBREAK_EPSILON]
    _, a_index, b_index, order_a, order_b = rng.choice(candidates)
    plan_a = make_plan([profiles[i] for i in a_index], order_a, table)
    plan_b = make_plan([profiles[i] for i in b_index], order_b, table)

    return BalanceResult(
        team_a=plan_a,
        team_b=plan_b,
        score=balance_score(plan_a, plan_b, table),
        breakdown=balance_breakdown(plan_a, plan_b, table),
        splits=len(results),
        evaluated=evaluated,
    )
