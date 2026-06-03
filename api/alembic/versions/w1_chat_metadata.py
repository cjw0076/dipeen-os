"""W-1: Add metadata_json and task_id to chat_messages

Revision ID: w1_chat_metadata
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa


revision = "w1_chat_metadata"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("task_id", sa.String(100), nullable=True))
    op.add_column("chat_messages", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "metadata_json")
    op.drop_column("chat_messages", "task_id")
