from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("discord_id", "game", name="uq_players_discord_id_game"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game: Mapped[str] = mapped_column(String(16), default="lol")
    riot_game_name: Mapped[str] = mapped_column(String(32))
    riot_tagline: Mapped[str] = mapped_column(String(8))
    puuid: Mapped[str] = mapped_column(String(78), unique=True)
    region: Mapped[str] = mapped_column(String(8), default="kr")
    main_role: Mapped[Optional[str]] = mapped_column(String(8))
    secondary_role: Mapped[Optional[str]] = mapped_column(String(8))
    avoid_role: Mapped[Optional[str]] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stats: Mapped[Optional["PlayerStats"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )
    roles: Mapped[List["PlayerRole"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )

class PlayerAlias(Base):
    """부계정 Riot ID. 전적 파일에서 참가자를 알아보는 데만 쓴다.

    솔랭 지표는 본계정에서만 받아온다. riot_id 는 대소문자를 무시한 비교용 키이고,
    남의 계정을 자기 부계정으로 등록하지 못하도록 전체에서 유일해야 한다.
    """

    __tablename__ = "player_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    riot_id: Mapped[str] = mapped_column(String(48), unique=True)
    riot_game_name: Mapped[str] = mapped_column(String(32))
    riot_tagline: Mapped[str] = mapped_column(String(8))

class PlayerTrait(Base):
    """오더능력·챔피언폭 같은 주관 지표. 여러 명이 매긴 평균을 쓴다.

    평가자는 Riot 계정 등록 없이도 매길 수 있어 Discord 사용자로 둔다.
    """

    __tablename__ = "player_traits"
    __table_args__ = (
        UniqueConstraint(
            "target_id", "rater_discord_id", "trait", name="uq_player_traits_rater"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    rater_discord_id: Mapped[int] = mapped_column(BigInteger)
    trait: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)

class PlayerStats(Base):
    __tablename__ = "player_stats"

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    tier: Mapped[Optional[str]] = mapped_column(String(16))
    division: Mapped[Optional[str]] = mapped_column(String(4))
    lp: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_kda: Mapped[float] = mapped_column(Float, default=0.0)
    recent_win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # 최근 폼을 집계한 경기 수. 0 이면 솔랭 표본이 없다는 뜻이라 최근 폼/KDA 를
    # 점수에 쓰지 않는다.
    recent_games: Mapped[int] = mapped_column(Integer, default=0)
    # 챔피언 숙련도에서 계산한 챔피언폭(0~100). 조회할 수 없으면 비워 둔다.
    champion_pool: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

class PlayerRole(Base):
    __tablename__ = "player_roles"

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(8), primary_key=True)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_kda: Mapped[float] = mapped_column(Float, default=0.0)
    role_score: Mapped[float] = mapped_column(Float, default=0.0)
