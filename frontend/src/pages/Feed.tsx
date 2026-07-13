/**
 * Feed 页面 - 个性化推荐
 * 
 * 展示用户个性化推荐的作品流
 */

import { useState, useEffect } from 'react';
import { SocialSystem } from '../components/SocialSystem';
import { Play, Music, Heart, Star } from 'lucide-react';

interface FeedItem {
  work_id: string;
  author_id: string;
  title: string;
  likes: number;
  favorites: number;
  plays: number;
  cover_url?: string;
  audio_url?: string;
  duration?: number;
}

interface FeedResponse {
  items: FeedItem[];
  total: number;
}

const API_BASE = 'http://localhost:8000/api/v1/social';

// 获取当前用户 ID
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

export function Feed() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPlaying, setCurrentPlaying] = useState<string | null>(null);

  useEffect(() => {
    loadFeed();
  }, []);

  const loadFeed = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/feed?limit=20`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        const data: FeedResponse = await response.json();
        // Mock 数据补充 (因为后端返回的是 mock 数据)
        const enrichedItems = data.items.map((item, index) => ({
          ...item,
          title: `推荐作品 ${index + 1}`,
          cover_url: `/covers/default_${(index % 5) + 1}.jpg`,
          audio_url: `/audio/demo_${(index % 3) + 1}.mp3`,
          duration: 180 + index * 10,
        }));
        setItems(enrichedItems);
      } else {
        // 使用 mock 数据
        setItems(generateMockFeed());
      }
    } catch (error) {
      console.error('Failed to load feed:', error);
      setItems(generateMockFeed());
    } finally {
      setLoading(false);
    }
  };

  const generateMockFeed = (): FeedItem[] => {
    return Array.from({ length: 10 }, (_, i) => ({
      work_id: `work_${i + 1}`,
      author_id: `author_${(i % 3) + 1}`,
      title: `推荐作品 ${i + 1}`,
      likes: Math.floor(Math.random() * 1000),
      favorites: Math.floor(Math.random() * 500),
      plays: Math.floor(Math.random() * 5000),
      cover_url: `/covers/default_${(i % 5) + 1}.jpg`,
      audio_url: `/audio/demo_${(i % 3) + 1}.mp3`,
      duration: 180 + i * 10,
    }));
  };

  const handlePlay = (workId: string) => {
    if (currentPlaying === workId) {
      setCurrentPlaying(null);
    } else {
      setCurrentPlaying(workId);
      // 这里可以集成音频播放器
      console.log('Playing:', workId);
    }
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
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
      <header className="sticky top-0 z-10 bg-zinc-900/80 backdrop-blur-sm border-b border-zinc-800">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold text-orange-500">个性化推荐</h1>
          <p className="text-zinc-400 text-sm mt-1">根据你的喜好推荐的音乐作品</p>
        </div>
      </header>

      {/* 内容 */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-zinc-500 animate-pulse">加载中...</div>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            <Music size={48} className="mb-4 opacity-50" />
            <p>暂无推荐作品</p>
            <p className="text-sm mt-2">先去探索更多音乐吧~</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {items.map((item) => (
              <article
                key={item.work_id}
                className="bg-zinc-900 rounded-lg p-4 hover:bg-zinc-800/80 transition-colors"
              >
                <div className="flex gap-4">
                  {/* 封面 */}
                  <div className="relative w-32 h-32 flex-shrink-0">
                    <div className="w-full h-full bg-zinc-800 rounded-md overflow-hidden">
                      {item.cover_url ? (
                        <img
                          src={item.cover_url}
                          alt={item.title}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-zinc-600">
                          <Music size={32} />
                        </div>
                      )}
                    </div>
                    {/* 播放按钮 */}
                    <button
                      onClick={() => handlePlay(item.work_id)}
                      className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 hover:opacity-100 transition-opacity"
                    >
                      <Play size={32} className="text-white" fill="white" />
                    </button>
                    {/* 播放状态 */}
                    {currentPlaying === item.work_id && (
                      <div className="absolute bottom-2 right-2 flex gap-0.5">
                        {[1, 2, 3, 4].map((bar) => (
                          <div
                            key={bar}
                            className="w-1 bg-orange-500 rounded-full animate-pulse"
                            style={{
                              height: `${8 + Math.random() * 8}px`,
                              animationDelay: `${bar * 0.1}s`,
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>

                  {/* 信息 */}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-zinc-100 truncate">
                      {item.title}
                    </h3>
                    <p className="text-zinc-400 text-sm mt-1">
                      作者：{item.author_id}
                    </p>

                    {/* 统计 */}
                    <div className="flex items-center gap-4 mt-3 text-zinc-500 text-sm">
                      <span className="flex items-center gap-1">
                        <Play size={14} />
                        {formatCount(item.plays)} 播放
                      </span>
                      <span className="flex items-center gap-1">
                        <Heart size={14} />
                        {formatCount(item.likes)} 点赞
                      </span>
                      <span className="flex items-center gap-1">
                        <Star size={14} />
                        {formatCount(item.favorites)} 收藏
                      </span>
                      {item.duration && (
                        <span className="text-zinc-600">
                          {formatDuration(item.duration)}
                        </span>
                      )}
                    </div>

                    {/* 社交按钮 */}
                    <div className="mt-4">
                      <SocialSystem
                        workId={item.work_id}
                        authorId={item.author_id}
                        showFollow
                      />
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}