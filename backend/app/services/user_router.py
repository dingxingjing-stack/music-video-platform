"""User‑related lightweight endpoints (age, preferences)."""

from fastapi import APIRouter, HTTPException, Depends
import logging
import os

from app.services.auth_identity import get_verified_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_user_by_supabase_id():
    """按 supabase_user_id（= 已验证 auth.users.id）查 profile。

    - Supabase：get_user_by_supabase_id（查 public.users.supabase_user_id）
    - SQLite：get_user（其入参即 supabase_user_id）
    """
    cfg = bool(
        os.getenv("SUPABASE_URL")
        and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    )
    if cfg:
        from app.services.supabase_service import get_user_by_supabase_id
        return get_user_by_supabase_id
    from app.services.sqlite_service import get_user
    return get_user


@router.get("/age", tags=["user"])
async def get_user_age(user_id: str = Depends(get_verified_user_id)):
    """Return the user's age from their stored profile.

    身份唯一可信来源：Authorization Bearer JWT → verified auth.users.id（缺 JWT 自动 401）。
    不再使用 X-User-ID / body / query / IP 作为身份。
    """
    get_user = _get_user_by_supabase_id()
    try:
        user = get_user(user_id)
    except Exception:
        logger.exception("Failed to look up user age for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to read user profile")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    age = user.get("age")
    if age is None:
        raise HTTPException(status_code=404, detail="Age not set for user")

    try:
        age = int(age)
    except (TypeError, ValueError):
        logger.error("Stored age for user=%s is not a valid integer", user_id)
        raise HTTPException(status_code=500, detail="Stored age is invalid")

    return {"age": age}
