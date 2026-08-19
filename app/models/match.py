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
