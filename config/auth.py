import os
from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(default=None)):
    """Require a matching X-API-Key header on protected routes.

    If API_KEY is not configured in the environment, auth is skipped so the
    app remains easy to run locally out of the box.
    """
    expected_key = os.getenv("API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
