from app.services.supabase_service import supabase
from postgrest.exceptions import APIError
from typing import Dict, Any

def create_feedback(name: str, text: str) -> Dict[str, Any]:
    """Create a new feedback entry in the database."""
    data = {"name": name, "text": text}
    try:
        response = supabase.table("feedback").insert(data).execute()
        return response.data[0]
    except APIError as e:
        raise e


def get_feedback(limit: int = 50, offset: int = 0) -> list[Dict[str, Any]]:
    """Fetch feedback entries, newest first."""
    try:
        response = (
            supabase.table("feedback")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        return response.data or []
    except APIError as e:
        raise e