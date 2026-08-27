"""add champion pool

Revision ID: f3a7d21e9b40
Revises: e1c4b8d92f57
Create Date: 2026-08-27 14:40:12.104883

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a7d21e9b40'
down_revision: Union[str, Sequence[str], None] = 'e1c4b8d92f57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("champion_pool", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_stats", "champion_pool")
