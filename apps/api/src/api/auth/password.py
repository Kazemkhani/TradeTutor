"""Password hashing utilities using bcrypt.

Uses passlib with bcrypt for secure password hashing.
"""

from passlib.context import CryptContext

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The bcrypt hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of a password.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash of the password.
    """
    return pwd_context.hash(password)
