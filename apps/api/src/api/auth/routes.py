"""Authentication API routes.

Provides signup, login, email verification, and token refresh endpoints.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import (
    TokenPair,
    create_token_pair,
    decode_token,
    get_current_user,
)
from api.auth.password import get_password_hash, verify_password
from api.db.database import get_db
from api.db.models import ReferralCode, Subscription, SubscriptionStatus, User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SignupRequest(BaseModel):
    """Request body for user signup."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    referral_code: str | None = None
    fingerprint: str | None = None  # Device fingerprint for anti-fraud


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class VerifyEmailRequest(BaseModel):
    """Request body for email verification."""

    token: str


class UserResponse(BaseModel):
    """User data response."""

    id: str
    email: str
    email_verified: bool
    phone: str | None
    phone_verified: bool
    trial_active: bool
    trial_minutes_remaining: float
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response with tokens and user data."""

    user: UserResponse
    tokens: TokenPair


# =============================================================================
# Email Verification Token Store (in-memory for MVP, use Redis in production)
# =============================================================================

# Simple in-memory store for email verification tokens
# In production, use Redis with TTL or database table
_email_verification_tokens: dict[str, tuple[str, datetime]] = {}


def create_email_verification_token(email: str) -> str:
    """Create a secure email verification token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    _email_verification_tokens[token] = (email, expires_at)
    return token


def verify_email_token(token: str) -> str | None:
    """Verify an email token and return the email if valid."""
    if token not in _email_verification_tokens:
        return None

    email, expires_at = _email_verification_tokens[token]
    if datetime.now(timezone.utc) > expires_at:
        del _email_verification_tokens[token]
        return None

    del _email_verification_tokens[token]
    return email


# =============================================================================
# Routes
# =============================================================================


@router.post(
    "/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    request: SignupRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account.

    - Creates user with hashed password
    - Starts 7-day trial with 10 minutes
    - Generates referral code
    - Returns JWT tokens

    If referral_code is provided, tracks the referral for commission.
    """
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Get client IP for anti-fraud
    client_ip = http_request.client.host if http_request.client else None

    # Create user
    user = User(
        email=request.email,
        password_hash=get_password_hash(request.password),
        signup_ip=client_ip,
        signup_fingerprint=request.fingerprint,
    )

    # Start trial
    user.start_trial(days=7, minutes=10)

    db.add(user)
    await db.flush()  # Get user ID

    # Create trial subscription
    trial_sub = Subscription(
        user_id=user.id,
        plan_id="trial",
        status=SubscriptionStatus.TRIALING,
        current_period_start=user.trial_started_at,
        current_period_end=user.trial_ends_at,
        minutes_limit=10,
        allow_overage=False,
    )
    db.add(trial_sub)

    # Generate referral code for new user
    referral_code = ReferralCode(user_id=user.id)
    db.add(referral_code)

    # TODO: Handle referral tracking if request.referral_code provided
    # TODO: Send email verification email

    await db.commit()

    # Create tokens
    tokens = create_token_pair(user.id)

    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            email_verified=user.is_email_verified,
            phone=user.phone,
            phone_verified=user.is_phone_verified,
            trial_active=user.is_trial_active,
            trial_minutes_remaining=float(user.trial_minutes_remaining),
            created_at=user.created_at,
        ),
        tokens=tokens,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return tokens.

    Verifies email and password, returns JWT access and refresh tokens.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user is None or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create tokens
    tokens = create_token_pair(user.id)

    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            email_verified=user.is_email_verified,
            phone=user.phone,
            phone_verified=user.is_phone_verified,
            trial_active=user.is_trial_active,
            trial_minutes_remaining=float(user.trial_minutes_remaining),
            created_at=user.created_at,
        ),
        tokens=tokens,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token.

    Returns new access and refresh token pair.
    """
    # Decode and validate refresh token
    token_data = decode_token(request.refresh_token)

    if token_data.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # Verify user still exists
    result = await db.execute(select(User).where(User.id == token_data.sub))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Create new token pair
    return create_token_pair(user.id)


@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify email address using verification token.

    Token is sent to user's email during signup.
    """
    email = verify_email_token(request.token)

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    # Update user's email verification status
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Email verified successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        email_verified=user.is_email_verified,
        phone=user.phone,
        phone_verified=user.is_phone_verified,
        trial_active=user.is_trial_active,
        trial_minutes_remaining=float(user.trial_minutes_remaining),
        created_at=user.created_at,
    )
