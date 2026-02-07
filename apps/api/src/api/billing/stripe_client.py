"""Stripe integration for subscription management.

Handles customer creation, subscription lifecycle, and payment methods.
"""

import os
from dataclasses import dataclass
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import PLAN_CONFIG, PlanType, Subscription, SubscriptionStatus, User


@dataclass
class StripeConfig:
    """Stripe configuration from environment."""

    api_key: str
    webhook_secret: str
    starter_price_id: str
    growth_price_id: str
    scale_price_id: str

    @classmethod
    def from_env(cls) -> "StripeConfig":
        """Load Stripe config from environment variables."""
        return cls(
            api_key=os.getenv("STRIPE_SECRET_KEY", ""),
            webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
            starter_price_id=os.getenv("STRIPE_STARTER_PRICE_ID", ""),
            growth_price_id=os.getenv("STRIPE_GROWTH_PRICE_ID", ""),
            scale_price_id=os.getenv("STRIPE_SCALE_PRICE_ID", ""),
        )

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return bool(self.api_key)


class StripeClient:
    """Stripe API client for subscription management."""

    def __init__(self, config: StripeConfig | None = None):
        """Initialize Stripe client.

        Args:
            config: Stripe configuration. Loads from env if not provided.
        """
        self.config = config or StripeConfig.from_env()
        if self.config.is_configured():
            stripe.api_key = self.config.api_key

    def get_price_id(self, plan: PlanType) -> str | None:
        """Get Stripe price ID for a plan."""
        price_map = {
            PlanType.STARTER: self.config.starter_price_id,
            PlanType.GROWTH: self.config.growth_price_id,
            PlanType.SCALE: self.config.scale_price_id,
        }
        return price_map.get(plan)

    async def create_customer(self, user: User) -> str:
        """Create a Stripe customer for a user.

        Args:
            user: The user to create a customer for.

        Returns:
            Stripe customer ID.
        """
        customer = stripe.Customer.create(
            email=user.email,
            metadata={
                "user_id": str(user.id),
            },
        )
        return customer.id

    async def create_setup_intent(self, customer_id: str) -> dict:
        """Create a SetupIntent for adding a payment method.

        Used for credit card verification during trial signup.

        Args:
            customer_id: Stripe customer ID.

        Returns:
            SetupIntent details including client_secret.
        """
        intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=["card"],
        )
        return {
            "client_secret": intent.client_secret,
            "setup_intent_id": intent.id,
        }

    async def create_subscription(
        self,
        customer_id: str,
        plan: PlanType,
        payment_method_id: str | None = None,
    ) -> dict:
        """Create a subscription for a customer.

        Args:
            customer_id: Stripe customer ID.
            plan: The plan to subscribe to.
            payment_method_id: Optional payment method to use.

        Returns:
            Subscription details.
        """
        price_id = self.get_price_id(plan)
        if not price_id:
            raise ValueError(f"No price ID configured for plan: {plan}")

        params: dict = {
            "customer": customer_id,
            "items": [{"price": price_id}],
            "payment_behavior": "default_incomplete",
            "expand": ["latest_invoice.payment_intent"],
        }

        if payment_method_id:
            params["default_payment_method"] = payment_method_id

        subscription = stripe.Subscription.create(**params)

        return {
            "subscription_id": subscription.id,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "client_secret": (
                subscription.latest_invoice.payment_intent.client_secret
                if subscription.latest_invoice
                and subscription.latest_invoice.payment_intent
                else None
            ),
        }

    async def cancel_subscription(self, subscription_id: str) -> dict:
        """Cancel a subscription at period end.

        Args:
            subscription_id: Stripe subscription ID.

        Returns:
            Updated subscription details.
        """
        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        )
        return {
            "subscription_id": subscription.id,
            "status": subscription.status,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    async def get_subscription(self, subscription_id: str) -> dict | None:
        """Get subscription details.

        Args:
            subscription_id: Stripe subscription ID.

        Returns:
            Subscription details or None if not found.
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "plan": subscription.items.data[0].price.id
                if subscription.items.data
                else None,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        except stripe.InvalidRequestError:
            return None

    async def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: int | None = None,
    ) -> dict:
        """Report usage for metered billing.

        Args:
            subscription_item_id: Stripe subscription item ID.
            quantity: Usage quantity (e.g., minutes).
            timestamp: Unix timestamp for the usage (defaults to now).

        Returns:
            Usage record details.
        """
        params: dict = {
            "quantity": quantity,
            "action": "increment",
        }
        if timestamp:
            params["timestamp"] = timestamp

        record = stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            **params,
        )
        return {
            "id": record.id,
            "quantity": record.quantity,
            "timestamp": record.timestamp,
        }

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        """Verify and parse a Stripe webhook.

        Args:
            payload: Raw request body.
            signature: Stripe-Signature header.

        Returns:
            Parsed webhook event.

        Raises:
            ValueError: If signature verification fails.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.config.webhook_secret,
            )
            return dict(event)
        except stripe.SignatureVerificationError as e:
            raise ValueError(f"Invalid webhook signature: {e}") from e


# Singleton instance
_stripe_client: StripeClient | None = None


def get_stripe_client() -> StripeClient:
    """Get the Stripe client singleton."""
    global _stripe_client
    if _stripe_client is None:
        _stripe_client = StripeClient()
    return _stripe_client


async def sync_subscription_from_stripe(
    db: AsyncSession,
    user_id: UUID,
    stripe_subscription_id: str,
) -> Subscription:
    """Sync subscription data from Stripe to database.

    Args:
        db: Database session.
        user_id: User's UUID.
        stripe_subscription_id: Stripe subscription ID.

    Returns:
        Updated or created Subscription model.
    """
    client = get_stripe_client()
    stripe_sub = await client.get_subscription(stripe_subscription_id)

    if not stripe_sub:
        raise ValueError(f"Subscription not found: {stripe_subscription_id}")

    # Find or create subscription in database
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    # Map Stripe status to our status
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELED,
        "trialing": SubscriptionStatus.TRIALING,
    }

    if subscription is None:
        # Determine plan from price ID
        price_id = stripe_sub.get("plan")
        plan_id = "starter"  # Default
        for plan in [PlanType.STARTER, PlanType.GROWTH, PlanType.SCALE]:
            if client.get_price_id(plan) == price_id:
                plan_id = plan.value
                break

        plan_config = PLAN_CONFIG.get(PlanType(plan_id), {})

        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status=status_map.get(stripe_sub["status"], SubscriptionStatus.ACTIVE),
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=price_id,
            minutes_limit=plan_config.get("minutes_limit"),
            allow_overage=True,
        )
        db.add(subscription)
    else:
        subscription.status = status_map.get(stripe_sub["status"], subscription.status)

    await db.flush()
    return subscription
