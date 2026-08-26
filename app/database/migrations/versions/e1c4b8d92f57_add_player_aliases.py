"""add player aliases

Revision ID: e1c4b8d92f57
Revises: d5a91c7fe310
Create Date: 2026-08-27 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1c4b8d92f57'
down_revision: Union[str, Sequence[str], None] = 'd5a91c7fe310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("riot_id", sa.String(length=48), nullable=False),
        sa.Column("riot_game_name", sa.String(length=32), nullable=False),
        sa.Column("riot_tagline", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("riot_id"),
    )
    op.create_index(op.f("ix_player_aliases_player_id"), "player_aliases", ["player_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_player_aliases_player_id"), table_name="player_aliases")
    op.drop_table("player_aliases")
