"""rename match calls to reviews, add rank and mvp votes

Revision ID: b7f21cd93e04
Revises: d4e6a03f81c2
Create Date: 2026-08-27 17:14:52.301776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f21cd93e04'
down_revision: Union[str, Sequence[str], None] = 'd4e6a03f81c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 메인오더만 매기던 표에서 판 전체를 평가하는 표로 바뀌어 이름을 옮긴다.
    op.drop_index("ix_match_calls_match_id", table_name="match_calls")
    op.rename_table("match_calls", "match_reviews")
    op.create_index("ix_match_reviews_match_id", "match_reviews", ["match_id"])
    # 팀 안에서의 순위(1~5). 절대 점수는 판마다 기준이 흔들려 순위로 받는다.
    op.add_column("match_reviews", sa.Column("rank", sa.Integer(), nullable=True))

    # MVP 직접 투표. 9명에게 1~10 을 매기는 기존 평점을 대신한다.
    op.create_table(
        "match_votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("voter_discord_id", sa.BigInteger(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # 한 사람은 한 판에 한 표만 던진다.
        sa.UniqueConstraint("match_id", "voter_discord_id", name="uq_match_votes_voter"),
    )
    op.create_index("ix_match_votes_match_id", "match_votes", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_match_votes_match_id", table_name="match_votes")
    op.drop_table("match_votes")
    op.drop_column("match_reviews", "rank")
    op.drop_index("ix_match_reviews_match_id", table_name="match_reviews")
    op.rename_table("match_reviews", "match_calls")
    op.create_index("ix_match_calls_match_id", "match_calls", ["match_id"])
