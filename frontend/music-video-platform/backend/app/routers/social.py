"""
社交系统路由 (Social System Router)

API 端点:
- POST /api/v1/social/like - 点赞作品
- POST /api/v1/social/unlike - 取消点赞
- POST /api/v1/social/favorite - 收藏作品
- POST /api/v1/social/unfavorite - 取消收藏
- POST /api/v1/social/follow - 关注用户
- POST /api/v1/social/unfollow - 取消关注
- GET /api/v1/social/stats/{work_id} - 获取统计 (点赞/播放/收藏数)
- GET /api/v1/social/feed - 个性化推荐 feed
"""

from fastapi import APIRouter, HTTPException, Query, Header
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.social import social_storage, WorkStats


router = APIRouter(prefix="/api/v1/social", tags=["社交系统"])


# ============ Request Models ============

class LikeRequest(BaseModel):
    work_id: str = Field(..., description="作品 ID")


class FavoriteRequest(BaseModel):
    work_id: str = Field(..., description="作品 ID")


class FollowRequest(BaseModel):
    user_id: str = Field(..., description="要关注的用户 ID")


class SocialResponse(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[dict] = Field(default=None, description="响应数据")


class StatsResponse(BaseModel):
    work_id: str
    likes: int
    favorites: int
    plays: int
    is_liked: bool = False
    is_favorited: bool = False


class FeedItem(BaseModel):
    work_id: str
    author_id: str
    title: str
    likes: int
    favorites: int
    plays: int


class FeedResponse(BaseModel):
    items: List[FeedItem]
    total: int


# ============ Helper Functions ============

def get_current_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """
    获取当前用户 ID
    从请求头 X-User-ID 获取，如果没有则使用默认用户
    """
    return x_user_id or "user_anonymous"


# ============ Like Endpoints ============

@router.post("/like", response_model=SocialResponse)
async def like_work(
    request: LikeRequest,
    x_user_id: Optional[str] = Header(None)
):
    """点赞作品"""
    user_id = get_current_user_id(x_user_id)
    work_id = request.work_id
    
    success = social_storage.add_like(user_id, work_id)
    
    if success:
        count = social_storage.get_like_count(work_id)
        return SocialResponse(
            success=True,
            message="点赞成功",
            data={"count": count}
        )
    else:
        return SocialResponse(
            success=True,
            message="已经点赞过",
            data={"count": social_storage.get_like_count(work_id)}
        )


@router.post("/unlike", response_model=SocialResponse)
async def unlike_work(
    request: LikeRequest,
    x_user_id: Optional[str] = Header(None)
):
    """取消点赞"""
    user_id = get_current_user_id(x_user_id)
    work_id = request.work_id
    
    success = social_storage.remove_like(user_id, work_id)
    
    return SocialResponse(
        success=True,
        message="已取消点赞" if success else "未找到点赞记录",
        data={"count": social_storage.get_like_count(work_id)}
    )


# ============ Favorite Endpoints ============

@router.post("/favorite", response_model=SocialResponse)
async def favorite_work(
    request: FavoriteRequest,
    x_user_id: Optional[str] = Header(None)
):
    """收藏作品"""
    user_id = get_current_user_id(x_user_id)
    work_id = request.work_id
    
    success = social_storage.add_favorite(user_id, work_id)
    
    if success:
        count = social_storage.get_favorite_count(work_id)
        return SocialResponse(
            success=True,
            message="收藏成功",
            data={"count": count}
        )
    else:
        return SocialResponse(
            success=True,
            message="已经收藏过",
            data={"count": social_storage.get_favorite_count(work_id)}
        )


@router.post("/unfavorite", response_model=SocialResponse)
async def unfavorite_work(
    request: FavoriteRequest,
    x_user_id: Optional[str] = Header(None)
):
    """取消收藏"""
    user_id = get_current_user_id(x_user_id)
    work_id = request.work_id
    
    success = social_storage.remove_favorite(user_id, work_id)
    
    return SocialResponse(
        success=True,
        message="已取消收藏" if success else "未找到收藏记录",
        data={"count": social_storage.get_favorite_count(work_id)}
    )


# ============ Follow Endpoints ============

@router.post("/follow", response_model=SocialResponse)
async def follow_user(
    request: FollowRequest,
    x_user_id: Optional[str] = Header(None)
):
    """关注用户"""
    user_id = get_current_user_id(x_user_id)
    target_user_id = request.user_id
    
    if user_id == target_user_id:
        raise HTTPException(status_code=400, detail="不能关注自己")
    
    success = social_storage.add_follow(user_id, target_user_id)
    
    if success:
        count = social_storage.get_follower_count(target_user_id)
        return SocialResponse(
            success=True,
            message="关注成功",
            data={"count": count}
        )
    else:
        return SocialResponse(
            success=True,
            message="已经关注",
            data={"count": social_storage.get_follower_count(target_user_id)}
        )


@router.post("/unfollow", response_model=SocialResponse)
async def unfollow_user(
    request: FollowRequest,
    x_user_id: Optional[str] = Header(None)
):
    """取消关注"""
    user_id = get_current_user_id(x_user_id)
    target_user_id = request.user_id
    
    success = social_storage.remove_follow(user_id, target_user_id)
    
    return SocialResponse(
        success=True,
        message="已取消关注" if success else "未找到关注记录",
        data={"count": social_storage.get_follower_count(target_user_id)}
    )


# ============ Stats Endpoints ============

@router.get("/stats/{work_id}", response_model=StatsResponse)
async def get_work_stats(
    work_id: str,
    x_user_id: Optional[str] = Header(None)
):
    """获取作品统计信息"""
    user_id = get_current_user_id(x_user_id)
    
    stats = social_storage.get_work_stats(work_id)
    
    return StatsResponse(
        work_id=work_id,
        likes=stats.likes,
        favorites=stats.favorites,
        plays=stats.plays,
        is_liked=social_storage.is_liked(user_id, work_id),
        is_favorited=social_storage.is_favorited(user_id, work_id)
    )


@router.post("/play", response_model=SocialResponse)
async def record_play(
    request: LikeRequest,
    x_user_id: Optional[str] = Header(None)
):
    """记录播放（内部使用）"""
    work_id = request.work_id
    count = social_storage.increment_play(work_id)
    
    return SocialResponse(
        success=True,
        message="播放计数已更新",
        data={"count": count}
    )


# ============ Feed Endpoint ============

@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    limit: int = Query(default=20, ge=1, le=50),
    x_user_id: Optional[str] = Header(None)
):
    """
    获取个性化推荐 feed
    
    根据用户关注的用户和喜好推荐作品
    """
    user_id = get_current_user_id(x_user_id)
    
    # 获取推荐的作品 ID 列表
    work_ids = social_storage.get_user_feed(user_id, limit)
    
    # 构建 feed 项
    items = []
    for work_id in work_ids:
        stats = social_storage.get_work_stats(work_id)
        items.append(FeedItem(
            work_id=work_id,
            author_id=f"author_{work_id}",  # Mock 作者 ID
            title=f"作品 {work_id}",  # Mock 标题
            likes=stats.likes,
            favorites=stats.favorites,
            plays=stats.plays
        ))
    
    return FeedResponse(
        items=items,
        total=len(items)
    )


# ============ User Profile Endpoints ============

@router.get("/user/{user_id}/stats")
async def get_user_stats(user_id: str):
    """获取用户统计 (粉丝数/关注数)"""
    return {
        "user_id": user_id,
        "followers": social_storage.get_follower_count(user_id),
        "following": social_storage.get_following_count(user_id),
        "is_following": False  # 需要传入当前用户 ID 才能判断
    }


@router.get("/user/{user_id}/following")
async def get_user_following(user_id: str):
    """获取用户关注的用户列表"""
    following = social_storage.get_following(user_id)
    return {
        "user_id": user_id,
        "following": following,
        "total": len(following)
    }


@router.get("/user/{user_id}/followers")
async def get_user_followers(user_id: str):
    """获取用户的粉丝列表"""
    followers = social_storage.get_followers(user_id)
    return {
        "user_id": user_id,
        "followers": followers,
        "total": len(followers)
    }