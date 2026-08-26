"""add player traits

Revision ID: d5a91c7fe310
Revises: b73d1c40e9a2
Create Date: 2026-08-26 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a91c7fe310'
down_revision: Union[str, Sequence[str], None] = 'b73d1c40e9a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_traits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("rater_discord_id", sa.BigInteger(), nullable=False),
        sa.Column("trait", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["target_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_id", "rater_discord_id", "trait", name="uq_player_traits_rater"
        ),
    )


def downgrade() -> None:
    op.drop_table("player_traits")
