"""add extraction_hint to indicators

Revision ID: 0104a9e516ee
Revises: 81cd342ab5da
Create Date: 2026-05-15 15:20:38.225914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0104a9e516ee'
down_revision: Union[str, Sequence[str], None] = '81cd342ab5da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 행은 NULL 유지 — 백필 없음.
    # extraction_hint는 LLM 단서이므로 영구 보존 의무 없는 메타성격 데이터.
    op.add_column(
        "indicators",
        sa.Column("extraction_hint", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    # downgrade 시 extraction_hint 데이터는 손실된다 (메타성격이라 무방).
    op.drop_column("indicators", "extraction_hint")
