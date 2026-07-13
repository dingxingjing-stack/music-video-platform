/**
 * 素材库页面 - 展示和管理免费素材
 * 
 * 功能:
 * - 按分类浏览
 * - 搜索和过滤
 * - 预览和收藏
 * - 一键使用到 MV 项目
 */

import { useState, useMemo } from 'react';
import { StockVideo, StockCategory } from '../../types';

// Mock 数据 (实际应从 API 获取)
const MOCK_CATEGORIES: StockCategory[] = [
  { id: 'nature', name: '自然风景', icon: '🌲', count: 10 },
  { id: 'city', name: '城市建筑', icon: '🏙️', count: 10 },
  { id: 'people', name: '人物活动', icon: '👥', count: 10 },
  { id: 'technology', name: '科技数码', icon: '💻', count: 10 },
  { id: 'abstract', name: '抽象艺术', icon: '🎨', count: 10 },
  { id: 'music', name: '音乐演出', icon: '🎵', count: 10 },
  { id: 'sports', name: '运动健身', icon: '⚽', count: 10 },
  { id: 'food', name: '美食餐饮', icon: '🍔', count: 10 },
  { id: 'travel', name: '旅行度假', icon: '✈️', count: 10 },
  { id: 'emotions', name: '情绪氛围', icon: '❤️', count: 10 }
];

const MOCK_VIDEOS: StockVideo[] = Array.from({ length: 100 }, (_, i) => {
  const category = MOCK_CATEGORIES[i % MOCK_CATEGORIES.length];
  return {
    id: `stock-${i}`,
    title: `${category.name} 素材 ${i + 1}`,
    category: category.id,
    thumbnail: `/assets/stock/${category.id}/thumb_${i}.jpg`,
    previewUrl: `/assets/stock/${category.id}/video_${i}.mp4`,
    duration: Math.floor(Math.random() * 30) + 5,
    width: 1920,
    height: 1080,
    tags: [category.name, 'free', 'hd'],
    source: i % 2 === 0 ? 'pexels' : 'pixabay',
    license: 'Free'
  };
});

interface StockLibraryProps {
  onUseVideo?: (video: StockVideo) => void;
}

export default function StockLibrary({ onUseVideo }: StockLibraryProps) {
  const [selectedCategory, setSelectedCategory] = useState<string | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [favorites, setFavorites] = useState<Set<string>>(new Set());

  // 过滤素材
  const filteredVideos = useMemo(() => {
    return MOCK_VIDEOS.filter(video => {
      const matchCategory = selectedCategory === 'all' || video.category === selectedCategory;
      const matchSearch = !searchQuery || 
        video.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        video.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchCategory && matchSearch;
    });
  }, [selectedCategory, searchQuery]);

  // 收藏切换
  const toggleFavorite = (videoId: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(videoId)) {
        next.delete(videoId);
      } else {
        next.add(videoId);
      }
      return next;
    });
  };

  // 使用素材
  const handleUseVideo = (video: StockVideo) => {
    if (onUseVideo) {
      onUseVideo(video);
    } else {
      alert(`已选择：${video.title}`);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-white p-6">
      {/* 头部 */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">📚 免费素材库</h1>
        <p className="text-gray-400 mb-6">
          100+ 免费高清视频素材，来自 Pexels & Pixabay，可用于商业用途
        </p>

        {/* 搜索栏 */}
        <div className="flex gap-4 mb-6">
          <input
            type="text"
            placeholder="搜索素材..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-[#1a1a1a] border border-gray-700 rounded-full px-6 py-3 focus:outline-none focus:border-orange-500"
          />
          <button
            onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}
            className="px-4 py-3 bg-[#1a1a1a] border border-gray-700 rounded-full hover:border-orange-500"
          >
            {viewMode === 'grid' ? '📋' : '📱'}
          </button>
        </div>

        {/* 分类标签 */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => setSelectedCategory('all')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
              selectedCategory === 'all'
                ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                : 'bg-[#1a1a1a] text-gray-400 hover:text-white'
            }`}
          >
            全部 ({MOCK_VIDEOS.length})
          </button>
          {MOCK_CATEGORIES.map(cat => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                selectedCategory === cat.id
                  ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                  : 'bg-[#1a1a1a] text-gray-400 hover:text-white'
              }`}
            >
              {cat.icon} {cat.name} ({cat.count})
            </button>
          ))}
        </div>
      </div>

      {/* 素材网格 */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {filteredVideos.map(video => (
            <VideoCard
              key={video.id}
              video={video}
              isFavorite={favorites.has(video.id)}
              onToggleFavorite={() => toggleFavorite(video.id)}
              onUseVideo={() => handleUseVideo(video)}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredVideos.map(video => (
            <VideoListItem
              key={video.id}
              video={video}
              isFavorite={favorites.has(video.id)}
              onToggleFavorite={() => toggleFavorite(video.id)}
              onUseVideo={() => handleUseVideo(video)}
            />
          ))}
        </div>
      )}

      {/* 结果统计 */}
      <div className="mt-8 text-center text-gray-400">
        显示 {filteredVideos.length} / {MOCK_VIDEOS.length} 个素材
      </div>
    </div>
  );
}

// ========== 视频卡片组件 ==========

interface VideoCardProps {
  video: StockVideo;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onUseVideo: () => void;
}

function VideoCard({ video, isFavorite, onToggleFavorite, onUseVideo }: VideoCardProps) {
  return (
    <div className="bg-[#1a1a1a] rounded-lg overflow-hidden hover:scale-105 transition-transform group">
      {/* 缩略图 */}
      <div className="relative aspect-video bg-gray-800">
        <img
          src={video.thumbnail}
          alt={video.title}
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = 'https://via.placeholder.com/320x180?text=Preview';
          }}
        />
        
        {/* 时长标签 */}
        <div className="absolute bottom-2 right-2 bg-black bg-opacity-75 text-white text-xs px-2 py-1 rounded">
          {video.duration}s
        </div>

        {/* 收藏按钮 */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite();
          }}
          className="absolute top-2 right-2 p-2 bg-black bg-opacity-50 rounded-full hover:bg-opacity-75"
        >
          {isFavorite ? '❤️' : '🤍'}
        </button>

        {/* 悬停遮罩 */}
        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-50 transition-all flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
          <button
            onClick={onUseVideo}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-sm font-medium hover:scale-110 transition-transform"
          >
            使用
          </button>
        </div>
      </div>

      {/* 信息 */}
      <div className="p-3">
        <h3 className="text-sm font-medium truncate mb-1">{video.title}</h3>
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>{video.width}x{video.height}</span>
          <span className="capitalize">{video.source}</span>
        </div>
      </div>
    </div>
  );
}

// ========== 视频列表项组件 ==========

interface VideoListItemProps {
  video: StockVideo;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onUseVideo: () => void;
}

function VideoListItem({ video, isFavorite, onToggleFavorite, onUseVideo }: VideoListItemProps) {
  return (
    <div className="flex items-center gap-4 p-4 bg-[#1a1a1a] rounded-lg hover:bg-[#222] transition-colors">
      {/* 缩略图 */}
      <div className="relative w-40 aspect-video bg-gray-800 rounded overflow-hidden flex-shrink-0">
        <img
          src={video.thumbnail}
          alt={video.title}
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = 'https://via.placeholder.com/160x90?text=Preview';
          }}
        />
        <div className="absolute bottom-1 right-1 bg-black bg-opacity-75 text-white text-xs px-1 py-0.5 rounded">
          {video.duration}s
        </div>
      </div>

      {/* 信息 */}
      <div className="flex-1 min-w-0">
        <h3 className="text-base font-medium truncate mb-1">{video.title}</h3>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <span>{video.width}x{video.height}</span>
          <span>{video.duration}s</span>
          <span className="capitalize">{video.source}</span>
          <div className="flex gap-1">
            {video.tags.slice(0, 3).map(tag => (
              <span key={tag} className="px-2 py-0.5 bg-gray-700 rounded text-xs">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 操作 */}
      <div className="flex items-center gap-2">
        <button
          onClick={onToggleFavorite}
          className="p-2 hover:bg-gray-700 rounded-full"
        >
          {isFavorite ? '❤️' : '🤍'}
        </button>
        <button
          onClick={onUseVideo}
          className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-sm font-medium hover:scale-105 transition-transform"
        >
          使用
        </button>
      </div>
    </div>
  );
}