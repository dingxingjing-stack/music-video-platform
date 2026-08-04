"""
社区排行榜路由 (Community Charts Router)

API 端点:
GET  /api/v1/community/hot — 热门排行榜
GET  /api/v1/community/new — 新歌榜
GET  /api/v1/community/trending — 趋势榜
GET  /api/v1/community/search — 搜索
GET  /api/v1/community/genre/{genre} — 按风格筛选
POST /api/v1/community/{id}/like — 点赞
POST /api/v1/community/{id}/play — 增加播放
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List

from app.services.community_service import community_service, CommunityTrack
from app.services.cache_service import cached


router = APIRouter(prefix="/api/v1/community", tags=["社区"])


@router.get("/hot")
@cached(ttl=30)
async def get_hot_chart(
    limit: int = Query(default=20, ge=1, le=50)
):
    """获取热门排行榜（按播放量）"""
    tracks = community_service.get_hot_chart(limit)
    return {
        "chart_type": "hot",
        "tracks": tracks,
        "total": len(tracks),
    }


@router.get("/new")
async def get_new_chart(
    limit: int = Query(default=20, ge=1, le=50)
):
    """获取新歌榜（按创建时间）"""
    tracks = community_service.get_new_chart(limit)
    return {
        "chart_type": "new",
        "tracks": tracks,
        "total": len(tracks),
    }


@router.get("/trending")
async def get_trending_chart(
    limit: int = Query(default=20, ge=1, le=50)
):
    """获取趋势榜（播放量 + 点赞增长率）"""
    tracks = community_service.get_trending_chart(limit)
    return {
        "chart_type": "trending",
        "tracks": tracks,
        "total": len(tracks),
    }


@router.get("/search")
async def search_tracks(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    genre: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50)
):
    """搜索歌曲"""
    results = community_service.search_tracks(q, genre)
    return {
        "query": q,
        "genre": genre,
        "tracks": results[:limit],
        "total": len(results),
    }


@router.get("/genre/{genre}")
async def get_tracks_by_genre(
    genre: str,
    limit: int = Query(default=20, ge=1, le=50)
):
    """按风格筛选"""
    tracks = community_service.get_tracks_by_genre(genre, limit)
    return {
        "genre": genre,
        "tracks": tracks,
        "total": len(tracks),
    }


@router.post("/{track_id}/like")
async def like_track(track_id: str):
    """点赞歌曲"""
    likes = community_service.like_track(track_id)
    if likes == 0:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return {"success": True, "likes": likes}


@router.post("/{track_id}/play")
async def play_track(track_id: str):
    """增加播放量"""
    plays = community_service.play_track(track_id)
    if plays == 0:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return {"success": True, "plays": plays}