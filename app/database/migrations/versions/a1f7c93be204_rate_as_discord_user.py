"""rate as discord user

Revision ID: a1f7c93be204
Revises: 253623086f94
Create Date: 2026-08-24 21:02:11.480915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f7c93be204'
down_revision: Union[str, Sequence[str], None] = '253623086f94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """평가자를 player 에서 Discord 사용자로 옮긴다. 관전자는 player 행이 없다."""
    op.add_column(
        "match_ratings", sa.Column("rater_discord_id", sa.BigInteger(), nullable=True)
    )
    op.execute(
        "UPDATE match_ratings SET rater_discord_id = "
        "(SELECT discord_id FROM players WHERE players.id = match_ratings.rater_id)"
    )
    # 평가자의 계정이 이미 지워졌다면 옮길 값이 없다.
    op.execute("DELETE FROM match_ratings WHERE rater_discord_id IS NULL")

    with op.batch_alter_table("match_ratings") as batch:
        batch.drop_constraint("uq_match_ratings_rater_target", type_="unique")
        batch.drop_column("rater_id")
        batch.alter_column("rater_discord_id", nullable=False)
        batch.create_unique_constraint(
            "uq_match_ratings_rater_target",
            ["match_id", "rater_discord_id", "target_id"],
        )


def downgrade() -> None:
    op.add_column("match_ratings", sa.Column("rater_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE match_ratings SET rater_id = "
        "(SELECT id FROM players WHERE players.discord_id = "
        "match_ratings.rater_discord_id)"
    )
    op.execute("DELETE FROM match_ratings WHERE rater_id IS NULL")

    with op.batch_alter_table("match_ratings") as batch:
        batch.drop_constraint("uq_match_ratings_rater_target", type_="unique")
        batch.drop_column("rater_discord_id")
        batch.alter_column("rater_id", nullable=False)
        batch.create_foreign_key(
            "fk_match_ratings_rater_id", "players", ["rater_id"], ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint(
            "uq_match_ratings_rater_target", ["match_id", "rater_id", "target_id"]
        )
