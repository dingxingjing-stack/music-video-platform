"""User‑related lightweight endpoints (age, preferences)."""

from fastapi import APIRouter, HTTPException
import os

router = APIRouter()

@router.get("/age", tags=["user"])
async def get_user_age():
    """Return the user's age.
    In a real deployment this would be looked up from an auth service or DB.
    Here we read the optional environment variable ``USER_AGE`` – if missing
    we fall back to a safe default of ``25`` (an adult).
    """
    try:
        age = int(os.getenv("USER_AGE", "25"))
    except ValueError:
        raise HTTPException(status_code=500, detail="Invalid USER_AGE env var")
    return {"age": age}
