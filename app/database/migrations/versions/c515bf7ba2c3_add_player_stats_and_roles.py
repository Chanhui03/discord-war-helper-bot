"""add player stats and roles

Revision ID: c515bf7ba2c3
Revises: 9cac2de51ce4
Create Date: 2026-08-19 16:04:22.160677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c515bf7ba2c3'
down_revision: Union[str, Sequence[str], None] = '9cac2de51ce4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("main_role", sa.String(length=8), nullable=True))
    op.add_column("players", sa.Column("secondary_role", sa.String(length=8), nullable=True))

    op.create_table(
        "player_stats",
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("division", sa.String(length=4), nullable=True),
        sa.Column("lp", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("avg_kda", sa.Float(), nullable=False),
        sa.Column("recent_win_rate", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )

    op.create_table(
        "player_roles",
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("avg_kda", sa.Float(), nullable=False),
        sa.Column("role_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id", "role"),
    )


def downgrade() -> None:
    op.drop_table("player_roles")
    op.drop_table("player_stats")
    op.drop_column("players", "secondary_role")
    op.drop_column("players", "main_role")
