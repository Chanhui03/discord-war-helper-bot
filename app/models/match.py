from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_server_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game_type: Mapped[str] = mapped_column(String(16), default="5v5")
    team_a_score: Mapped[int] = mapped_column(Integer, default=0)
    team_b_score: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    participants: Mapped[List["MatchPlayer"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="MatchPlayer.id"
    )
    # 평점은 로비를 그릴 때마다 끌고 올 필요가 없어 관계로 두지 않는다.
    spectators: Mapped[List["MatchSpectator"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="MatchSpectator.id"
    )

class MatchPlayer(Base):
    """내전 참가자 스냅샷. 팀/라인은 밸런싱 후에, 성적은 결과 입력 후에 채워진다."""

    __tablename__ = "match_players"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_match_players_match_player"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    team: Mapped[Optional[str]] = mapped_column(String(1))
    role: Mapped[Optional[str]] = mapped_column(String(8))
    win: Mapped[Optional[bool]] = mapped_column(Boolean)
    kills: Mapped[Optional[int]] = mapped_column(Integer)
    deaths: Mapped[Optional[int]] = mapped_column(Integer)
    assists: Mapped[Optional[int]] = mapped_column(Integer)
    cs: Mapped[Optional[int]] = mapped_column(Integer)
    damage: Mapped[Optional[int]] = mapped_column(Integer)
    gold: Mapped[Optional[int]] = mapped_column(Integer)

    player: Mapped["Player"] = relationship(lazy="selectin")

class MatchSpectator(Base):
    """관전자. Riot 계정 등록 없이 참여하므로 Discord 사용자만 남긴다."""

    __tablename__ = "match_spectators"
    __table_args__ = (
        UniqueConstraint("match_id", "discord_id", name="uq_match_spectators_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    discord_id: Mapped[int] = mapped_column(BigInteger)

class MatchRating(Base):
    """경기 후 남긴 평점. MVP 는 이 평균에서 나온다.

    평가는 관전자도 할 수 있어 평가자에게는 player 행이 없을 수 있다. 그래서
    rater 는 Discord 사용자로 두고, 대상만 참가자(player_id)로 묶는다.
    """

    __tablename__ = "match_ratings"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "rater_discord_id",
            "target_id",
            name="uq_match_ratings_rater_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    rater_discord_id: Mapped[int] = mapped_column(BigInteger)
    target_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(Integer)
