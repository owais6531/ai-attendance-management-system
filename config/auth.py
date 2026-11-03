import os
import secrets

from fastapi import Header, HTTPException, status


def auth_enabled() -> bool:
    return bool(os.getenv("API_KEY"))


async def verify_api_key(x_api_key: str | None = Header(default=None)):
    """Require a matching X-API-Key header on protected routes.

    If API_KEY is not configured, auth is skipped so the app runs out of the
    box locally. (Proper user logins are planned; see the README roadmap.)
    """
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
