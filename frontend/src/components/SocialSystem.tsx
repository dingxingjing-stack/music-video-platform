/**
 * SocialSystem 组件
 * 
 * 提供点赞、收藏、关注功能
 * - 点赞按钮 (心形图标 + 计数)
 * - 收藏按钮 (星形图标 + 计数)
 * - 关注按钮 (用户图标)
 */

import { useState, useEffect } from 'react';
import { Heart, Star, User, UserCheck } from 'lucide-react';

interface SocialSystemProps {
  workId: string;
  authorId?: string;
  showFollow?: boolean;
  onSocialUpdate?: (stats: SocialStats) => void;
}

export interface SocialStats {
  likes: number;
  favorites: number;
  plays: number;
  isLiked: boolean;
  isFavorited: boolean;
  isFollowing?: boolean;
}

const API_BASE = 'http://localhost:8000/api/v1/social';

// 获取当前用户 ID (从 localStorage 或生成随机 ID)
const getCurrentUserId = (): string => {
  let userId = localStorage.getItem('user_id');
  if (!userId) {
    userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    localStorage.setItem('user_id', userId);
  }
  return userId;
};

// 获取请求头
const getHeaders = () => ({
  'Content-Type': 'application/json',
  'X-User-ID': getCurrentUserId(),
});

export function SocialSystem({ workId, authorId, showFollow = false, onSocialUpdate }: SocialSystemProps) {
  const [stats, setStats] = useState<SocialStats>({
    likes: 0,
    favorites: 0,
    plays: 0,
    isLiked: false,
    isFavorited: false,
    isFollowing: false,
  });
  const [loading, setLoading] = useState(true);

  // 加载统计信息
  useEffect(() => {
    loadStats();
  }, [workId]);

  const loadStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/stats/${workId}`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setStats({
          likes: data.likes,
          favorites: data.favorites,
          plays: data.plays,
          isLiked: data.is_liked,
          isFavorited: data.is_favorited,
        });
      }
    } catch (error) {
      console.error('Failed to load social stats:', error);
    } finally {
      setLoading(false);
    }
  };

  // 点赞
  const handleLike = async () => {
    try {
      const response = await fetch(`${API_BASE}/like`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ work_id: workId }),
      });
      if (response.ok) {
        const result = await response.json();
        setStats(prev => ({
          ...prev,
          isLiked: true,
          likes: result.data?.count || prev.likes + 1,
        }));
        onSocialUpdate?.(stats);
      }
    } catch (error) {
      console.error('Like failed:', error);
    }
  };

  // 取消点赞
  const handleUnlike = async () => {
    try {
      const response = await fetch(`${API_BASE}/unlike`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ work_id: workId }),
      });
      if (response.ok) {
        const result = await response.json();
        setStats(prev => ({
          ...prev,
          isLiked: false,
          likes: result.data?.count || Math.max(0, prev.likes - 1),
        }));
        onSocialUpdate?.(stats);
      }
    } catch (error) {
      console.error('Unlike failed:', error);
    }
  };

  // 收藏
  const handleFavorite = async () => {
    try {
      const response = await fetch(`${API_BASE}/favorite`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ work_id: workId }),
      });
      if (response.ok) {
        const result = await response.json();
        setStats(prev => ({
          ...prev,
          isFavorited: true,
          favorites: result.data?.count || prev.favorites + 1,
        }));
        onSocialUpdate?.(stats);
      }
    } catch (error) {
      console.error('Favorite failed:', error);
    }
  };

  // 取消收藏
  const handleUnfavorite = async () => {
    try {
      const response = await fetch(`${API_BASE}/unfavorite`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ work_id: workId }),
      });
      if (response.ok) {
        const result = await response.json();
        setStats(prev => ({
          ...prev,
          isFavorited: false,
          favorites: result.data?.count || Math.max(0, prev.favorites - 1),
        }));
        onSocialUpdate?.(stats);
      }
    } catch (error) {
      console.error('Unfavorite failed:', error);
    }
  };

  // 关注
  const handleFollow = async () => {
    if (!authorId) return;
    try {
      const response = await fetch(`${API_BASE}/follow`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: authorId }),
      });
      if (response.ok) {
        setStats(prev => ({
          ...prev,
          isFollowing: true,
        }));
      }
    } catch (error) {
      console.error('Follow failed:', error);
    }
  };

  // 取消关注
  const handleUnfollow = async () => {
    if (!authorId) return;
    try {
      const response = await fetch(`${API_BASE}/unfollow`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: authorId }),
      });
      if (response.ok) {
        setStats(prev => ({
          ...prev,
          isFollowing: false,
        }));
      }
    } catch (error) {
      console.error('Unfollow failed:', error);
    }
  };

  const formatCount = (count: number): string => {
    if (count >= 10000) {
      return (count / 10000).toFixed(1) + 'w';
    }
    if (count >= 1000) {
      return (count / 1000).toFixed(1) + 'k';
    }
    return count.toString();
  };

  if (loading) {
    return <div className="flex gap-4 text-zinc-500">加载中...</div>;
  }

  return (
    <div className="flex items-center gap-4">
      {/* 点赞按钮 */}
      <button
        onClick={stats.isLiked ? handleUnlike : handleLike}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full transition-all ${
          stats.isLiked
            ? 'bg-red-500/20 text-red-500 hover:bg-red-500/30'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-red-400'
        }`}
      >
        <Heart
          size={18}
          fill={stats.isLiked ? 'currentColor' : 'none'}
          strokeWidth={2}
        />
        <span className="text-sm font-medium">{formatCount(stats.likes)}</span>
      </button>

      {/* 收藏按钮 */}
      <button
        onClick={stats.isFavorited ? handleUnfavorite : handleFavorite}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full transition-all ${
          stats.isFavorited
            ? 'bg-orange-500/20 text-orange-500 hover:bg-orange-500/30'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-orange-400'
        }`}
      >
        <Star
          size={18}
          fill={stats.isFavorited ? 'currentColor' : 'none'}
          strokeWidth={2}
        />
        <span className="text-sm font-medium">{formatCount(stats.favorites)}</span>
      </button>

      {/* 播放数 (只读) */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 text-zinc-400 rounded-full">
        <span className="text-sm font-medium">{formatCount(stats.plays)}</span>
        <span className="text-xs">播放</span>
      </div>

      {/* 关注按钮 */}
      {showFollow && authorId && (
        <button
          onClick={stats.isFollowing ? handleUnfollow : handleFollow}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full transition-all ${
            stats.isFollowing
              ? 'bg-orange-600 text-white hover:bg-orange-700'
              : 'bg-zinc-800 text-zinc-300 hover:bg-orange-600 hover:text-white'
          }`}
        >
          {stats.isFollowing ? (
            <>
              <UserCheck size={18} />
              <span className="text-sm font-medium">已关注</span>
            </>
          ) : (
            <>
              <User size={18} />
              <span className="text-sm font-medium">关注</span>
            </>
          )}
        </button>
      )}
    </div>
  );
}