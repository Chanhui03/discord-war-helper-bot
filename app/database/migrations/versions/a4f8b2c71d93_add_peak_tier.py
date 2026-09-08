"""add peak tier

Revision ID: a4f8b2c71d93
Revises: c9d3a71f5b28
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f8b2c71d93'
down_revision: Union[str, Sequence[str], None] = 'c9d3a71f5b28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("peak_tier", sa.String(16), nullable=True))
    op.add_column("player_stats", sa.Column("peak_division", sa.String(4), nullable=True))
    op.add_column(
        "player_stats",
        sa.Column("peak_lp", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("player_stats", "peak_lp")
    op.drop_column("player_stats", "peak_division")
    op.drop_column("player_stats", "peak_tier")
