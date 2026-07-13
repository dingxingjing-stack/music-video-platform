"""
社区排行榜服务 (Community Charts Service)

功能:
- 热门歌曲排行榜
- 播放量/点赞数统计
- 趋势算法 (新歌 + 热门)
- 用户作品展示

注意：当前使用内存 Mock 数据
正式版本需要数据库支持 (PostgreSQL/SQLite)
"""

from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import random


class CommunityTrack(BaseModel):
    """社区歌曲"""
    id: str
    title: str
    artist: str
    audio_url: str
    cover_url: Optional[str] = None
    plays: int = 0
    likes: int = 0
    comments: int = 0
    duration: int = 0
    created_at: str = ""
    genre: str = "pop"
    tags: List[str] = []
    is_trending: bool = False


class ChartResponse(BaseModel):
    """排行榜响应"""
    chart_type: str  # hot/new/trending
    tracks: List[CommunityTrack]
    updated_at: str


class CommunityService:
    """社区服务"""
    
    def __init__(self):
        # Mock 数据池
        self.mock_tracks = self._generate_mock_tracks()
    
    def _generate_mock_tracks(self) -> List[CommunityTrack]:
        """生成 Mock 歌曲数据"""
        base_tracks = [
            {
                "title": "夏日午后",
                "artist": "AI Musician",
                "genre": "pop",
                "plays": 15234,
                "likes": 892,
            },
            {
                "title": "午夜爵士",
                "artist": "Jazz Bot",
                "genre": "jazz",
                "plays": 8921,
                "likes": 654,
            },
            {
                "title": "电子梦境",
                "artist": "Synth AI",
                "genre": "electronic",
                "plays": 23456,
                "likes": 1523,
            },
            {
                "title": "摇滚之夜",
                "artist": "Rock Generator",
                "genre": "rock",
                "plays": 12890,
                "likes": 876,
            },
            {
                "title": "古典印象",
                "artist": "Classical AI",
                "genre": "classical",
                "plays": 5432,
                "likes": 432,
            },
            {
                "title": "嘻哈节奏",
                "artist": "Beat Master",
                "genre": "hip-hop",
                "plays": 18765,
                "likes": 1234,
            },
            {
                "title": "氛围空间",
                "artist": "Ambient Dreams",
                "genre": "ambient",
                "plays": 7654,
                "likes": 543,
            },
            {
                "title": "电影配乐",
                "artist": "Cinematic AI",
                "genre": "cinematic",
                "plays": 9876,
                "likes": 765,
            },
            {
                "title": "Lo-Fi 学习",
                "artist": "Chill Beats",
                "genre": "lo-fi",
                "plays": 34567,
                "likes": 2345,
            },
            {
                "title": "R&B 灵魂",
                "artist": "Soul Singer",
                "genre": "r&b",
                "plays": 11234,
                "likes": 891,
            },
        ]
        
        tracks = []
        for i, t in enumerate(base_tracks):
            tracks.append(CommunityTrack(
                id=f"track_{i+1}",
                title=t["title"],
                artist=t["artist"],
                audio_url=f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{(i % 10) + 1}.mp3",
                cover_url=None,
                plays=t["plays"],
                likes=t["likes"],
                comments=random.randint(50, 500),
                duration=random.randint(120, 240),
                created_at=(datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
                genre=t["genre"],
                tags=[t["genre"], "AI Music", "Generated"],
                is_trending=t["plays"] > 10000,
            ))
        
        return tracks
    
    def get_hot_chart(self, limit: int = 20) -> List[CommunityTrack]:
        """获取热门排行榜 (按播放量)"""
        sorted_tracks = sorted(self.mock_tracks, key=lambda t: t.plays, reverse=True)
        return sorted_tracks[:limit]
    
    def get_new_chart(self, limit: int = 20) -> List[CommunityTrack]:
        """获取新歌榜 (按创建时间)"""
        sorted_tracks = sorted(
            self.mock_tracks,
            key=lambda t: t.created_at,
            reverse=True
        )
        return sorted_tracks[:limit]
    
    def get_trending_chart(self, limit: int = 20) -> List[CommunityTrack]:
        """获取趋势榜 (播放量增长率)"""
        # 简单算法：播放量 * 0.7 + 点赞数*100 * 0.3
        scored_tracks = [
            (t, t.plays * 0.7 + t.likes * 100 * 0.3)
            for t in self.mock_tracks
        ]
        sorted_tracks = sorted(scored_tracks, key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tracks][:limit]
    
    def search_tracks(self, query: str, genre: Optional[str] = None) -> List[CommunityTrack]:
        """搜索歌曲"""
        results = [
            t for t in self.mock_tracks
            if query.lower() in t.title.lower() or query.lower() in t.artist.lower()
        ]
        if genre:
            results = [t for t in results if t.genre == genre]
        return results
    
    def get_tracks_by_genre(self, genre: str, limit: int = 20) -> List[CommunityTrack]:
        """按风格筛选"""
        filtered = [t for t in self.mock_tracks if t.genre == genre]
        return sorted(filtered, key=lambda t: t.plays, reverse=True)[:limit]
    
    def like_track(self, track_id: str) -> int:
        """点赞歌曲"""
        track = next((t for t in self.mock_tracks if t.id == track_id), None)
        if track:
            track.likes += 1
            return track.likes
        return 0
    
    def play_track(self, track_id: str) -> int:
        """增加播放量"""
        track = next((t for t in self.mock_tracks if t.id == track_id), None)
        if track:
            track.plays += 1
            return track.plays
        return 0


# 全局服务实例
community_service = CommunityService()