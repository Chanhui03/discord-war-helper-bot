from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
