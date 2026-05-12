"""add journal_name to metric_values

Revision ID: a3d9f1b82c47
Revises: f61742926283
Create Date: 2026-05-12 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3d9f1b82c47'
down_revision: Union[str, Sequence[str], None] = 'f61742926283'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('metric_values', sa.Column('journal_name', sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column('metric_values', 'journal_name')
