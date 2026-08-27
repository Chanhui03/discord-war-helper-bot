"""챔피언 한글 이름. Data Dragon 에서 한 번 받아 프로세스에 캐시한다.

사설 전적 파일에는 championId 숫자만 들어 있어 이름표가 따로 필요하다.
파일로 들고 있으면 신규 챔피언이 나올 때마다 갱신해야 하므로 받아서 쓴다.
"""

import logging
from typing import Dict, Optional

import httpx

from app.log import warn

log = logging.getLogger(__name__)

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPIONS_URL = (
    "https://ddragon.leagueoflegends.com/cdn/{version}/data/ko_KR/champion.json"
)

_names: Optional[Dict[int, str]] = None

async def champion_names() -> Dict[int, str]:
    """championId 별 한글 이름. 받아오지 못하면 빈 표를 돌려준다."""
    global _names
    if _names is not None:
        return _names

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            versions = (await client.get(VERSIONS_URL)).json()
            payload = (
                await client.get(CHAMPIONS_URL.format(version=versions[0]))
            ).json()
        _names = {
            int(champion["key"]): champion["name"]
            for champion in payload["data"].values()
        }
    except (httpx.HTTPError, ValueError, LookupError) as error:
        # 이름표가 없어도 번호로는 보여줄 수 있으니 기능 전체를 막지는 않는다.
        warn(log, "ddragon_error", error=str(error))
        return {}

    return _names
