"""JWT token creation and validation.

Provides access tokens (short-lived) and refresh tokens (long-lived).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.database import get_db
from api.db.models import User

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_32_BYTES!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str  # User ID
    type: str  # "access" or "refresh"
    exp: datetime
    iat: datetime


class TokenPair(BaseModel):
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until access token expires


# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: UUID | str, expires_delta: timedelta | None = None
) -> str:
    """Create a short-lived access token.

    Args:
        user_id: The user's UUID.
        expires_delta: Optional custom expiration time.

    Returns:
        Encoded JWT access token.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    to_encode: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: UUID | str, expires_delta: timedelta | None = None
) -> str:
    """Create a long-lived refresh token.

    Args:
        user_id: The user's UUID.
        expires_delta: Optional custom expiration time.

    Returns:
        Encoded JWT refresh token.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    to_encode: dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_token_pair(user_id: UUID | str) -> TokenPair:
    """Create both access and refresh tokens.

    Args:
        user_id: The user's UUID.

    Returns:
        TokenPair with access_token, refresh_token, and metadata.
    """
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token to decode.

    Returns:
        TokenPayload with user ID and token metadata.

    Raises:
        HTTPException: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(
            sub=payload["sub"],
            type=payload["type"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e!s}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency to get the current authenticated user.

    Usage:
        @app.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return user

    Raises:
        HTTPException: 401 if not authenticated or token invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(credentials.credentials)

    if token_data.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == UUID(token_data.sub)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """FastAPI dependency to optionally get the current user.

    Returns None if not authenticated instead of raising an exception.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
