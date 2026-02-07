"""Risk scoring system for anti-fraud protection.

Calculates a risk score (0-100) based on multiple signals.
Higher scores indicate higher fraud risk.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import User
from api.security.email_validator import is_disposable_email, is_free_email


@dataclass
class SignupData:
    """Data collected during signup for risk analysis."""

    email: str
    ip: str | None = None
    fingerprint: str | None = None
    phone: str | None = None
    phone_verified: bool = False
    user_agent: str | None = None
    referrer: str | None = None


@dataclass
class RiskFactors:
    """Individual risk factors with scores."""

    disposable_email: int = 0
    free_email: int = 0
    device_reuse: int = 0
    ip_velocity: int = 0
    no_phone: int = 0
    suspicious_ua: int = 0
    vpn_detected: int = 0

    def total(self) -> int:
        """Calculate total risk score."""
        return min(
            100,
            self.disposable_email
            + self.free_email
            + self.device_reuse
            + self.ip_velocity
            + self.no_phone
            + self.suspicious_ua
            + self.vpn_detected,
        )


class RiskScorer:
    """Calculates risk scores for signup attempts."""

    # Risk thresholds
    SCORE_DISPOSABLE_EMAIL = 40
    SCORE_FREE_EMAIL = 5
    SCORE_DEVICE_REUSE = 30
    SCORE_IP_VELOCITY = 20
    SCORE_NO_PHONE = 10
    SCORE_SUSPICIOUS_UA = 15
    SCORE_VPN = 25

    # Action thresholds
    THRESHOLD_NORMAL = 20  # 0-20: Normal signup
    THRESHOLD_REQUIRE_PHONE = 40  # 21-40: Require phone verification
    THRESHOLD_MANUAL_REVIEW = 60  # 41-60: Require phone + manual review
    # 61+: Block signup

    def __init__(self, db: AsyncSession):
        """Initialize the risk scorer.

        Args:
            db: Async database session.
        """
        self.db = db

    async def calculate(self, data: SignupData) -> tuple[int, RiskFactors]:
        """Calculate risk score for a signup attempt.

        Args:
            data: Signup data to analyze.

        Returns:
            Tuple of (total_score, individual_factors).
        """
        factors = RiskFactors()

        # Check email
        if is_disposable_email(data.email):
            factors.disposable_email = self.SCORE_DISPOSABLE_EMAIL
        elif is_free_email(data.email):
            factors.free_email = self.SCORE_FREE_EMAIL

        # Check device fingerprint
        if data.fingerprint:
            device_count = await self._count_accounts_by_fingerprint(data.fingerprint)
            if device_count >= 2:
                factors.device_reuse = self.SCORE_DEVICE_REUSE

        # Check IP velocity (signups from same IP in last hour)
        if data.ip:
            ip_signups = await self._count_recent_signups_by_ip(data.ip)
            if ip_signups >= 3:
                factors.ip_velocity = self.SCORE_IP_VELOCITY

        # Check phone verification
        if not data.phone_verified:
            factors.no_phone = self.SCORE_NO_PHONE

        # Check for suspicious user agents
        if data.user_agent and self._is_suspicious_user_agent(data.user_agent):
            factors.suspicious_ua = self.SCORE_SUSPICIOUS_UA

        return factors.total(), factors

    async def _count_accounts_by_fingerprint(self, fingerprint: str) -> int:
        """Count accounts with the same device fingerprint."""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.signup_fingerprint == fingerprint)
        )
        return result.scalar() or 0

    async def _count_recent_signups_by_ip(self, ip: str, hours: int = 1) -> int:
        """Count signups from the same IP in the last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(func.count(User.id))
            .where(User.signup_ip == ip)
            .where(User.created_at >= cutoff)
        )
        return result.scalar() or 0

    def _is_suspicious_user_agent(self, ua: str) -> bool:
        """Check if user agent looks suspicious."""
        ua_lower = ua.lower()

        # Bot/scraper indicators
        suspicious_patterns = [
            "bot",
            "crawler",
            "spider",
            "scrape",
            "headless",
            "phantom",
            "selenium",
            "puppeteer",
            "playwright",
            "curl",
            "wget",
            "python-requests",
            "httpx",
            "axios",
        ]

        return any(pattern in ua_lower for pattern in suspicious_patterns)

    def get_action(self, score: int) -> str:
        """Determine action based on risk score.

        Returns:
            One of: 'allow', 'require_phone', 'manual_review', 'block'
        """
        if score <= self.THRESHOLD_NORMAL:
            return "allow"
        elif score <= self.THRESHOLD_REQUIRE_PHONE:
            return "require_phone"
        elif score <= self.THRESHOLD_MANUAL_REVIEW:
            return "manual_review"
        else:
            return "block"


async def calculate_risk_score(
    db: AsyncSession,
    data: SignupData,
) -> tuple[int, str, RiskFactors]:
    """Calculate risk score and recommended action.

    Args:
        db: Async database session.
        data: Signup data to analyze.

    Returns:
        Tuple of (score, action, factors).
    """
    scorer = RiskScorer(db)
    score, factors = await scorer.calculate(data)
    action = scorer.get_action(score)
    return score, action, factors
