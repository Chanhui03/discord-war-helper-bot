"""add recent games

Revision ID: a92c4f5d17be
Revises: f3a7d21e9b40
Create Date: 2026-08-27 15:02:41.882014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a92c4f5d17be'
down_revision: Union[str, Sequence[str], None] = 'f3a7d21e9b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "player_stats",
        sa.Column("recent_games", sa.Integer(), nullable=False, server_default="0"),
    )
    # 기존 행은 최근 20경기를 집계해 채운 값이다. 0 으로 두면 다음 갱신 전까지
    # 최근 폼과 KDA 가 통째로 '모름' 처리되어 점수가 조용히 달라진다.
    op.execute("UPDATE player_stats SET recent_games = 20 WHERE avg_kda > 0")


def downgrade() -> None:
    op.drop_column("player_stats", "recent_games")
