/**
 * CommunityFeed — 社区/发现页面（类似 Suno feed）
 */

import { useState, useEffect, useCallback } from 'react';

interface TrackPost {
  id: string;
  title: string;
  artist: string;
  avatar?: string;
  coverArt?: string;
  duration: number; // seconds
  plays: number;
  likes: number;
  tags: string[];
  createdAt: number;
  audioUrl?: string;
  isLiked: boolean;
}

const MOCK_POSTS: TrackPost[] = [
  {
    id: '1',
    title: '夏日微风',
    artist: '音乐人 A',
    coverArt: 'https://picsum.photos/seed/summer/400/400',
    duration: 185,
    plays: 12340,
    likes: 856,
    tags: ['流行', '夏日', '轻松'],
    createdAt: Date.now() - 3600000,
    isLiked: false,
  },
  {
    id: '2',
    title: '深夜代码',
    artist: '音乐人 B',
    coverArt: 'https://picsum.photos/seed/night/400/400',
    duration: 245,
    plays: 8920,
    likes: 642,
    tags: ['电子', '专注', '氛围'],
    createdAt: Date.now() - 7200000,
    isLiked: true,
  },
  {
    id: '3',
    title: '晨跑节奏',
    artist: '音乐人 C',
    coverArt: 'https://picsum.photos/seed/morning/400/400',
    duration: 198,
    plays: 15670,
    likes: 1024,
    tags: ['摇滚', '运动', '能量'],
    createdAt: Date.now() - 86400000,
    isLiked: false,
  },
  {
    id: '4',
    title: '雨后咖啡馆',
    artist: '音乐人 D',
    coverArt: 'https://picsum.photos/seed/cafe/400/400',
    duration: 210,
    plays: 6780,
    likes: 445,
    tags: ['爵士', '放松', '雨天'],
    createdAt: Date.now() - 172800000,
    isLiked: false,
  },
];

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatTimeAgo(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  
  if (hours < 1) return '刚刚';
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return new Date(timestamp).toLocaleDateString();
}

export function CommunityFeed() {
  const [posts, setPosts] = useState<TrackPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('全部');
  const [playingId, setPlayingId] = useState<string | null>(null);

  // 加载帖子
  useEffect(() => {
    // Mock 加载延迟
    const timer = setTimeout(() => {
      setPosts(MOCK_POSTS);
      setLoading(false);
    }, 800);
    return () => clearTimeout(timer);
  }, []);

  // 点赞/取消点赞
  const toggleLike = useCallback((postId: string) => {
    setPosts(posts => posts.map(post => {
      if (post.id !== postId) return post;
      return {
        ...post,
        isLiked: !post.isLiked,
        likes: post.isLiked ? post.likes - 1 : post.likes + 1,
      };
    }));
  }, []);

  // 播放/暂停
  const togglePlay = useCallback((postId: string) => {
    setPlayingId(current => current === postId ? null : postId);
  }, []);

  // 过滤标签
  const allTags = ['全部', ...new Set(posts.flatMap(p => p.tags))];
  const filteredPosts = filter === '全部' 
    ? posts 
    : posts.filter(p => p.tags.includes(filter));

  return (
    <div className="min-h-screen bg-[#121212]">
      {/* 头部 */}
      <div className="sticky top-0 z-10 bg-[#121212]/95 backdrop-blur border-b border-[#2a2a2a]">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[#e0e0e0]">🌍 发现</h1>
              <p className="text-xs text-[#777777] mt-1">探索社区创作的优秀作品</p>
            </div>
            <button className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition">
              ✨ 发布作品
            </button>
          </div>

          {/* 标签过滤 */}
          <div className="flex gap-2 mt-4 overflow-x-auto pb-2">
            {allTags.slice(0, 10).map(tag => (
              <button
                key={tag}
                onClick={() => setFilter(tag)}
                className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition ${
                  filter === tag
                    ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                    : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333]'
                }`}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 内容区 */}
      <div className="max-w-6xl mx-auto px-4 py-6">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="bg-[#1e1e1e] rounded-xl p-4 animate-pulse">
                <div className="aspect-square bg-[#2a2a2a] rounded-lg mb-4" />
                <div className="h-4 bg-[#2a2a2a] rounded w-3/4 mb-2" />
                <div className="h-3 bg-[#2a2a2a] rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : filteredPosts.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-[#777777]">暂无内容</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredPosts.map(post => (
              <div
                key={post.id}
                className="group bg-[#1e1e1e] rounded-xl overflow-hidden border border-[#2a2a2a] hover:border-[#3a3a3a] transition"
              >
                {/* 封面 */}
                <div className="relative aspect-square overflow-hidden">
                  <img
                    src={post.coverArt}
                    alt={post.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                  {/* 播放按钮 */}
                  <button
                    onClick={() => togglePlay(post.id)}
                    className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition"
                  >
                    <div className="w-14 h-14 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full flex items-center justify-center">
                      {playingId === post.id ? (
                        <span className="text-2xl">⏸️</span>
                      ) : (
                        <span className="text-2xl ml-1">▶️</span>
                      )}
                    </div>
                  </button>
                  {/* 时长 */}
                  <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/70 rounded text-xs text-white">
                    {formatDuration(post.duration)}
                  </div>
                </div>

                {/* 信息 */}
                <div className="p-4">
                  <h3 className="text-base font-semibold text-[#e0e0e0] mb-1 truncate">
                    {post.title}
                  </h3>
                  <p className="text-sm text-[#777777] mb-3">{post.artist}</p>

                  {/* 标签 */}
                  <div className="flex flex-wrap gap-1 mb-3">
                    {post.tags.slice(0, 3).map(tag => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 bg-[#2a2a2a] text-[#777777] text-xs rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  {/* 统计 */}
                  <div className="flex items-center justify-between text-xs text-[#777777]">
                    <div className="flex items-center gap-3">
                      <span>🎧 {formatNumber(post.plays)}</span>
                      <button
                        onClick={() => toggleLike(post.id)}
                        className={`flex items-center gap-1 transition ${
                          post.isLiked ? 'text-pink-500' : 'hover:text-pink-500'
                        }`}
                      >
                        <span>{post.isLiked ? '❤️' : '🤍'}</span>
                        <span>{formatNumber(post.likes)}</span>
                      </button>
                    </div>
                    <span>{formatTimeAgo(post.createdAt)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 播放条 */}
      {playingId && (
        <div className="fixed bottom-0 left-0 right-0 bg-[#1e1e1e]/95 backdrop-blur border-t border-[#2a2a2a] p-4">
          <div className="max-w-6xl mx-auto flex items-center gap-4">
            <button
              onClick={() => setPlayingId(null)}
              className="w-10 h-10 bg-[#2a2a2a] hover:bg-[#333333] rounded-full flex items-center justify-center"
            >
              ⏸️
            </button>
            <div className="flex-1">
              <div className="h-1 bg-[#2a2a2a] rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-orange-500 to-pink-500 w-1/3" />
              </div>
            </div>
            <span className="text-xs text-[#777777]">1:23 / 3:45</span>
          </div>
        </div>
      )}
    </div>
  );
}