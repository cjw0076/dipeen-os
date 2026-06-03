"""F-3: Add token quota fields to agents

Revision ID: f3_agent_quota
Revises: w1_chat_metadata
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa


revision = "f3_agent_quota"
down_revision = "w1_chat_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("monthly_token_budget", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("tokens_used_this_month", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("agents", "tokens_used_this_month")
    op.drop_column("agents", "monthly_token_budget")
