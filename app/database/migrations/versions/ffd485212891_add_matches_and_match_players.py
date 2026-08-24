"""add matches and match players

Revision ID: ffd485212891
Revises: c515bf7ba2c3
Create Date: 2026-08-19 16:08:50.332778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffd485212891'
down_revision: Union[str, Sequence[str], None] = 'c515bf7ba2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discord_server_id", sa.BigInteger(), nullable=False),
        sa.Column("game_type", sa.String(length=16), nullable=False),
        sa.Column("team_a_score", sa.Integer(), nullable=False),
        sa.Column("team_b_score", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_matches_discord_server_id"), "matches", ["discord_server_id"]
    )

    op.create_table(
        "match_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=1), nullable=True),
        sa.Column("role", sa.String(length=8), nullable=True),
        sa.Column("win", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("cs", sa.Integer(), nullable=True),
        sa.Column("damage", sa.Integer(), nullable=True),
        sa.Column("gold", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id", "player_id", name="uq_match_players_match_player"
        ),
    )
    op.create_index(op.f("ix_match_players_match_id"), "match_players", ["match_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_match_players_match_id"), table_name="match_players")
    op.drop_table("match_players")
    op.drop_index(op.f("ix_matches_discord_server_id"), table_name="matches")
    op.drop_table("matches")
