"""add champion and series

Revision ID: c9d3a71f5b28
Revises: b7f21cd93e04
Create Date: 2026-08-27 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d3a71f5b28'
down_revision: Union[str, Sequence[str], None] = 'b7f21cd93e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("match_players", sa.Column("champion_id", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("previous_match_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "previous_match_id")
    op.drop_column("match_players", "champion_id")
