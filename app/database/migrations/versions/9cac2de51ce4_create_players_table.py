"""create players table

Revision ID: 9cac2de51ce4
Revises: 
Create Date: 2026-08-19 15:56:19.067281

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9cac2de51ce4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discord_id", sa.BigInteger(), nullable=False),
        sa.Column("game", sa.String(length=16), nullable=False),
        sa.Column("riot_game_name", sa.String(length=32), nullable=False),
        sa.Column("riot_tagline", sa.String(length=8), nullable=False),
        sa.Column("puuid", sa.String(length=78), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("puuid"),
        sa.UniqueConstraint("discord_id", "game", name="uq_players_discord_id_game"),
    )
    op.create_index(op.f("ix_players_discord_id"), "players", ["discord_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_players_discord_id"), table_name="players")
    op.drop_table("players")
