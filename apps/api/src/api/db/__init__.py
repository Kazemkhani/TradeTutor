"""Database module for the API.

Provides SQLAlchemy models, async database session management, and utilities.
"""

from api.db.database import (
    Base,
    get_db,
    init_db,
)
from api.db.models import (
    Referral,
    ReferralCode,
    ReferralEarning,
    ReferralPayout,
    Subscription,
    UsageEvent,
    User,
)

__all__ = [
    "Base",
    "Referral",
    "ReferralCode",
    "ReferralEarning",
    "ReferralPayout",
    "Subscription",
    "UsageEvent",
    "User",
    "get_db",
    "init_db",
]
