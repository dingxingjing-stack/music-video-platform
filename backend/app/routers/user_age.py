from fastapi import APIRouter, HTTPException, Depends
import os

from app.services.auth_identity import get_verified_user_id

router = APIRouter(prefix="/api/v1", tags=["user_age"])

@router.get("/user/age")
async def get_user_age(user_id: str = Depends(get_verified_user_id)):
    """
    Return user age for age-gating AI generation features.
    身份：Authorization Bearer JWT → verified auth.users.id（缺 JWT 自动 401）。
    In production replace with real user data source.
    """
    age_str = os.getenv("USER_AGE")
    if not age_str:
        raise HTTPException(status_code=500, detail="USER_AGE env var not set")
    try:
        age = int(age_str)
    except ValueError:
        age = age_str
    return {"age": age, "under_13": age < 13}