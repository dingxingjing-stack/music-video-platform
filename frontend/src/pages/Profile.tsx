/**
 * Profile 页面 - 个人主页
 * 
 * 展示用户信息、作品、收藏等
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { SocialSystem } from '../components/SocialSystem';
import { User, Music, Heart, Star, Play } from 'lucide-react';

interface UserProfile {
  user_id: string;
  username: string;
  avatar?: string;
  bio?: string;
  followers: number;
  following: number;
  is_following: boolean;
}

interface Work {
  work_id: string;
  title: string;
  cover_url?: string;
  likes: number;
  favorites: number;
  plays: number;
  created_at?: string;
}

const API_BASE = 'http://localhost:8000/api/v1/social';

const getCurrentUserId = (): string => {
  let userId = localStorage.getItem('user_id');
  if (!userId) {
    userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    localStorage.setItem('user_id', userId);
  }
  return userId;
};

const getHeaders = () => ({
  'Content-Type': 'application/json',
  'X-User-ID': getCurrentUserId(),
});

type TabType = 'works' | 'favorites';

export function Profile() {
  const { userId } = useParams<{ userId: string }>();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [works, setWorks] = useState<Work[]>([]);
  const [favorites, setFavorites] = useState<Work[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>('works');
  const [loading, setLoading] = useState(true);

  const currentUserId = getCurrentUserId();
  const targetUserId = userId || currentUserId;
  const isOwnProfile = targetUserId === currentUserId;

  useEffect(() => {
    loadProfile();
    loadWorks();
  }, [targetUserId]);

  const loadProfile = async () => {
    try {
      const response = await fetch(`${API_BASE}/user/${targetUserId}/stats`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setProfile({
          user_id: targetUserId,
          username: `用户 ${targetUserId.slice(-6)}`,
          avatar: undefined,
          bio: '这个人很懒，什么都没写~',
          followers: data.followers || 0,
          following: data.following || 0,
          is_following: data.is_following || false,
        });
      } else {
        // Mock 数据
        setProfile({
          user_id: targetUserId,
          username: `用户 ${targetUserId.slice(-6)}`,
          avatar: undefined,
          bio: '这个人很懒，什么都没写~',
          followers: Math.floor(Math.random() * 1000),
          following: Math.floor(Math.random() * 100),
          is_following: false,
        });
      }
    } catch (error) {
      console.error('Failed to load profile:', error);
      setProfile({
        user_id: targetUserId,
        username: `用户 ${targetUserId.slice(-6)}`,
        avatar: undefined,
        bio: '这个人很懒，什么都没写~',
        followers: 0,
        following: 0,
        is_following: false,
      });
    }
  };

  const loadWorks = async () => {
    // Mock 作品数据
    const mockWorks: Work[] = Array.from({ length: 6 }, (_, i) => ({
      work_id: `work_${targetUserId}_${i + 1}`,
      title: `我的作品 ${i + 1}`,
      cover_url: `/covers/default_${(i % 5) + 1}.jpg`,
      likes: Math.floor(Math.random() * 500),
      favorites: Math.floor(Math.random() * 200),
      plays: Math.floor(Math.random() * 2000),
      created_at: new Date().toISOString(),
    }));
    setWorks(mockWorks);

    const mockFavorites: Work[] = Array.from({ length: 4 }, (_, i) => ({
      work_id: `fav_work_${i + 1}`,
      title: `收藏的作品 ${i + 1}`,
      cover_url: `/covers/default_${(i % 5) + 1}.jpg`,
      likes: Math.floor(Math.random() * 1000),
      favorites: Math.floor(Math.random() * 500),
      plays: Math.floor(Math.random() * 5000),
      created_at: new Date().toISOString(),
    }));
    setFavorites(mockFavorites);

    setLoading(false);
  };

  const handleFollow = async () => {
    if (!profile || isOwnProfile) return;
    try {
      const endpoint = profile.is_following ? 'unfollow' : 'follow';
      const response = await fetch(`${API_BASE}/${endpoint}`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: targetUserId }),
      });
      if (response.ok) {
        setProfile(prev => prev ? {
          ...prev,
          is_following: !prev.is_following,
          followers: prev.is_following ? Math.max(0, prev.followers - 1) : prev.followers + 1,
        } : null);
      }
    } catch (error) {
      console.error('Follow action failed:', error);
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

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* 头部 */}
      <header className="bg-gradient-to-b from-orange-900/20 to-zinc-950 border-b border-zinc-800">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="flex items-start gap-6">
            {/* 头像 */}
            <div className="w-24 h-24 rounded-full bg-zinc-800 flex items-center justify-center overflow-hidden border-2 border-orange-500/50">
              {profile?.avatar ? (
                <img src={profile.avatar} alt={profile.username} className="w-full h-full object-cover" />
              ) : (
                <User size={48} className="text-zinc-600" />
              )}
            </div>

            {/* 信息 */}
            <div className="flex-1">
              <div className="flex items-center gap-4">
                <h1 className="text-2xl font-bold">{profile?.username || '加载中...'}</h1>
                {!isOwnProfile && profile && (
                  <button
                    onClick={handleFollow}
                    className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                      profile.is_following
                        ? 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                        : 'bg-orange-600 text-white hover:bg-orange-700'
                    }`}
                  >
                    {profile.is_following ? '已关注' : '关注'}
                  </button>
                )}
              </div>
              <p className="text-zinc-400 mt-2">{profile?.bio}</p>
              
              {/* 统计 */}
              <div className="flex items-center gap-6 mt-4">
                <span className="text-zinc-400">
                  <strong className="text-zinc-100">{formatCount(profile?.following || 0)}</strong> 关注
                </span>
                <span className="text-zinc-400">
                  <strong className="text-zinc-100">{formatCount(profile?.followers || 0)}</strong> 粉丝
                </span>
                <span className="text-zinc-400">
                  <strong className="text-zinc-100">{works.length}</strong> 作品
                </span>
              </div>
            </div>
          </div>

          {/* 标签页 */}
          <div className="flex gap-6 mt-8 border-b border-zinc-800">
            <button
              onClick={() => setActiveTab('works')}
              className={`pb-3 px-2 transition-colors relative ${
                activeTab === 'works'
                  ? 'text-orange-500'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <div className="flex items-center gap-2">
                <Music size={18} />
                <span>作品</span>
              </div>
              {activeTab === 'works' && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-orange-500" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('favorites')}
              className={`pb-3 px-2 transition-colors relative ${
                activeTab === 'favorites'
                  ? 'text-orange-500'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <div className="flex items-center gap-2">
                <Heart size={18} />
                <span>收藏</span>
              </div>
              {activeTab === 'favorites' && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-orange-500" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* 内容 */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-zinc-500 animate-pulse">加载中...</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(activeTab === 'works' ? works : favorites).map((work) => (
              <article
                key={work.work_id}
                className="bg-zinc-900 rounded-lg overflow-hidden hover:bg-zinc-800/80 transition-colors group"
              >
                {/* 封面 */}
                <div className="relative aspect-square">
                  <div className="w-full h-full bg-zinc-800">
                    {work.cover_url ? (
                      <img
                        src={work.cover_url}
                        alt={work.title}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-zinc-600">
                        <Music size={48} />
                      </div>
                    )}
                  </div>
                  {/* 播放按钮 */}
                  <button className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Play size={48} className="text-white" fill="white" />
                  </button>
                </div>

                {/* 信息 */}
                <div className="p-4">
                  <h3 className="font-medium text-zinc-100 truncate">{work.title}</h3>
                  <div className="flex items-center gap-4 mt-3 text-zinc-500 text-sm">
                    <span className="flex items-center gap-1">
                      <Play size={14} />
                      {formatCount(work.plays)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Heart size={14} />
                      {formatCount(work.likes)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Star size={14} />
                      {formatCount(work.favorites)}
                    </span>
                  </div>

                  {/* 社交按钮 */}
                  <div className="mt-3 pt-3 border-t border-zinc-800">
                    <SocialSystem workId={work.work_id} />
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {(activeTab === 'works' ? works : favorites).length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            {activeTab === 'works' ? <Music size={48} className="mb-4 opacity-50" /> : <Heart size={48} className="mb-4 opacity-50" />}
            <p>暂无{activeTab === 'works' ? '作品' : '收藏'}</p>
          </div>
        )}
      </main>
    </div>
  );
}