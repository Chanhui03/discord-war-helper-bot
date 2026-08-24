from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# 실행 위치와 무관하게 같은 DB 파일을 쓰도록 저장소 루트를 기준으로 잡는다.
ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    discord_token: str
    riot_api_key: str
    database_url: str = f"sqlite+aiosqlite:///{ROOT / 'war_helper.db'}"
    # 쉼표로 여러 서버를 적을 수 있다. 비우면 전역 등록.
    # NoDecode 가 없으면 pydantic 이 "1,2" 를 JSON 으로 파싱하려다 실패한다.
    discord_guild_ids: Annotated[List[int], NoDecode] = Field(
        default=[], validation_alias="DISCORD_GUILD_ID"
    )

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra='ignore',
    )

    @field_validator("discord_guild_ids", mode="before")
    @classmethod
    def _split_guild_ids(cls, value):
        if isinstance(value, str):
            return [part for part in (p.strip() for p in value.split(",")) if part]
        return value

settings = Settings()
