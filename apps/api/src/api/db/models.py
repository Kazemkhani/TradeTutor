"""SQLAlchemy models for users, subscriptions, usage, and referrals.

Based on the monetization plan with anti-fraud and referral tracking.
"""

import secrets
import string
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.database import Base

if TYPE_CHECKING:
    pass


# =============================================================================
# Enums
# =============================================================================


class PlanType(str, Enum):
    """Subscription plan types."""

    TRIAL = "trial"
    STARTER = "starter"
    GROWTH = "growth"
    SCALE = "scale"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status values."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ReferralType(str, Enum):
    """Referral program types."""

    USER = "user"  # Regular user referrals (get minutes)
    AFFILIATE = "affiliate"  # Affiliate program (get commission %)


class ReferralStatus(str, Enum):
    """Referral tracking status."""

    PENDING = "pending"  # Link clicked but not signed up
    SIGNED_UP = "signed_up"  # User created account
    CONVERTED = "converted"  # User became paying customer
    CHURNED = "churned"  # User canceled


class PayoutStatus(str, Enum):
    """Payout request status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PayoutMethod(str, Enum):
    """Payout methods."""

    STRIPE = "stripe"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


# =============================================================================
# Plan Configuration
# =============================================================================

PLAN_CONFIG = {
    PlanType.TRIAL: {
        "price_cents": 0,
        "minutes_limit": 10,
        "duration_days": 7,
        "overage_price_cents": None,  # No overage allowed
    },
    PlanType.STARTER: {
        "price_cents": 2900,  # $29
        "minutes_limit": 100,
        "overage_price_cents": 20,  # $0.20/min
    },
    PlanType.GROWTH: {
        "price_cents": 9900,  # $99
        "minutes_limit": 500,
        "overage_price_cents": 18,  # $0.18/min
    },
    PlanType.SCALE: {
        "price_cents": 29900,  # $299
        "minutes_limit": 2000,
        "overage_price_cents": 15,  # $0.15/min
    },
    PlanType.ENTERPRISE: {
        "price_cents": None,  # Custom pricing
        "minutes_limit": None,  # Unlimited
        "overage_price_cents": None,
    },
}


# =============================================================================
# User Model
# =============================================================================


class User(Base):
    """User account with authentication and anti-fraud tracking."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Authentication
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(String(20))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # Stripe integration
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Trial tracking
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_minutes_used: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )
    trial_minutes_limit: Mapped[int] = mapped_column(Integer, default=10)

    # Anti-fraud tracking
    signup_fingerprint: Mapped[str | None] = mapped_column(String(255))
    signup_ip: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length
    risk_score: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    usage_events: Mapped[list["UsageEvent"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    referral_code: Mapped["ReferralCode | None"] = relationship(
        back_populates="user", lazy="selectin"
    )
    referrals_made: Mapped[list["Referral"]] = relationship(
        foreign_keys="[Referral.referrer_user_id]",
        back_populates="referrer",
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_stripe_customer_id", "stripe_customer_id"),
        Index("ix_users_signup_fingerprint", "signup_fingerprint"),
        Index("ix_users_signup_ip", "signup_ip"),
    )

    @property
    def is_email_verified(self) -> bool:
        """Check if email is verified."""
        return self.email_verified_at is not None

    @property
    def is_phone_verified(self) -> bool:
        """Check if phone is verified."""
        return self.phone_verified_at is not None

    @property
    def is_trial_active(self) -> bool:
        """Check if trial is still active."""
        if not self.trial_ends_at:
            return False
        return datetime.now(timezone.utc) < self.trial_ends_at

    @property
    def trial_minutes_remaining(self) -> Decimal:
        """Get remaining trial minutes."""
        return max(Decimal("0"), self.trial_minutes_limit - self.trial_minutes_used)

    def start_trial(self, days: int = 7, minutes: int = 10) -> None:
        """Start the trial period."""
        now = datetime.now(timezone.utc)
        self.trial_started_at = now
        self.trial_ends_at = now + timedelta(days=days)
        self.trial_minutes_limit = minutes
        self.trial_minutes_used = Decimal("0")


# =============================================================================
# Subscription Model
# =============================================================================


class Subscription(Base):
    """User subscription with plan and usage tracking."""

    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Plan details
    plan_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Stripe integration
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))

    # Billing period
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Usage tracking
    minutes_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    minutes_limit: Mapped[int | None] = mapped_column(Integer)
    allow_overage: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")
    usage_events: Mapped[list["UsageEvent"]] = relationship(
        back_populates="subscription", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_subscriptions_user_id", "user_id"),
        Index("ix_subscriptions_stripe_subscription_id", "stripe_subscription_id"),
        Index("ix_subscriptions_status", "status"),
    )

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)

    @property
    def minutes_remaining(self) -> Decimal | None:
        """Get remaining minutes in current period."""
        if self.minutes_limit is None:
            return None  # Unlimited
        return max(Decimal("0"), Decimal(self.minutes_limit) - self.minutes_used)

    @property
    def is_over_limit(self) -> bool:
        """Check if usage exceeds limit."""
        if self.minutes_limit is None:
            return False
        return self.minutes_used >= self.minutes_limit


# =============================================================================
# Usage Event Model
# =============================================================================


class UsageEvent(Base):
    """Track call usage for billing and analytics."""

    __tablename__ = "usage_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id")
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # call_initiated, call_minute, call_completed
    call_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    room_name: Mapped[str | None] = mapped_column(String(255))

    # Usage metrics
    minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    is_overage: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    metadata_json: Mapped[str | None] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="usage_events")
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="usage_events"
    )

    __table_args__ = (
        Index("ix_usage_events_user_id", "user_id"),
        Index("ix_usage_events_subscription_id", "subscription_id"),
        Index("ix_usage_events_call_id", "call_id"),
        Index("ix_usage_events_created_at", "created_at"),
    )


# =============================================================================
# Referral Models
# =============================================================================


def generate_referral_code(length: int = 8) -> str:
    """Generate a unique referral code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


class ReferralCode(Base):
    """User's referral code for tracking referrals."""

    __tablename__ = "referral_codes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )

    # Code details
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, default=generate_referral_code
    )
    type: Mapped[str] = mapped_column(String(20), default=ReferralType.USER)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.20")
    )  # 20%

    # Stats
    total_referrals: Mapped[int] = mapped_column(Integer, default=0)
    total_conversions: Mapped[int] = mapped_column(Integer, default=0)
    total_earnings_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="referral_code")
    referrals: Mapped[list["Referral"]] = relationship(
        back_populates="referral_code", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_referral_codes_code", "code"),
        Index("ix_referral_codes_user_id", "user_id"),
    )


class Referral(Base):
    """Track individual referral from referrer to referee."""

    __tablename__ = "referrals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    referral_code_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("referral_codes.id"), nullable=False
    )
    referrer_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    referee_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )

    # Tracking
    referee_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=ReferralStatus.PENDING)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    signed_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    referral_code: Mapped["ReferralCode"] = relationship(back_populates="referrals")
    referrer: Mapped["User"] = relationship(
        foreign_keys=[referrer_user_id], back_populates="referrals_made"
    )
    earnings: Mapped[list["ReferralEarning"]] = relationship(
        back_populates="referral", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_referrals_referral_code_id", "referral_code_id"),
        Index("ix_referrals_referrer_user_id", "referrer_user_id"),
        Index("ix_referrals_referee_user_id", "referee_user_id"),
        Index("ix_referrals_status", "status"),
    )


class ReferralEarning(Base):
    """Track earnings from a referred customer's payments."""

    __tablename__ = "referral_earnings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    referral_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("referrals.id"), nullable=False
    )
    referrer_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Payment details
    stripe_payment_id: Mapped[str | None] = mapped_column(String(255))
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    referral: Mapped["Referral"] = relationship(back_populates="earnings")

    __table_args__ = (
        Index("ix_referral_earnings_referral_id", "referral_id"),
        Index("ix_referral_earnings_referrer_user_id", "referrer_user_id"),
        Index("ix_referral_earnings_status", "status"),
    )


class ReferralPayout(Base):
    """Track payout requests from affiliates."""

    __tablename__ = "referral_payouts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Payout details
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PayoutStatus.PENDING)

    # External reference (Stripe payout ID, PayPal transaction, etc.)
    payout_reference: Mapped[str | None] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_referral_payouts_user_id", "user_id"),
        Index("ix_referral_payouts_status", "status"),
    )
