import httpx

from app.config.settings import settings
from app.services.riot.exceptions import RiotAPIError

class RiotClient:
    BASE_URL = "https://asia.api.riotgames.com"

    def __init__(self):
        self.headers = {
            "X-Riot-Token": settings.riot_api_key
        }

    async def get_account(self, game_name: str, tag_line: str):
        url = (
            f"{self.BASE_URL}"
            f"/riot/account/v1/accounts/by-riot-id/"
            f"{game_name}/{tag_line}"
        )

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

        if response.status_code == 403:
            raise RiotAPIError("Riot API Key가 올바르지 않습니다.")

        if response.status_code == 429:
            raise RiotAPIError("Riot API 요청 제한에 걸렸습니다.")

        raise RiotAPIError(
            f"Riot API 오류: {response.status_code}"
        )
