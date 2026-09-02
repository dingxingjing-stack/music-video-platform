"""User‑related lightweight endpoints (age, preferences)."""

from fastapi import APIRouter, HTTPException, Header
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_user_backend():
    """Return the configured user lookup function (Supabase if configured, else SQLite)."""
    cfg = bool(
        os.getenv("SUPABASE_URL")
        and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    )
    if cfg:
        from app.services.supabase_service import get_user
    else:
        from app.services.sqlite_service import get_user
    return get_user


@router.get("/age", tags=["user"])
async def get_user_age(x_user_id: str = Header(None, alias="X-User-ID")):
    """Return the user's age from their stored profile.

    The user is identified via the ``X-User-ID`` header (same auth convention as
    the rest of the API). Anonymous requests receive 401 so age‑gating can only be
    enforced for known users — never a fabricated default.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-ID header required")

    get_user = _get_user_backend()
    try:
        user = get_user(x_user_id)
    except Exception:
        logger.exception("Failed to look up user age for user=%s", x_user_id)
        raise HTTPException(status_code=500, detail="Failed to read user profile")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    age = user.get("age")
    if age is None:
        raise HTTPException(status_code=404, detail="Age not set for user")

    try:
        age = int(age)
    except (TypeError, ValueError):
        logger.error("Stored age for user=%s is not a valid integer", x_user_id)
        raise HTTPException(status_code=500, detail="Stored age is invalid")

    return {"age": age}
