"""Security and anti-fraud module.

Provides multi-layer protection against abuse:
- Cloudflare Turnstile verification
- Email domain validation
- Device fingerprint tracking
- IP reputation checking
- Risk scoring
"""

from api.security.email_validator import (
    is_disposable_email,
    is_free_email,
    validate_email_domain,
)
from api.security.risk_scoring import RiskScorer, calculate_risk_score
from api.security.turnstile import verify_turnstile

__all__ = [
    "RiskScorer",
    "calculate_risk_score",
    "is_disposable_email",
    "is_free_email",
    "validate_email_domain",
    "verify_turnstile",
]
