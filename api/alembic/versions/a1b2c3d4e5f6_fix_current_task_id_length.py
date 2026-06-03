"""fix current_task_id length

Revision ID: a1b2c3d4e5f6
Revises: 63695b172b01
Create Date: 2026-04-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '63695b172b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('agents') as batch_op:
        batch_op.alter_column(
            'current_task_id',
            existing_type=sa.String(36),
            type_=sa.String(100),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('agents') as batch_op:
        batch_op.alter_column(
            'current_task_id',
            existing_type=sa.String(100),
            type_=sa.String(36),
            existing_nullable=True,
        )
