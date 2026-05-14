"""migrate search_source to combined

Revision ID: 81cd342ab5da
Revises: a3d9f1b82c47
Create Date: 2026-05-14 16:13:44.821575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81cd342ab5da'
down_revision: Union[str, Sequence[str], None] = 'a3d9f1b82c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 단일 소스 값(semantic_scholar/openalex)을 combined로 통합.
    # downgrade 시 둘의 구분은 복원되지 않는다 — search_source는 표시·라우팅용이라 무방.
    op.execute(
        "UPDATE tech_queries SET search_source = 'combined' "
        "WHERE search_source IN ('semantic_scholar', 'openalex')"
    )
    op.alter_column(
        "tech_queries", "search_source",
        server_default="combined",
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tech_queries", "search_source",
        server_default="semantic_scholar",
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE tech_queries SET search_source = 'semantic_scholar' "
        "WHERE search_source = 'combined'"
    )
