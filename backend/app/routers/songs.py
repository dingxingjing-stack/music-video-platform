"""
歌曲管理路由
功能：创建、查询、更新、删除歌曲
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import uuid

# 尝试导入 SQLite 服务（优先）或 Supabase 服务
try:
    from app.services.sqlite_service import (
        get_user, create_song, get_user_songs, log_activity
    )
    DB_BACKEND = "sqlite"
except ImportError:
    from app.services.supabase_service import (
        SupabaseService, get_user, create_song, get_user_songs, log_activity
    )
    DB_BACKEND = "supabase"

router = APIRouter(prefix="/api/v1/songs", tags=["歌曲管理"])


class SongCreate(BaseModel):
    title: str
    lyrics: Optional[str] = None
    style: Optional[str] = None
    duration_seconds: Optional[int] = None
    is_public: bool = False
    metadata: Optional[Dict] = {}


class SongResponse(BaseModel):
    id: str
    user_id: str
    title: str
    lyrics: Optional[str] = None
    style: Optional[str] = None
    duration_seconds: Optional[int] = None
    audio_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    mv_url: Optional[str] = None
    status: str = 'pending'
    is_public: bool = False
    play_count: int = 0
    like_count: int = 0
    metadata: Dict = {}
    created_at: str
    updated_at: str


@router.post("/", response_model=SongResponse)
async def create_new_song(
    song_data: SongCreate,
    authorization: Optional[str] = Header(None)
):
    """
    创建新歌曲
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    supabase_user_id = authorization.replace("Bearer ", "")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 检查用户额度
    if user.get("credits", 0) <= 0:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credits. Please add credits first."
        )
    
    try:
        # 创建歌曲记录
        song = create_song(
            user_id=user["id"],
            title=song_data.title,
            lyrics=song_data.lyrics,
            style=song_data.style,
            duration_seconds=song_data.duration_seconds,
            is_public=song_data.is_public,
            metadata=song_data.metadata or {}
        )
        
        # 扣除额度
        from app.services.sqlite_service import decrement_user_credits
        decrement_user_credits(user["id"], 1)
        
        # 记录日志
        log_activity(
            user_id=user["id"],
            action="SONG_CREATED",
            resource_id=song["id"],
            metadata={"title": song_data.title}
        )
        
        return SongResponse(**song)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create song: {str(e)}")


@router.get("/", response_model=List[SongResponse])
async def list_user_songs(
    authorization: Optional[str] = Header(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    获取用户歌曲列表
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    supabase_user_id = authorization.replace("Bearer ", "")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    songs = get_user_songs(user["id"], limit=limit)
    
    # 应用 offset
    if offset > 0:
        songs = songs[offset:]
    
    return [SongResponse(**song) for song in songs]


@router.get("/{song_id}", response_model=SongResponse)
async def get_song(song_id: str, authorization: Optional[str] = Header(None)):
    """
    获取歌曲详情
    """
    from app.services.supabase_service import supabase
    
    response = supabase.table("songs").select("*").eq("id", song_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Song not found")
    
    song = response.data[0]
    
    # 检查权限
    if authorization:
        supabase_user_id = authorization.replace("Bearer ", "")
        user = get_user(supabase_user_id)
        if user and song["user_id"] == user["id"]:
            return SongResponse(**song)
    
    # 公开歌曲任何人都可访问
    if song["is_public"]:
        return SongResponse(**song)
    
    raise HTTPException(status_code=403, detail="Access denied")


@router.put("/{song_id}", response_model=SongResponse)
async def update_song(
    song_id: str,
    update_data: Dict,
    authorization: Optional[str] = Header(None)
):
    """
    更新歌曲信息
    """
    from app.services.supabase_service import supabase
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    supabase_user_id = authorization.replace("Bearer ", "")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 获取歌曲
    response = supabase.table("songs").select("*").eq("id", song_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Song not found")
    
    song = response.data[0]
    
    # 检查所有权
    if song["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this song")
    
    # 更新
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    response = supabase.table("songs")\
        .update(update_data)\
        .eq("id", song_id)\
        .execute()
    
    # 记录日志
    log_activity(
        user_id=user["id"],
        action="SONG_UPDATED",
        resource_id=song_id,
        metadata={"updated_fields": list(update_data.keys())}
    )
    
    return SongResponse(**response.data[0])


@router.delete("/{song_id}")
async def delete_song(song_id: str, authorization: Optional[str] = Header(None)):
    """
    删除歌曲
    """
    from app.services.supabase_service import supabase
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    supabase_user_id = authorization.replace("Bearer ", "")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 获取歌曲
    response = supabase.table("songs").select("*").eq("id", song_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Song not found")
    
    song = response.data[0]
    
    # 检查所有权
    if song["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this song")
    
    # 删除
    supabase.table("songs").delete().eq("id", song_id).execute()
    
    # 记录日志
    log_activity(
        user_id=user["id"],
        action="SONG_DELETED",
        resource_id=song_id,
        metadata={"title": song["title"]}
    )
    
    return {"success": True, "message": "Song deleted successfully"}


@router.post("/{song_id}/publish")
async def publish_song(song_id: str, authorization: Optional[str] = Header(None)):
    """
    发布歌曲（设为公开）
    """
    from app.services.supabase_service import supabase
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    supabase_user_id = authorization.replace("Bearer ", "")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 更新为公开
    response = supabase.table("songs")\
        .update({"is_public": True, "updated_at": datetime.utcnow().isoformat()})\
        .eq("id", song_id)\
        .execute()
    
    # 记录日志
    log_activity(
        user_id=user["id"],
        action="SONG_PUBLISHED",
        resource_id=song_id
    )
    
    return {"success": True, "message": "Song published"}


@router.get("/{song_id}/stats")
async def get_song_stats(song_id: str):
    """
    获取歌曲统计信息
    """
    from app.services.supabase_service import supabase
    
    response = supabase.table("songs").select("play_count, like_count").eq("id", song_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Song not found")
    
    song = response.data[0]
    
    return {
        "song_id": song_id,
        "play_count": song["play_count"],
        "like_count": song["like_count"]
    }