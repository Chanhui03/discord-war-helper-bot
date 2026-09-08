"""op.gg 소환사 페이지에서 과거 시즌 최고 티어를 읽는다.

Riot API 는 지난 시즌 티어를 돌려주지 않는다. 우리가 직접 쌓는 최고 티어는
등록 시점부터라 시즌 초에 비어 있는데, 정확히 그때가 보정이 가장 필요한
시점이다. 그 구멍만 op.gg 로 한 번 메운다.

읽는 값은 페이지에 서버 렌더링으로 박혀 있는 시즌별 high_rank_info 다.
Next.js 페이로드 안에 이중 이스케이프된 조각으로 흩어져 있어 잘 깨진다.
그래서 이 모듈은 실패를 정상으로 취급하고 None 을 돌려준다. 최고 티어는
없어도 점수가 나오는 보조 지표이므로, 깨져도 봇은 그대로 돈다.
"""

import json
import logging
import re
from typing import Optional, Tuple
from urllib.parse import quote

import httpx

from app.log import warn

log = logging.getLogger(__name__)

PROFILE_URL = "https://www.op.gg/summoners/kr/{riot_id}"

# 브라우저가 아니면 막는 경우가 있어 평범한 UA 를 붙인다.
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10.0

# 시즌별 티어 조각. 두 키가 나란히 온다.
#   high_rank_info — 그 시즌 최고 티어. 비어 있는 시즌도 있다.
#   rank_info      — 그 시즌 최종 티어. high 가 비어도 이쪽에는 값이 있다.
# 둘 다 읽고 가장 높은 것을 고른다.
#
#   "high_rank_info":{"tier":"emerald 3","value":"EMERALD","division":3,"lp":"8", ...
#   "rank_info":{"tier":"","value":"Unranked","division":"$undefined","lp":null, ...
#
# tier 는 프로 계정이면 "challenger", 일반 계정이면 "emerald 3" 처럼 디비전이
# 붙어 나와 못 믿는다. 대문자로 오는 value 를 쓴다. 마스터 이상은 division 이
# "$undefined" 이고, 판을 안 한 시즌은 lp 가 null 이다.
ENTRY_PATTERN = re.compile(
    r'"(?:high_rank_info|rank_info)":\{"tier":"[^"]*","value":"(?P<tier>[A-Za-z]+)",'
    r'"division":(?P<division>\d+|"?\$undefined"?),"lp":(?P<lp>"[\d,]+"|null)'
)

# op.gg 는 디비전을 숫자로 준다. 우리는 로마자를 쓴다.
DIVISIONS = {1: "I", 2: "II", 3: "III", 4: "IV"}

Peak = Tuple[str, Optional[str], int]

def unescape(body: str) -> str:
    """Next.js 페이로드의 이중 이스케이프를 한 겹 벗긴다.

    본문이 self.__next_f.push([1,"...json..."]) 안에 문자열로 들어 있어
    따옴표가 \\" 로 한 번 더 감싸여 있다.
    """
    return body.replace('\\\\"', "\x00").replace('\\"', '"').replace("\x00", '\\"')

def parse_peak(body: str) -> Optional[Peak]:
    """HTML 에서 가장 높은 시즌 티어를 뽑는다. 못 찾으면 None.

    언랭 시즌이나 모르는 티어 이름은 tier_score 가 None 을 돌려주므로 걸러진다.
    """
    from app.services.scoring import tier_score

    best: Optional[Peak] = None
    best_score = -1.0
    for match in ENTRY_PATTERN.finditer(unescape(body)):
        tier = match.group("tier").upper()
        raw_division = match.group("division")
        division = DIVISIONS.get(int(raw_division)) if raw_division.isdigit() else None
        raw_lp = match.group("lp")
        lp = 0 if raw_lp == "null" else int(raw_lp.strip('"').replace(",", ""))

        score = tier_score(tier, division, lp)
        if score is not None and score > best_score:
            best, best_score = (tier, division, lp), score
    return best

async def fetch_peak(game_name: str, tagline: str) -> Optional[Peak]:
    """op.gg 에서 이 계정의 과거 시즌 최고 티어를 받아온다. 실패하면 None."""
    url = PROFILE_URL.format(riot_id=quote(f"{game_name}-{tagline}"))
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
            )
        if response.status_code != 200:
            warn(log, "opgg_status", status=response.status_code)
            return None
        return parse_peak(response.text)
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
        # 남의 사이트라 언제든 모양이 바뀔 수 있다. 없으면 없는 대로 간다.
        warn(log, "opgg_failed", error=type(error).__name__)
        return None
