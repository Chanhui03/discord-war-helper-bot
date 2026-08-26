"""add detailed match stats

Revision ID: b73d1c40e9a2
Revises: a1f7c93be204
Create Date: 2026-08-26 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b73d1c40e9a2'
down_revision: Union[str, Sequence[str], None] = 'a1f7c93be204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("duration", sa.Integer(), nullable=True))
    for column, type_ in (
        ("damage_taken", sa.Integer()),
        ("wards", sa.Integer()),
        ("first_blood", sa.Boolean()),
        ("first_tower", sa.Boolean()),
        ("played_role", sa.String(length=8)),
    ):
        op.add_column("match_players", sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    for column in ("played_role", "first_tower", "first_blood", "wards", "damage_taken"):
        op.drop_column("match_players", column)
    op.drop_column("matches", "duration")
