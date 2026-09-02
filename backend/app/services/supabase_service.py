"""
Supabase service for database operations.
"""
import os
from typing import Dict, List, Optional, Any
from postgrest.exceptions import APIError
from supabase import create_client, Client

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_SUPABASE_CONFIGURED = bool(SUPABASE_URL and (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY))


class _LazySupabase:
    """惰性 Supabase 客户端代理。

    未配置 SUPABASE_URL/KEY 时模块可正常导入，
    实际调用才抛 APIError，由各 service 的 except APIError 兜底降级。
    """

    _client: Optional[Client] = None
    _error: Optional[APIError] = None

    def _ensure(self) -> Client:
        if not _SUPABASE_CONFIGURED:
            raise APIError({"message": "Supabase 未配置 (SUPABASE_URL/KEY 缺失)"})
        if self._client is None:
            self._client = create_client(
                SUPABASE_URL,
                SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY,
            )
        return self._client

    def __getattr__(self, name: str):
        client = self._ensure()
        return getattr(client, name)


# Use service role key for backend operations if available, else anon key
supabase = _LazySupabase()

def get_user_by_supabase_id(supabase_user_id: str) -> Optional[Dict]:
    """Get user by Supabase user ID."""
    try:
        response = supabase.table("users").select("*").eq("supabase_user_id", supabase_user_id).execute()
        return response.data[0] if response.data else None
    except APIError as e:
        print(f"Error fetching user: {e}")
        return None

def create_user(email: str, supabase_user_id: str, username: Optional[str] = None, 
                avatar_url: Optional[str] = None, age: Optional[int] = None) -> Dict:
    """Create a new user."""
    try:
        user_data = {
            "email": email,
            "supabase_user_id": supabase_user_id,
            "username": username,
            "avatar_url": avatar_url,
            "age": age,
        }
        # Remove None values
        user_data = {k: v for k, v in user_data.items() if v is not None}
        response = supabase.table("users").insert(user_data).execute()
        return response.data[0]
    except APIError as e:
        print(f"Error creating user: {e}")
        raise

def get_user(user_id: str) -> Optional[Dict]:
    """Get user by internal user ID."""
    try:
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        return response.data[0] if response.data else None
    except APIError as e:
        print(f"Error fetching user: {e}")
        return None

def update_user(user_id: str, updates: Dict) -> Optional[Dict]:
    """Update user by ID."""
    try:
        response = supabase.table("users").update(updates).eq("id", user_id).execute()
        return response.data[0] if response.data else None
    except APIError as e:
        print(f"Error updating user: {e}")
        return None

def get_songs_by_user(user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get songs for a user."""
    try:
        response = supabase.table("songs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset).execute()
        return response.data
    except APIError as e:
        print(f"Error fetching songs: {e}")
        return []

def get_song_by_id(song_id: str) -> Optional[Dict]:
    """Get song by ID."""
    try:
        response = supabase.table("songs").select("*").eq("id", song_id).execute()
        return response.data[0] if response.data else None
    except APIError as e:
        print(f"Error fetching song: {e}")
        return None

def create_song(user_id: str, song_data: Dict) -> Dict:
    """Create a new song."""
    try:
        song_data["user_id"] = user_id
        response = supabase.table("songs").insert(song_data).execute()
        return response.data[0]
    except APIError as e:
        print(f"Error creating song: {e}")
        raise

def update_song(song_id: str, updates: Dict) -> Optional[Dict]:
    """Update song by ID."""
    try:
        response = supabase.table("songs").update(updates).eq("id", song_id).execute()
        return response.data[0] if response.data else None
    except APIError as e:
        print(f"Error updating song: {e}")
        return None

def delete_song(song_id: str) -> bool:
    """Delete song by ID."""
    try:
        supabase.table("songs").delete().eq("id", song_id).execute()
        return True
    except APIError as e:
        print(f"Error deleting song: {e}")
        return False

def get_feedback(limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get feedback entries."""
    try:
        response = supabase.table("feedback").select("*").order("created_at", desc=True).limit(limit).offset(offset).execute()
        return response.data
    except APIError as e:
        print(f"Error fetching feedback: {e}")
        return []

def create_feedback(name: str, text: str) -> Dict:
    """Create a new feedback entry."""
    try:
        feedback_data = {
            "name": name,
            "text": text,
        }
        response = supabase.table("feedback").insert(feedback_data).execute()
        return response.data[0]
    except APIError as e:
        print(f"Error creating feedback: {e}")
        raise


# ── auth.py / songs.py 所需的接口（安全包装，避免 Supabase 分支 ImportError）──

def get_user_songs(user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
    """获取用户歌曲（songs.py 期望的接口名，映射到 get_songs_by_user）。"""
    return get_songs_by_user(user_id, limit, offset)

def log_activity(user_id: str, action: str, resource_type: str = "",
                 resource_id: str = "", metadata: Optional[Dict] = None) -> Any:
    """记录活动日志（Supabase activity_logs；表/列缺失时安全降级，不抛错）。"""
    try:
        row: Dict[str, Any] = {"user_id": user_id, "action": action}
        if resource_type:
            row["resource_type"] = resource_type
        if resource_id:
            row["resource_id"] = resource_id
        if metadata:
            row["metadata"] = metadata
        supabase.table("activity_logs").insert(row).execute()
        return True
    except Exception:
        return None

def _adjust_user_credits(user_id: str, delta: int) -> Any:
    """读取并调整 users.credits；表/列缺失时安全返回 None，不抛错。"""
    try:
        resp = supabase.table("users").select("credits").eq("id", user_id).execute()
        if not resp.data:
            return None
        cur = int(resp.data[0].get("credits") or 0)
        new = max(0, cur + delta)
        supabase.table("users").update({"credits": new}).eq("id", user_id).execute()
        return new
    except Exception:
        return None

def increment_user_credits(user_id: str, amount: int = 1) -> Any:
    return _adjust_user_credits(user_id, amount)

def decrement_user_credits(user_id: str, amount: int = 1) -> Any:
    return _adjust_user_credits(user_id, -amount)