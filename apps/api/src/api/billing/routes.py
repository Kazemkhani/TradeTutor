"""Billing API routes.

Provides subscription management, usage tracking, and Stripe webhook handling.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import get_current_user
from api.billing.metering import UsageMeter
from api.billing.stripe_client import (
    StripeClient,
    get_stripe_client,
    sync_subscription_from_stripe,
)
from api.db.database import get_db
from api.db.models import (
    PLAN_CONFIG,
    PlanType,
    Subscription,
    SubscriptionStatus,
    User,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


# =============================================================================
# Request/Response Models
# =============================================================================


class PlanInfo(BaseModel):
    """Information about a subscription plan."""

    id: str
    name: str
    price_cents: int | None
    price_display: str
    minutes_limit: int | None
    overage_price_cents: int | None
    features: list[str]


class PlansResponse(BaseModel):
    """Available subscription plans."""

    plans: list[PlanInfo]


class SubscribeRequest(BaseModel):
    """Request to create a subscription."""

    plan: str  # 'starter', 'growth', 'scale'
    payment_method_id: str | None = None


class SubscriptionResponse(BaseModel):
    """Subscription details response."""

    id: str
    plan: str
    status: str
    minutes_used: float
    minutes_limit: int | None
    minutes_remaining: float | None
    period_start: str | None
    period_end: str | None
    cancel_at_period_end: bool


class UsageResponse(BaseModel):
    """Current usage response."""

    plan: str | None
    status: str
    minutes_used: float
    minutes_limit: int | None
    minutes_remaining: float | None
    period_start: str | None
    period_end: str | None
    trial_ends_at: str | None = None


class SetupIntentResponse(BaseModel):
    """SetupIntent for adding payment method."""

    client_secret: str
    setup_intent_id: str


# =============================================================================
# Routes
# =============================================================================


@router.get("/plans", response_model=PlansResponse)
async def get_plans():
    """Get available subscription plans."""
    plans = [
        PlanInfo(
            id="starter",
            name="Starter",
            price_cents=PLAN_CONFIG[PlanType.STARTER]["price_cents"],
            price_display="$29/month",
            minutes_limit=PLAN_CONFIG[PlanType.STARTER]["minutes_limit"],
            overage_price_cents=PLAN_CONFIG[PlanType.STARTER]["overage_price_cents"],
            features=[
                "100 minutes per month",
                "Up to 5 leads per submission",
                "$0.20/min overage",
                "Email support",
            ],
        ),
        PlanInfo(
            id="growth",
            name="Growth",
            price_cents=PLAN_CONFIG[PlanType.GROWTH]["price_cents"],
            price_display="$99/month",
            minutes_limit=PLAN_CONFIG[PlanType.GROWTH]["minutes_limit"],
            overage_price_cents=PLAN_CONFIG[PlanType.GROWTH]["overage_price_cents"],
            features=[
                "500 minutes per month",
                "Up to 5 leads per submission",
                "$0.18/min overage",
                "Priority support",
                "Call analytics",
            ],
        ),
        PlanInfo(
            id="scale",
            name="Scale",
            price_cents=PLAN_CONFIG[PlanType.SCALE]["price_cents"],
            price_display="$299/month",
            minutes_limit=PLAN_CONFIG[PlanType.SCALE]["minutes_limit"],
            overage_price_cents=PLAN_CONFIG[PlanType.SCALE]["overage_price_cents"],
            features=[
                "2000 minutes per month",
                "Up to 5 leads per submission",
                "$0.15/min overage",
                "Dedicated support",
                "Advanced analytics",
                "Custom voice options",
            ],
        ),
    ]
    return PlansResponse(plans=plans)


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's subscription."""
    meter = UsageMeter(db)
    subscription = await meter.get_active_subscription(user.id)

    if not subscription:
        return None

    current_usage = await meter.get_period_usage(subscription.id)

    return SubscriptionResponse(
        id=str(subscription.id),
        plan=subscription.plan_id,
        status=subscription.status,
        minutes_used=float(current_usage),
        minutes_limit=subscription.minutes_limit,
        minutes_remaining=(
            float(subscription.minutes_limit - current_usage)
            if subscription.minutes_limit
            else None
        ),
        period_start=(
            subscription.current_period_start.isoformat()
            if subscription.current_period_start
            else None
        ),
        period_end=(
            subscription.current_period_end.isoformat()
            if subscription.current_period_end
            else None
        ),
        cancel_at_period_end=subscription.canceled_at is not None,
    )


@router.post("/subscribe", response_model=dict)
async def create_subscription(
    request: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """Create a new subscription.

    If user doesn't have a Stripe customer, creates one first.
    Returns client_secret for completing payment in frontend.
    """
    # Validate plan
    try:
        plan = PlanType(request.plan)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {request.plan}",
        ) from e

    if plan not in [PlanType.STARTER, PlanType.GROWTH, PlanType.SCALE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan for subscription",
        )

    # Ensure user has Stripe customer ID
    if not user.stripe_customer_id:
        customer_id = await stripe_client.create_customer(user)
        user.stripe_customer_id = customer_id
        await db.flush()

    # Create subscription
    result = await stripe_client.create_subscription(
        customer_id=user.stripe_customer_id,
        plan=plan,
        payment_method_id=request.payment_method_id,
    )

    # Create subscription record in database
    plan_config = PLAN_CONFIG[plan]
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.value,
        status=SubscriptionStatus.ACTIVE,
        stripe_subscription_id=result["subscription_id"],
        minutes_limit=plan_config["minutes_limit"],
        allow_overage=True,
    )
    db.add(subscription)
    await db.commit()

    return {
        "subscription_id": result["subscription_id"],
        "status": result["status"],
        "client_secret": result.get("client_secret"),
    }


@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """Cancel subscription at period end."""
    meter = UsageMeter(db)
    subscription = await meter.get_active_subscription(user.id)

    if not subscription or not subscription.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    # Cancel in Stripe
    result = await stripe_client.cancel_subscription(
        subscription.stripe_subscription_id
    )

    # Update database
    subscription.canceled_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "message": "Subscription will be canceled at period end",
        "cancel_at_period_end": result["cancel_at_period_end"],
    }


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current usage summary."""
    meter = UsageMeter(db)
    summary = await meter.get_usage_summary(user.id)

    return UsageResponse(
        plan=summary.get("plan"),
        status=summary.get("status", "inactive"),
        minutes_used=summary.get("minutes_used", 0),
        minutes_limit=summary.get("minutes_limit"),
        minutes_remaining=summary.get("minutes_remaining"),
        period_start=summary.get("period_start"),
        period_end=summary.get("period_end"),
        trial_ends_at=summary.get("trial_ends_at"),
    )


@router.post("/setup-intent", response_model=SetupIntentResponse)
async def create_setup_intent(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """Create a SetupIntent for adding a payment method.

    Used during trial signup to verify credit card without charging.
    """
    # Ensure user has Stripe customer ID
    if not user.stripe_customer_id:
        customer_id = await stripe_client.create_customer(user)
        user.stripe_customer_id = customer_id
        await db.commit()

    result = await stripe_client.create_setup_intent(user.stripe_customer_id)

    return SetupIntentResponse(
        client_secret=result["client_secret"],
        setup_intent_id=result["setup_intent_id"],
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """Handle Stripe webhooks.

    Processes subscription lifecycle events:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.paid
    - invoice.payment_failed
    """
    payload = await request.body()

    try:
        event = stripe_client.verify_webhook(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    # Handle subscription events
    if event_type in [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ]:
        subscription_id = data.get("id")
        customer_id = data.get("customer")

        # Find user by Stripe customer ID
        from sqlalchemy import select

        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()

        if user:
            await sync_subscription_from_stripe(db, user.id, subscription_id)
            await db.commit()

    # Handle invoice events for commission tracking
    elif event_type == "invoice.paid":
        # TODO: Track for referral commissions
        pass

    elif event_type == "invoice.payment_failed":
        # TODO: Handle payment failures (send email, update status)
        pass

    return {"received": True}
