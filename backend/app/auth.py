import os

from fastapi import Request
from fastapi.responses import JSONResponse

ENV_TOKEN = "WHEREISIT_TOKEN"
EXEMPT_PATHS = frozenset({"/health"})


def current_token() -> str | None:
    """The configured shared token, or None for dev mode (env var unset/empty)."""
    return os.getenv(ENV_TOKEN) or None


async def auth_middleware(request: Request, call_next):
    if request.url.path in EXEMPT_PATHS:
        return await call_next(request)

    token = current_token()
    if token is None:
        return await call_next(request)

    presented = request.headers.get("authorization", "")
    if presented != f"Bearer {token}":
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)
