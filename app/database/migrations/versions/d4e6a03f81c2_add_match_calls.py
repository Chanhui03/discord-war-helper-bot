"""add match calls

Revision ID: d4e6a03f81c2
Revises: c81b5e2a94df
Create Date: 2026-08-27 16:02:33.410882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e6a03f81c2'
down_revision: Union[str, Sequence[str], None] = 'c81b5e2a94df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("main_call", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "player_id", name="uq_match_calls_match_player"),
    )
    op.create_index("ix_match_calls_match_id", "match_calls", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_match_calls_match_id", table_name="match_calls")
    op.drop_table("match_calls")
