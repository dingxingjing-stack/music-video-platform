from app.services.supabase_service import supabase
from postgrest.exceptions import APIError
from typing import Dict, Any

def create_feedback(name: str, text: str, user_id: str) -> Dict[str, Any]:
    """Create a new feedback entry in the database.

    真实 Supabase feedback 表要求 user_id uuid NOT NULL、content text NOT NULL、
    text NOT NULL。user_id 必须来自认证用户对应的 users.id（UUID）。
    """
    data = {"user_id": user_id, "name": name, "text": text, "content": text}
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