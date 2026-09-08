"""add vision and objective stats

Revision ID: b6d21e04f8a7
Revises: a4f8b2c71d93
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6d21e04f8a7'
down_revision: Union[str, Sequence[str], None] = 'a4f8b2c71d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = ("vision_score", "wards_killed", "objective_damage", "cc_time")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("match_players", sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("match_players", name)
