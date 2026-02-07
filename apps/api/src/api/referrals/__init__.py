"""Referral program module.

Provides referral tracking, commission calculation, and payout management.
"""

from api.referrals.routes import router as referrals_router

__all__ = [
    "referrals_router",
]
