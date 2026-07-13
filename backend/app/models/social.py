"""
社交系统数据模型 (Social System Models)

数据模型:
- Like: 点赞 (user_id, work_id, created_at)
- Favorite: 收藏 (user_id, work_id, created_at)
- Follow: 关注 (follower_id, followed_id, created_at)

使用 Mock 内存存储 (后续可接数据库)
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class Like(BaseModel):
    """点赞记录"""
    user_id: str = Field(..., description="用户 ID")
    work_id: str = Field(..., description="作品 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class Favorite(BaseModel):
    """收藏记录"""
    user_id: str = Field(..., description="用户 ID")
    work_id: str = Field(..., description="作品 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class Follow(BaseModel):
    """关注记录"""
    follower_id: str = Field(..., description="关注者 ID")
    followed_id: str = Field(..., description="被关注者 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class WorkStats(BaseModel):
    """作品统计"""
    work_id: str = Field(..., description="作品 ID")
    likes: int = Field(default=0, description="点赞数")
    favorites: int = Field(default=0, description="收藏数")
    plays: int = Field(default=0, description="播放数")


class SocialStorage:
    """
    Mock 内存存储类
    
    提供点赞、收藏、关注的内存存储功能
    后续可替换为数据库存储
    """
    
    def __init__(self):
        # 点赞存储：{work_id: {user_id: Like}}
        self.likes: Dict[str, Dict[str, Like]] = {}
        # 收藏存储：{work_id: {user_id: Favorite}}
        self.favorites: Dict[str, Dict[str, Favorite]] = {}
        # 关注存储：{followed_id: {follower_id: Follow}}
        self.follows: Dict[str, Dict[str, Follow]] = {}
        # 播放计数：{work_id: count}
        self.plays: Dict[str, int] = {}
    
    def add_like(self, user_id: str, work_id: str) -> bool:
        """添加点赞"""
        if work_id not in self.likes:
            self.likes[work_id] = {}
        if user_id not in self.likes[work_id]:
            self.likes[work_id][user_id] = Like(user_id=user_id, work_id=work_id)
            return True
        return False
    
    def remove_like(self, user_id: str, work_id: str) -> bool:
        """取消点赞"""
        if work_id in self.likes and user_id in self.likes[work_id]:
            del self.likes[work_id][user_id]
            return True
        return False
    
    def is_liked(self, user_id: str, work_id: str) -> bool:
        """检查是否已点赞"""
        return work_id in self.likes and user_id in self.likes.get(work_id, {})
    
    def get_like_count(self, work_id: str) -> int:
        """获取点赞数"""
        return len(self.likes.get(work_id, {}))
    
    def add_favorite(self, user_id: str, work_id: str) -> bool:
        """添加收藏"""
        if work_id not in self.favorites:
            self.favorites[work_id] = {}
        if user_id not in self.favorites[work_id]:
            self.favorites[work_id][user_id] = Favorite(user_id=user_id, work_id=work_id)
            return True
        return False
    
    def remove_favorite(self, user_id: str, work_id: str) -> bool:
        """取消收藏"""
        if work_id in self.favorites and user_id in self.favorites[work_id]:
            del self.favorites[work_id][user_id]
            return True
        return False
    
    def is_favorited(self, user_id: str, work_id: str) -> bool:
        """检查是否已收藏"""
        return work_id in self.favorites and user_id in self.favorites.get(work_id, {})
    
    def get_favorite_count(self, work_id: str) -> int:
        """获取收藏数"""
        return len(self.favorites.get(work_id, {}))
    
    def add_follow(self, follower_id: str, followed_id: str) -> bool:
        """添加关注"""
        if follower_id == followed_id:
            return False  # 不能关注自己
        if followed_id not in self.follows:
            self.follows[followed_id] = {}
        if follower_id not in self.follows[followed_id]:
            self.follows[followed_id][follower_id] = Follow(
                follower_id=follower_id,
                followed_id=followed_id
            )
            return True
        return False
    
    def remove_follow(self, follower_id: str, followed_id: str) -> bool:
        """取消关注"""
        if followed_id in self.follows and follower_id in self.follows[followed_id]:
            del self.follows[followed_id][follower_id]
            return True
        return False
    
    def is_following(self, follower_id: str, followed_id: str) -> bool:
        """检查是否已关注"""
        return followed_id in self.follows and follower_id in self.follows.get(followed_id, {})
    
    def get_follower_count(self, user_id: str) -> int:
        """获取粉丝数"""
        return len(self.follows.get(user_id, {}))
    
    def get_following_count(self, user_id: str) -> int:
        """获取关注数"""
        count = 0
        for follows in self.follows.values():
            if user_id in follows:
                count += 1
        return count
    
    def get_following(self, user_id: str) -> List[str]:
        """获取用户关注的用户 ID 列表"""
        following = []
        for followed_id, follows in self.follows.items():
            if user_id in follows:
                following.append(followed_id)
        return following
    
    def get_followers(self, user_id: str) -> List[str]:
        """获取用户的粉丝 ID 列表"""
        return list(self.follows.get(user_id, {}).keys())
    
    def increment_play(self, work_id: str) -> int:
        """增加播放计数"""
        self.plays[work_id] = self.plays.get(work_id, 0) + 1
        return self.plays[work_id]
    
    def get_play_count(self, work_id: str) -> int:
        """获取播放数"""
        return self.plays.get(work_id, 0)
    
    def get_work_stats(self, work_id: str) -> WorkStats:
        """获取作品统计"""
        return WorkStats(
            work_id=work_id,
            likes=self.get_like_count(work_id),
            favorites=self.get_favorite_count(work_id),
            plays=self.get_play_count(work_id)
        )
    
    def get_user_feed(self, user_id: str, limit: int = 20) -> List[str]:
        """
        获取个性化推荐 feed
        返回用户关注的用户发布的作品 ID 列表
        """
        # 获取用户关注的用户
        following = self.get_following(user_id)
        # 简单实现：返回所有作品（后续可根据算法优化）
        # 这里返回所有作品 ID，实际应按时间排序并限制数量
        all_works = set(self.likes.keys()) | set(self.favorites.keys()) | set(self.plays.keys())
        return list(all_works)[:limit]


# 全局存储实例
social_storage = SocialStorage()