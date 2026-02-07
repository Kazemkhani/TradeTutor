"""Cloudflare Turnstile verification.

Invisible CAPTCHA verification for bot protection.
https://developers.cloudflare.com/turnstile/
"""

import os

import httpx


async def verify_turnstile(
    token: str,
    remote_ip: str | None = None,
) -> tuple[bool, str | None]:
    """Verify a Cloudflare Turnstile token.

    Args:
        token: The turnstile response token from the client.
        remote_ip: Optional client IP for additional verification.

    Returns:
        Tuple of (is_valid, error_message).
    """
    secret_key = os.getenv("TURNSTILE_SECRET_KEY", "")

    # If not configured, allow (for development)
    if not secret_key:
        return True, None

    # Verify with Cloudflare
    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    payload = {
        "secret": secret_key,
        "response": token,
    }

    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=5.0)
            result = response.json()

            if result.get("success"):
                return True, None

            # Get error codes
            error_codes = result.get("error-codes", [])

            if "missing-input-secret" in error_codes:
                return False, "Server configuration error"
            if "invalid-input-secret" in error_codes:
                return False, "Server configuration error"
            if "missing-input-response" in error_codes:
                return False, "Missing verification token"
            if "invalid-input-response" in error_codes:
                return False, "Invalid verification token"
            if "bad-request" in error_codes:
                return False, "Verification request failed"
            if "timeout-or-duplicate" in error_codes:
                return False, "Verification expired, please try again"
            if "internal-error" in error_codes:
                return False, "Verification service error, please try again"

            return False, "Verification failed"

    except httpx.TimeoutException:
        # Allow on timeout (graceful degradation)
        return True, None
    except Exception as e:
        # Log error but allow (graceful degradation)
        print(f"Turnstile verification error: {e}")
        return True, None
