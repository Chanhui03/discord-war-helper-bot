from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
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

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_server_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game_type: Mapped[str] = mapped_column(String(16), default="5v5")
    # 사설 전적 파일로 확정한 내전만 채워진다. 분당 지표(DPM 등)의 분모다.
    duration: Mapped[Optional[int]] = mapped_column(Integer)
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
    damage_taken: Mapped[Optional[int]] = mapped_column(Integer)
    gold: Mapped[Optional[int]] = mapped_column(Integer)
    wards: Mapped[Optional[int]] = mapped_column(Integer)
    first_blood: Mapped[Optional[bool]] = mapped_column(Boolean)
    first_tower: Mapped[Optional[bool]] = mapped_column(Boolean)
    # 실제로 간 라인. 배정(role)과 다를 수 있어 따로 남긴다.
    played_role: Mapped[Optional[str]] = mapped_column(String(8))

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

class MatchReview(Base):
    """대본과 전적을 함께 읽은 판별 평가. 한 내전에 한 사람당 한 행.

    절대 점수가 아니라 팀 안에서의 순위(1~5)를 받는다. '7점'은 판마다 기준이
    흔들리지만 '5명 중 2등'은 그 판 안에서만 비교하므로 드리프트가 없다.
    누적할 때도 평균 순위가 평균 점수보다 안정적이다.

    근거를 함께 남겨, 점수가 이상할 때 무엇을 보고 그렇게 매겼는지 확인한다.
    """

    __tablename__ = "match_reviews"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_match_calls_match_player"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    # 자기 팀 5명 안에서의 순위. 1 등이 그 팀에서 제일 잘한 사람.
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    main_call: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[str] = mapped_column(String(500), default="")

class MatchVote(Base):
    """MVP 직접 투표. 이긴 팀과 관전자가 한 명씩 고른다.

    9명에게 1~10 을 매기던 방식은 아무도 끝까지 하지 않아 표가 비었다.
    한 번 누르면 끝나는 쪽이 실제로 모인다. 이 표는 밸런싱에 쓰지 않고,
    AI 가 매긴 순위가 사람 판단과 맞는지 확인하는 정답지로 쓴다.
    """

    __tablename__ = "match_votes"
    __table_args__ = (
        UniqueConstraint("match_id", "voter_discord_id", name="uq_match_votes_voter"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    # 관전자도 던지므로 Discord 사용자로 둔다.
    voter_discord_id: Mapped[int] = mapped_column(BigInteger)
    target_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))

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
