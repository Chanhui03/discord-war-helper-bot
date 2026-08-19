from typing import Any, Dict, List

import httpx

from app.config.settings import settings
from app.services.riot.exceptions import RiotAPIError

class RiotClient:
    # 계정/경기 정보는 광역 라우팅, 랭크 정보는 플랫폼 라우팅을 쓴다.
    REGIONAL_URL = "https://asia.api.riotgames.com"
    PLATFORM_URL = "https://kr.api.riotgames.com"

    def __init__(self):
        self.headers = {
            "X-Riot-Token": settings.riot_api_key
        }

    async def _get(self, url: str) -> Any:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                timeout=10.0,
            )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise RiotAPIError("존재하지 않는 Riot ID입니다.")

        if response.status_code in (401, 403):
            raise RiotAPIError("Riot API Key가 올바르지 않습니다.")

        if response.status_code == 429:
            raise RiotAPIError("Riot API 요청 제한에 걸렸습니다.")

        raise RiotAPIError(
            f"Riot API 오류: {response.status_code}"
        )

    async def get_account(self, game_name: str, tag_line: str) -> Dict[str, Any]:
        return await self._get(
            f"{self.REGIONAL_URL}"
            f"/riot/account/v1/accounts/by-riot-id/"
            f"{game_name}/{tag_line}"
        )

    async def get_league_entries(self, puuid: str) -> List[Dict[str, Any]]:
        return await self._get(
            f"{self.PLATFORM_URL}/lol/league/v4/entries/by-puuid/{puuid}"
        )

    async def get_match_ids(self, puuid: str, count: int) -> List[str]:
        return await self._get(
            f"{self.REGIONAL_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?start=0&count={count}"
        )

    async def get_match(self, match_id: str) -> Dict[str, Any]:
        return await self._get(
            f"{self.REGIONAL_URL}/lol/match/v5/matches/{match_id}"
        )
