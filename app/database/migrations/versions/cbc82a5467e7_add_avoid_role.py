"""add avoid role

Revision ID: cbc82a5467e7
Revises: ffd485212891
Create Date: 2026-08-19 17:12:55.620642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cbc82a5467e7'
down_revision: Union[str, Sequence[str], None] = 'ffd485212891'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("avoid_role", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "avoid_role")
