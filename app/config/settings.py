from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# 실행 위치와 무관하게 같은 DB 파일을 쓰도록 저장소 루트를 기준으로 잡는다.
ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    discord_token: str
    riot_api_key: str
    # 음성 대본 채점에만 쓴다. 비워두면 /오더채점 만 동작하지 않는다.
    anthropic_api_key: str = ""
    database_url: str = f"sqlite+aiosqlite:///{ROOT / 'war_helper.db'}"
    # 최고 티어를 op.gg 에서 한 번 받아올지. 우리가 직접 쌓는 최고 티어는 등록
    # 시점부터라 시즌 초에 비어 있어서, 그 구멍만 메우는 용도다. 꺼도 점수는
    # 그대로 나오고 최고 티어만 등록 이후 기록으로 채워진다.
    opgg_backfill: bool = True
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
