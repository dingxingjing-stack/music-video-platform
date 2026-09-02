from fastapi import APIRouter, Header, HTTPException
import os

router = APIRouter(prefix="/api/v1", tags=["user_age"])

@router.get("/user/age")
async def get_user_age(x_user_id: str = Header(None, alias="X-User-ID")):
    """
    Return user age for age‑gating AI generation features.
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