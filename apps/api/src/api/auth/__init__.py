"""Authentication module.

Provides JWT-based authentication, password hashing, and auth routes.
"""

from api.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_current_user_optional,
)
from api.auth.password import get_password_hash, verify_password
from api.auth.routes import router as auth_router

__all__ = [
    "auth_router",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "get_current_user_optional",
    "get_password_hash",
    "verify_password",
]
