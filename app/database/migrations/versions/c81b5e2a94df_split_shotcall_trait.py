"""split shotcall trait into main call and follow

Revision ID: c81b5e2a94df
Revises: a92c4f5d17be
Create Date: 2026-08-27 15:41:07.552910

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c81b5e2a94df'
down_revision: Union[str, Sequence[str], None] = 'a92c4f5d17be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 '오더능력' 표는 메인오더로 옮긴다. 셋 중 뜻이 가장 가깝다.
    # 오더수행(FOLLOW)은 새로 매겨야 하므로 옮길 표가 없다.
    op.execute("UPDATE player_traits SET trait = 'MAIN_CALL' WHERE trait = 'SHOTCALL'")


def downgrade() -> None:
    op.execute("UPDATE player_traits SET trait = 'SHOTCALL' WHERE trait = 'MAIN_CALL'")
    op.execute("DELETE FROM player_traits WHERE trait = 'FOLLOW'")
