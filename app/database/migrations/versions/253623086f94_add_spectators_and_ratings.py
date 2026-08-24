"""add spectators and ratings

Revision ID: 253623086f94
Revises: cbc82a5467e7
Create Date: 2026-08-24 20:35:47.294214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '253623086f94'
down_revision: Union[str, Sequence[str], None] = 'cbc82a5467e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_spectators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("discord_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "discord_id", name="uq_match_spectators_user"),
    )
    op.create_index(
        op.f("ix_match_spectators_match_id"), "match_spectators", ["match_id"]
    )

    op.create_table(
        "match_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("rater_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rater_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id", "rater_id", "target_id", name="uq_match_ratings_rater_target"
        ),
    )
    op.create_index(op.f("ix_match_ratings_match_id"), "match_ratings", ["match_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_match_ratings_match_id"), table_name="match_ratings")
    op.drop_table("match_ratings")
    op.drop_index(op.f("ix_match_spectators_match_id"), table_name="match_spectators")
    op.drop_table("match_spectators")
