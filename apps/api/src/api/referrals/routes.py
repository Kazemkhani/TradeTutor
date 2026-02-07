"""Referral program API routes.

Provides referral code management, stats tracking, and payout requests.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import get_current_user
from api.db.database import get_db
from api.db.models import (
    PayoutMethod,
    PayoutStatus,
    Referral,
    ReferralCode,
    ReferralEarning,
    ReferralPayout,
    ReferralStatus,
    User,
)

router = APIRouter(prefix="/referrals", tags=["Referrals"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ReferralCodeResponse(BaseModel):
    """Referral code details."""

    code: str
    type: str
    commission_rate: float
    referral_link: str
    is_active: bool


class ReferralStatsResponse(BaseModel):
    """Referral program statistics."""

    total_referrals: int
    pending_signups: int
    converted: int
    total_earnings_cents: int
    pending_earnings_cents: int
    available_balance_cents: int


class ReferralListItem(BaseModel):
    """Individual referral in list."""

    referee_email: str | None
    status: str
    signed_up_at: str | None
    converted_at: str | None
    earnings_cents: int


class ReferralsListResponse(BaseModel):
    """List of referrals."""

    referrals: list[ReferralListItem]
    total: int


class EarningsListItem(BaseModel):
    """Individual earning record."""

    referral_email: str | None
    amount_cents: int
    commission_cents: int
    status: str
    created_at: str


class EarningsListResponse(BaseModel):
    """List of earnings."""

    earnings: list[EarningsListItem]
    total: int
    total_cents: int


class PayoutRequest(BaseModel):
    """Request for payout."""

    amount_cents: int
    method: str  # 'stripe', 'paypal', 'bank_transfer'


class PayoutResponse(BaseModel):
    """Payout request response."""

    id: str
    amount_cents: int
    method: str
    status: str
    created_at: str


# =============================================================================
# Routes
# =============================================================================


@router.get("/code", response_model=ReferralCodeResponse)
async def get_referral_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's referral code.

    Creates one if it doesn't exist.
    """
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == user.id)
    )
    referral_code = result.scalar_one_or_none()

    if not referral_code:
        # Create referral code
        referral_code = ReferralCode(user_id=user.id)
        db.add(referral_code)
        await db.commit()
        await db.refresh(referral_code)

    # Build referral link
    base_url = "https://voiceagent.ai"  # TODO: Get from config
    referral_link = f"{base_url}/signup?ref={referral_code.code}"

    return ReferralCodeResponse(
        code=referral_code.code,
        type=referral_code.type,
        commission_rate=float(referral_code.commission_rate),
        referral_link=referral_link,
        is_active=referral_code.is_active,
    )


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get referral program statistics."""
    # Get referral code
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == user.id)
    )
    referral_code = result.scalar_one_or_none()

    if not referral_code:
        return ReferralStatsResponse(
            total_referrals=0,
            pending_signups=0,
            converted=0,
            total_earnings_cents=0,
            pending_earnings_cents=0,
            available_balance_cents=0,
        )

    # Count referrals by status
    referrals_result = await db.execute(
        select(Referral.status, func.count(Referral.id))
        .where(Referral.referral_code_id == referral_code.id)
        .group_by(Referral.status)
    )
    status_counts = dict(referrals_result.all())

    # Calculate earnings
    total_earnings_result = await db.execute(
        select(func.sum(ReferralEarning.commission_cents)).where(
            ReferralEarning.referrer_user_id == user.id
        )
    )
    total_earnings = total_earnings_result.scalar() or 0

    pending_earnings_result = await db.execute(
        select(func.sum(ReferralEarning.commission_cents))
        .where(ReferralEarning.referrer_user_id == user.id)
        .where(ReferralEarning.status == "pending")
    )
    pending_earnings = pending_earnings_result.scalar() or 0

    # Calculate paid out
    paid_out_result = await db.execute(
        select(func.sum(ReferralPayout.amount_cents))
        .where(ReferralPayout.user_id == user.id)
        .where(ReferralPayout.status == PayoutStatus.COMPLETED)
    )
    paid_out = paid_out_result.scalar() or 0

    # Available balance = approved earnings - paid out
    approved_earnings_result = await db.execute(
        select(func.sum(ReferralEarning.commission_cents))
        .where(ReferralEarning.referrer_user_id == user.id)
        .where(ReferralEarning.status == "approved")
    )
    approved_earnings = approved_earnings_result.scalar() or 0
    available_balance = approved_earnings - paid_out

    return ReferralStatsResponse(
        total_referrals=sum(status_counts.values()),
        pending_signups=status_counts.get(ReferralStatus.PENDING, 0)
        + status_counts.get(ReferralStatus.SIGNED_UP, 0),
        converted=status_counts.get(ReferralStatus.CONVERTED, 0),
        total_earnings_cents=total_earnings,
        pending_earnings_cents=pending_earnings,
        available_balance_cents=max(0, available_balance),
    )


@router.get("/list", response_model=ReferralsListResponse)
async def list_referrals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List all referrals made by user."""
    # Get referral code
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == user.id)
    )
    referral_code = result.scalar_one_or_none()

    if not referral_code:
        return ReferralsListResponse(referrals=[], total=0)

    # Get referrals
    referrals_result = await db.execute(
        select(Referral)
        .where(Referral.referral_code_id == referral_code.id)
        .order_by(Referral.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    referrals = referrals_result.scalars().all()

    # Count total
    count_result = await db.execute(
        select(func.count(Referral.id)).where(
            Referral.referral_code_id == referral_code.id
        )
    )
    total = count_result.scalar() or 0

    # Get earnings per referral
    items = []
    for referral in referrals:
        earnings_result = await db.execute(
            select(func.sum(ReferralEarning.commission_cents)).where(
                ReferralEarning.referral_id == referral.id
            )
        )
        earnings = earnings_result.scalar() or 0

        items.append(
            ReferralListItem(
                referee_email=referral.referee_email,
                status=referral.status,
                signed_up_at=(
                    referral.signed_up_at.isoformat() if referral.signed_up_at else None
                ),
                converted_at=(
                    referral.converted_at.isoformat() if referral.converted_at else None
                ),
                earnings_cents=earnings,
            )
        )

    return ReferralsListResponse(referrals=items, total=total)


@router.get("/earnings", response_model=EarningsListResponse)
async def list_earnings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List all earnings from referrals."""
    # Get earnings with referral info
    earnings_result = await db.execute(
        select(ReferralEarning, Referral)
        .join(Referral, ReferralEarning.referral_id == Referral.id)
        .where(ReferralEarning.referrer_user_id == user.id)
        .order_by(ReferralEarning.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = earnings_result.all()

    # Count total
    count_result = await db.execute(
        select(func.count(ReferralEarning.id)).where(
            ReferralEarning.referrer_user_id == user.id
        )
    )
    total_count = count_result.scalar() or 0

    # Sum total cents
    sum_result = await db.execute(
        select(func.sum(ReferralEarning.commission_cents)).where(
            ReferralEarning.referrer_user_id == user.id
        )
    )
    total_cents = sum_result.scalar() or 0

    items = [
        EarningsListItem(
            referral_email=referral.referee_email,
            amount_cents=earning.amount_cents,
            commission_cents=earning.commission_cents,
            status=earning.status,
            created_at=earning.created_at.isoformat(),
        )
        for earning, referral in rows
    ]

    return EarningsListResponse(
        earnings=items,
        total=total_count,
        total_cents=total_cents,
    )


@router.post("/payout", response_model=PayoutResponse)
async def request_payout(
    request: PayoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a payout of available earnings.

    Minimum payout is $50 (5000 cents).
    """
    # Validate method
    try:
        method = PayoutMethod(request.method)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payout method: {request.method}",
        ) from e

    # Check minimum payout
    min_payout_cents = 5000  # $50
    if request.amount_cents < min_payout_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum payout is ${min_payout_cents / 100:.2f}",
        )

    # Calculate available balance
    approved_earnings_result = await db.execute(
        select(func.sum(ReferralEarning.commission_cents))
        .where(ReferralEarning.referrer_user_id == user.id)
        .where(ReferralEarning.status == "approved")
    )
    approved_earnings = approved_earnings_result.scalar() or 0

    paid_out_result = await db.execute(
        select(func.sum(ReferralPayout.amount_cents))
        .where(ReferralPayout.user_id == user.id)
        .where(ReferralPayout.status == PayoutStatus.COMPLETED)
    )
    paid_out = paid_out_result.scalar() or 0

    pending_payouts_result = await db.execute(
        select(func.sum(ReferralPayout.amount_cents))
        .where(ReferralPayout.user_id == user.id)
        .where(
            ReferralPayout.status.in_([PayoutStatus.PENDING, PayoutStatus.PROCESSING])
        )
    )
    pending_payouts = pending_payouts_result.scalar() or 0

    available_balance = approved_earnings - paid_out - pending_payouts

    if request.amount_cents > available_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Available: ${available_balance / 100:.2f}",
        )

    # Create payout request
    payout = ReferralPayout(
        user_id=user.id,
        amount_cents=request.amount_cents,
        method=method.value,
        status=PayoutStatus.PENDING,
    )
    db.add(payout)
    await db.commit()
    await db.refresh(payout)

    return PayoutResponse(
        id=str(payout.id),
        amount_cents=payout.amount_cents,
        method=payout.method,
        status=payout.status,
        created_at=payout.created_at.isoformat(),
    )


@router.get("/payouts", response_model=list[PayoutResponse])
async def list_payouts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all payout requests."""
    result = await db.execute(
        select(ReferralPayout)
        .where(ReferralPayout.user_id == user.id)
        .order_by(ReferralPayout.created_at.desc())
    )
    payouts = result.scalars().all()

    return [
        PayoutResponse(
            id=str(payout.id),
            amount_cents=payout.amount_cents,
            method=payout.method,
            status=payout.status,
            created_at=payout.created_at.isoformat(),
        )
        for payout in payouts
    ]


# =============================================================================
# Helper Functions (for use by other modules)
# =============================================================================


async def track_referral_signup(
    db: AsyncSession,
    referral_code_str: str,
    referee_user: User,
) -> Referral | None:
    """Track a referral when a new user signs up.

    Args:
        db: Database session.
        referral_code_str: The referral code used.
        referee_user: The new user who signed up.

    Returns:
        Created Referral or None if code not found.
    """
    # Find referral code
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.code == referral_code_str.upper())
    )
    referral_code = result.scalar_one_or_none()

    if not referral_code or not referral_code.is_active:
        return None

    # Don't allow self-referral
    if referral_code.user_id == referee_user.id:
        return None

    # Create referral record
    referral = Referral(
        referral_code_id=referral_code.id,
        referrer_user_id=referral_code.user_id,
        referee_user_id=referee_user.id,
        referee_email=referee_user.email,
        status=ReferralStatus.SIGNED_UP,
        signed_up_at=datetime.now(timezone.utc),
    )
    db.add(referral)

    # Update stats
    referral_code.total_referrals += 1

    await db.flush()
    return referral


async def track_referral_conversion(
    db: AsyncSession,
    referee_user_id: str,
    payment_amount_cents: int,
) -> ReferralEarning | None:
    """Track a referral conversion and calculate commission.

    Called when a referred user makes their first payment.

    Args:
        db: Database session.
        referee_user_id: The referred user's ID.
        payment_amount_cents: Amount paid in cents.

    Returns:
        Created ReferralEarning or None if not a referral.
    """
    from uuid import UUID

    # Find referral for this user
    result = await db.execute(
        select(Referral)
        .where(Referral.referee_user_id == UUID(referee_user_id))
        .where(Referral.status == ReferralStatus.SIGNED_UP)
    )
    referral = result.scalar_one_or_none()

    if not referral:
        return None

    # Get commission rate from referral code
    code_result = await db.execute(
        select(ReferralCode).where(ReferralCode.id == referral.referral_code_id)
    )
    referral_code = code_result.scalar_one_or_none()

    if not referral_code:
        return None

    # Calculate commission
    commission_rate = referral_code.commission_rate
    commission_cents = int(Decimal(payment_amount_cents) * commission_rate)

    # Update referral status
    referral.status = ReferralStatus.CONVERTED
    referral.converted_at = datetime.now(timezone.utc)

    # Update referral code stats
    referral_code.total_conversions += 1
    referral_code.total_earnings_cents += commission_cents

    # Create earning record
    earning = ReferralEarning(
        referral_id=referral.id,
        referrer_user_id=referral.referrer_user_id,
        amount_cents=payment_amount_cents,
        commission_cents=commission_cents,
        status="pending",  # Pending until 30-day hold period
    )
    db.add(earning)

    await db.flush()
    return earning
