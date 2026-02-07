"""initial_schema

Revision ID: c3768591d42a
Revises:
Create Date: 2026-02-07 16:08:57.080002

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3768591d42a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial database schema."""
    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Authentication
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("phone", sa.String(20)),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True)),
        sa.Column("password_hash", sa.String(255)),
        # Stripe integration
        sa.Column("stripe_customer_id", sa.String(255), unique=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # Trial tracking
        sa.Column("trial_started_at", sa.DateTime(timezone=True)),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column("trial_minutes_used", sa.Numeric(10, 2), default=0),
        sa.Column("trial_minutes_limit", sa.Integer, default=10),
        # Anti-fraud tracking
        sa.Column("signup_fingerprint", sa.String(255)),
        sa.Column("signup_ip", sa.String(45)),
        sa.Column("risk_score", sa.Integer, default=0),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"])
    op.create_index("ix_users_signup_fingerprint", "users", ["signup_fingerprint"])
    op.create_index("ix_users_signup_ip", "users", ["signup_ip"])

    # Subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # Plan details
        sa.Column("plan_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        # Stripe integration
        sa.Column("stripe_subscription_id", sa.String(255)),
        sa.Column("stripe_price_id", sa.String(255)),
        # Billing period
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        # Usage tracking
        sa.Column("minutes_used", sa.Numeric(10, 2), default=0),
        sa.Column("minutes_limit", sa.Integer),
        sa.Column("allow_overage", sa.Boolean, default=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index(
        "ix_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # Usage events table
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id"),
        ),
        # Event details
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("room_name", sa.String(255)),
        # Usage metrics
        sa.Column("minutes", sa.Numeric(10, 2)),
        sa.Column("cost_cents", sa.Integer),
        sa.Column("is_overage", sa.Boolean, default=False),
        # Metadata
        sa.Column("metadata_json", sa.Text),
        # Timestamp
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index(
        "ix_usage_events_subscription_id", "usage_events", ["subscription_id"]
    )
    op.create_index("ix_usage_events_call_id", "usage_events", ["call_id"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])

    # Referral codes table
    op.create_table(
        "referral_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            unique=True,
            nullable=False,
        ),
        # Code details
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("type", sa.String(20), default="user"),
        sa.Column("commission_rate", sa.Numeric(5, 4), default=0.20),
        # Stats
        sa.Column("total_referrals", sa.Integer, default=0),
        sa.Column("total_conversions", sa.Integer, default=0),
        sa.Column("total_earnings_cents", sa.Integer, default=0),
        # Status
        sa.Column("is_active", sa.Boolean, default=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_referral_codes_code", "referral_codes", ["code"])
    op.create_index("ix_referral_codes_user_id", "referral_codes", ["user_id"])

    # Referrals table
    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "referral_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral_codes.id"),
            nullable=False,
        ),
        sa.Column(
            "referrer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "referee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        # Tracking
        sa.Column("referee_email", sa.String(255)),
        sa.Column("status", sa.String(20), default="pending"),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("signed_up_at", sa.DateTime(timezone=True)),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_referrals_referral_code_id", "referrals", ["referral_code_id"])
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])
    op.create_index("ix_referrals_referee_user_id", "referrals", ["referee_user_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])

    # Referral earnings table
    op.create_table(
        "referral_earnings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "referral_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id"),
            nullable=False,
        ),
        sa.Column(
            "referrer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # Payment details
        sa.Column("stripe_payment_id", sa.String(255)),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("commission_cents", sa.Integer, nullable=False),
        # Status
        sa.Column("status", sa.String(20), default="pending"),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_referral_earnings_referral_id", "referral_earnings", ["referral_id"]
    )
    op.create_index(
        "ix_referral_earnings_referrer_user_id",
        "referral_earnings",
        ["referrer_user_id"],
    )
    op.create_index("ix_referral_earnings_status", "referral_earnings", ["status"])

    # Referral payouts table
    op.create_table(
        "referral_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # Payout details
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        # External reference
        sa.Column("payout_reference", sa.String(255)),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_referral_payouts_user_id", "referral_payouts", ["user_id"])
    op.create_index("ix_referral_payouts_status", "referral_payouts", ["status"])


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("referral_payouts")
    op.drop_table("referral_earnings")
    op.drop_table("referrals")
    op.drop_table("referral_codes")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("users")
