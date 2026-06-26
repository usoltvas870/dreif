"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("telegram_id", sa.BigInteger, unique=True, nullable=False),
        sa.Column("subscription_status", sa.String(20), nullable=False, server_default="trial"),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("subscription_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("web_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("web_session_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pd_consent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source", sa.String(255), nullable=True),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "sessions_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("state_before", JSON, nullable=True),
        sa.Column("state_after", JSON, nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sessions_log_user_id", "sessions_log", ["user_id"])

    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("yukassa_payment_id", sa.String(255), unique=True, nullable=False),
        sa.Column("amount_kopecks", sa.Integer, nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_yukassa_payment_id", "payments", ["yukassa_payment_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("sessions_log")
    op.drop_table("users")
