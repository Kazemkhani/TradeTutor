"""Usage metering and limit enforcement.

Tracks call minutes and enforces subscription limits.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import (
    PLAN_CONFIG,
    PlanType,
    Subscription,
    SubscriptionStatus,
    UsageEvent,
    User,
)


class UsageMeter:
    """Tracks and enforces usage limits."""

    def __init__(self, db: AsyncSession):
        """Initialize the usage meter.

        Args:
            db: Async database session.
        """
        self.db = db

    async def get_active_subscription(self, user_id: UUID) -> Subscription | None:
        """Get the user's active subscription.

        Args:
            user_id: User's UUID.

        Returns:
            Active subscription or None.
        """
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
                )
            )
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_period_usage(self, subscription_id: UUID) -> Decimal:
        """Get total minutes used in current billing period.

        Args:
            subscription_id: Subscription UUID.

        Returns:
            Total minutes used.
        """
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return Decimal("0")

        # Get usage events in current period
        usage_result = await self.db.execute(
            select(func.sum(UsageEvent.minutes))
            .where(UsageEvent.subscription_id == subscription_id)
            .where(UsageEvent.created_at >= subscription.current_period_start)
        )
        total = usage_result.scalar()
        return Decimal(str(total or 0))

    async def check_can_make_call(
        self,
        user_id: UUID,
        estimated_minutes: Decimal = Decimal("5"),
    ) -> tuple[bool, str | None]:
        """Check if user can make a call.

        Args:
            user_id: User's UUID.
            estimated_minutes: Estimated call duration in minutes.

        Returns:
            Tuple of (can_make_call, error_message).
        """
        # Get user for trial check
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return False, "User not found"

        # Get active subscription
        subscription = await self.get_active_subscription(user_id)

        if subscription is None:
            # Check if in trial
            if user.is_trial_active:
                if user.trial_minutes_remaining < estimated_minutes:
                    return (
                        False,
                        "Trial minutes exhausted. Please subscribe to continue.",
                    )
                return True, None
            return False, "No active subscription. Please subscribe to make calls."

        # Check subscription limits
        if subscription.minutes_limit is not None:
            current_usage = await self.get_period_usage(subscription.id)
            remaining = Decimal(subscription.minutes_limit) - current_usage

            if remaining < estimated_minutes:
                if subscription.allow_overage:
                    return True, None  # Overage allowed
                return (
                    False,
                    f"Monthly limit reached ({subscription.minutes_limit} minutes). Upgrade to continue.",
                )

        return True, None

    async def record_call_start(
        self,
        user_id: UUID,
        call_id: UUID,
        room_name: str | None = None,
    ) -> UsageEvent:
        """Record that a call has started.

        Args:
            user_id: User's UUID.
            call_id: Call UUID.
            room_name: LiveKit room name.

        Returns:
            Created UsageEvent.
        """
        subscription = await self.get_active_subscription(user_id)

        event = UsageEvent(
            user_id=user_id,
            subscription_id=subscription.id if subscription else None,
            event_type="call_initiated",
            call_id=call_id,
            room_name=room_name,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def record_call_usage(
        self,
        user_id: UUID,
        call_id: UUID,
        minutes: Decimal,
    ) -> UsageEvent:
        """Record call minutes used.

        Args:
            user_id: User's UUID.
            call_id: Call UUID.
            minutes: Minutes used.

        Returns:
            Created UsageEvent.
        """
        # Get user and subscription
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        subscription = await self.get_active_subscription(user_id)

        # Calculate cost
        cost_cents = 0
        is_overage = False

        if subscription and subscription.minutes_limit:
            current_usage = await self.get_period_usage(subscription.id)
            remaining = Decimal(subscription.minutes_limit) - current_usage

            if minutes > remaining:
                is_overage = True
                # Get overage price from plan config
                plan_config = PLAN_CONFIG.get(PlanType(subscription.plan_id), {})
                overage_price = plan_config.get("overage_price_cents", 20)
                overage_minutes = minutes - max(Decimal("0"), remaining)
                cost_cents = int(overage_minutes * overage_price)

        event = UsageEvent(
            user_id=user_id,
            subscription_id=subscription.id if subscription else None,
            event_type="call_completed",
            call_id=call_id,
            minutes=minutes,
            cost_cents=cost_cents,
            is_overage=is_overage,
        )
        self.db.add(event)

        # Update subscription usage
        if subscription:
            subscription.minutes_used += minutes

        # Update trial usage if applicable
        if user and user.is_trial_active and not subscription:
            user.trial_minutes_used += minutes

        await self.db.flush()
        return event

    async def get_usage_summary(self, user_id: UUID) -> dict:
        """Get usage summary for a user.

        Args:
            user_id: User's UUID.

        Returns:
            Usage summary dict.
        """
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return {"error": "User not found"}

        subscription = await self.get_active_subscription(user_id)

        if subscription:
            current_usage = await self.get_period_usage(subscription.id)
            return {
                "plan": subscription.plan_id,
                "status": subscription.status,
                "minutes_used": float(current_usage),
                "minutes_limit": subscription.minutes_limit,
                "minutes_remaining": (
                    float(Decimal(subscription.minutes_limit) - current_usage)
                    if subscription.minutes_limit
                    else None
                ),
                "allow_overage": subscription.allow_overage,
                "period_start": (
                    subscription.current_period_start.isoformat()
                    if subscription.current_period_start
                    else None
                ),
                "period_end": (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
            }

        # Return trial usage if no subscription
        if user.is_trial_active:
            return {
                "plan": "trial",
                "status": "trialing",
                "minutes_used": float(user.trial_minutes_used),
                "minutes_limit": user.trial_minutes_limit,
                "minutes_remaining": float(user.trial_minutes_remaining),
                "trial_ends_at": (
                    user.trial_ends_at.isoformat() if user.trial_ends_at else None
                ),
            }

        return {
            "plan": None,
            "status": "inactive",
            "minutes_used": 0,
            "minutes_limit": 0,
            "minutes_remaining": 0,
        }


# Dependency injection helper
async def get_usage_meter(db: AsyncSession) -> UsageMeter:
    """Get a UsageMeter instance."""
    return UsageMeter(db)
