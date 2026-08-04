/**
 * 视频素材库组件（增强版）
 * 
 * 功能：
 * - 浏览 500+ 免费视频素材（Pexels/Pixabay/Mixkit）
 * - 搜索/筛选（分类/时长/分辨率）
 * - 分页/无限滚动
 * - 预览
 * - 添加到时间轴
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { StockVideo } from '../types/video-sync';
import { STOCK_VIDEOS, STOCK_VIDEO_CATEGORIES } from '../data/stock-videos';

interface Props {
  onVideoSelect: (video: StockVideo) => void;
}

// 分页配置
const PAGE_SIZE = 20; // 每页显示 20 个视频

// 时长选项
const DURATION_OPTIONS = [
  { label: '任意时长', value: 'all' },
  { label: '短 (<10s)', value: 'short' },
  { label: '中 (10-20s)', value: 'medium' },
  { label: '长 (>20s)', value: 'long' },
];

// 分辨率选项
const RESOLUTION_OPTIONS = [
  { label: '任意分辨率', value: 'all' },
  { label: '1080p', value: '1080p' },
  { label: '4K', value: '4K' },
];

// 帧率选项
const FPS_OPTIONS = [
  { label: '任意帧率', value: 'all' },
  { label: '24 fps', value: '24' },
  { label: '30 fps', value: '30' },
  { label: '60 fps', value: '60' },
];

export function StockVideoLibrary({ onVideoSelect }: Props) {
  // 数据状态
  const [videos, setVideos] = useState<StockVideo[]>([]);
  const [filteredVideos, setFilteredVideos] = useState<StockVideo[]>([]);
  
  // 搜索和筛选状态
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('全部');
  const [selectedDuration, setSelectedDuration] = useState<string>('all');
  const [selectedResolution, setSelectedResolution] = useState<string>('all');
  const [selectedFps, setSelectedFps] = useState<string>('all');
  
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  
  // 预览状态
  const [previewVideo, setPreviewVideo] = useState<StockVideo | null>(null);
  
  // 无限滚动引用
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  // 初始化加载数据
  useEffect(() => {
    loadVideos();
  }, []);

  const loadVideos = async () => {
    setLoading(true);
    // 模拟 API 延迟
    await new Promise(resolve => setTimeout(resolve, 300));
    setVideos(STOCK_VIDEOS);
    setFilteredVideos(STOCK_VIDEOS);
    setLoading(false);
    console.log(`加载了 ${STOCK_VIDEOS.length} 个视频素材`);
  };

  // 筛选逻辑
  const applyFilters = useCallback(() => {
    let result = [...STOCK_VIDEOS];
    
    // 搜索过滤
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      result = result.filter(video => 
        video.title.toLowerCase().includes(term) ||
        video.description.toLowerCase().includes(term) ||
        video.tags.some(tag => tag.toLowerCase().includes(term))
      );
    }
    
    // 分类过滤
    if (selectedCategory !== '全部') {
      result = result.filter(video => video.category === selectedCategory);
    }
    
    // 时长过滤
    if (selectedDuration !== 'all') {
      result = result.filter(video => {
        if (selectedDuration === 'short') return video.duration < 10;
        if (selectedDuration === 'medium') return video.duration >= 10 && video.duration <= 20;
        if (selectedDuration === 'long') return video.duration > 20;
        return true;
      });
    }
    
    // 分辨率过滤
    if (selectedResolution !== 'all') {
      result = result.filter(video => video.resolution === selectedResolution);
    }
    
    // 帧率过滤
    if (selectedFps !== 'all') {
      result = result.filter(video => video.fps === parseInt(selectedFps));
    }
    
    setFilteredVideos(result);
    setCurrentPage(1); // 重置到第一页
  }, [searchTerm, selectedCategory, selectedDuration, selectedResolution, selectedFps]);

  // 应用筛选
  useEffect(() => {
    applyFilters();
  }, [applyFilters]);

  // 计算当前页的视频
  const totalPages = Math.ceil(filteredVideos.length / PAGE_SIZE);
  const currentPageVideos = filteredVideos.slice(0, currentPage * PAGE_SIZE);
  
  // 检查是否还有更多
  useEffect(() => {
    setHasMore(currentPage < totalPages);
  }, [currentPage, totalPages]);

  // 无限滚动观察者
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          setCurrentPage(prev => prev + 1);
        }
      },
      { threshold: 0.1, rootMargin: '100px' }
    );

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [hasMore, loading]);

  // 重置筛选
  const handleResetFilters = () => {
    setSearchTerm('');
    setSelectedCategory('全部');
    setSelectedDuration('all');
    setSelectedResolution('all');
    setSelectedFps('all');
    setCurrentPage(1);
  };

  // 添加到时间轴
  const handleAddToTimeline = (video: StockVideo) => {
    onVideoSelect(video);
  };

  // 渲染筛选器
  const renderFilters = () => (
    <div className="space-y-3">
      {/* 搜索栏 */}
      <div className="flex gap-2">
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="搜索素材（标题/描述/标签）..."
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm border border-gray-700 focus:border-orange-500 focus:outline-none"
        />
      </div>
      
      {/* 分类选择 */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400 text-xs whitespace-nowrap">分类:</span>
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm border border-gray-700 focus:border-orange-500 focus:outline-none"
        >
          {STOCK_VIDEO_CATEGORIES.map(cat => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>
      
      {/* 时长选择 */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400 text-xs whitespace-nowrap">时长:</span>
        <select
          value={selectedDuration}
          onChange={(e) => setSelectedDuration(e.target.value)}
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm border border-gray-700 focus:border-orange-500 focus:outline-none"
        >
          {DURATION_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      
      {/* 分辨率选择 */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400 text-xs whitespace-nowrap">分辨率:</span>
        <select
          value={selectedResolution}
          onChange={(e) => setSelectedResolution(e.target.value)}
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm border border-gray-700 focus:border-orange-500 focus:outline-none"
        >
          {RESOLUTION_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      
      {/* 帧率选择 */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400 text-xs whitespace-nowrap">帧率:</span>
        <select
          value={selectedFps}
          onChange={(e) => setSelectedFps(e.target.value)}
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm border border-gray-700 focus:border-orange-500 focus:outline-none"
        >
          {FPS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      
      {/* 重置按钮 */}
      <button
        onClick={handleResetFilters}
        className="w-full py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition"
      >
        重置筛选
      </button>
      
      {/* 结果统计 */}
      <div className="text-xs text-gray-500 text-center">
        共 {filteredVideos.length} 个结果 {filteredVideos.length !== STOCK_VIDEOS.length && `(筛选自 ${STOCK_VIDEOS.length} 个素材)`}
      </div>
    </div>
  );

  // 渲染视频卡片
  const renderVideoCard = (video: StockVideo) => (
    <div
      key={video.id}
      className="bg-gray-800 rounded overflow-hidden cursor-pointer hover:ring-2 hover:ring-orange-500 transition group"
      onClick={() => setPreviewVideo(video)}
    >
      {/* 缩略图 */}
      <div className="relative aspect-video">
        <img
          src={video.thumbnailUrl}
          alt={video.title}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        <div className="absolute bottom-1 right-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded flex items-center gap-1">
          <span>{video.duration}s</span>
        </div>
        {/* 分辨率标签 */}
        {video.resolution === '4K' && (
          <div className="absolute top-1 left-1 bg-orange-600/90 text-white text-xs px-1.5 py-0.5 rounded">
            4K
          </div>
        )}
        {/* 播放按钮 */}
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition bg-black/30">
          <div className="w-10 h-10 bg-white/90 rounded-full flex items-center justify-center">
            <span className="text-orange-600 text-xl">▶</span>
          </div>
        </div>
      </div>
      
      {/* 信息 */}
      <div className="p-2">
        <h4 className="text-white text-sm font-medium truncate">{video.title}</h4>
        <p className="text-gray-400 text-xs truncate">{video.description}</p>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {video.tags.slice(0, 3).map(tag => (
            <span key={tag} className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
          <span>{video.width}x{video.height}</span>
          <span>•</span>
          <span>{video.fps}fps</span>
          <span>•</span>
          <span className="uppercase">{video.source}</span>
        </div>
      </div>
      
      {/* 添加按钮 */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          handleAddToTimeline(video);
        }}
        className="w-full py-1.5 bg-orange-600 hover:bg-orange-500 text-white text-xs font-medium transition"
      >
        + 添加到时间轴
      </button>
    </div>
  );

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-white font-semibold">视频素材库</h3>
        <span className="text-xs text-gray-500">{STOCK_VIDEOS.length} 个素材</span>
      </div>
      
      <div className="flex gap-4 h-full">
        {/* 左侧筛选器 */}
        <div className="w-48 flex-shrink-0 overflow-y-auto pr-2">
          {renderFilters()}
        </div>
        
        {/* 右侧视频网格 */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto">
            {loading && currentPage === 1 ? (
              <div className="text-center text-gray-400 py-8">加载中...</div>
            ) : filteredVideos.length === 0 ? (
              <div className="text-center text-gray-400 py-8">
                <div className="text-4xl mb-2">🔍</div>
                <p>没有找到匹配的素材</p>
                <button
                  onClick={handleResetFilters}
                  className="mt-3 text-orange-500 hover:text-orange-400 text-sm"
                >
                  重置筛选条件
                </button>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  {currentPageVideos.map(video => renderVideoCard(video))}
                </div>
                
                {/* 加载更多指示器 */}
                <div ref={loadMoreRef} className="py-4 text-center">
                  {loading && (
                    <div className="text-gray-400 text-sm">加载中...</div>
                  )}
                  {!hasMore && filteredVideos.length > 0 && (
                    <div className="text-gray-500 text-sm">
                      已显示全部 {filteredVideos.length} 个素材
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
      
      {/* 来源说明 */}
      <div className="mt-3 pt-3 border-t border-gray-800 text-xs text-gray-500 flex items-center justify-between">
        <span>素材来源：Pexels, Pixabay, Mixkit (免费商用)</span>
        <span>{currentPageVideos.length} / {filteredVideos.length}</span>
      </div>
      
      {/* 预览弹窗 */}
      {previewVideo && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={() => setPreviewVideo(null)}
        >
          <div className="bg-gray-800 rounded-lg p-4 max-w-3xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-3">
              <div>
                <h4 className="text-white font-semibold text-lg">{previewVideo.title}</h4>
                <p className="text-gray-400 text-sm mt-1">{previewVideo.description}</p>
              </div>
              <button
                onClick={() => setPreviewVideo(null)}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ✕
              </button>
            </div>
            
            <video
              src={previewVideo.url}
              controls
              autoPlay
              className="w-full rounded mb-4 bg-black"
            />
            
            {/* 详细信息 */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-gray-900 rounded p-3">
                <div className="text-gray-400 text-xs mb-1">分辨率</div>
                <div className="text-white text-sm">{previewVideo.width}x{previewVideo.height} ({previewVideo.resolution})</div>
              </div>
              <div className="bg-gray-900 rounded p-3">
                <div className="text-gray-400 text-xs mb-1">帧率</div>
                <div className="text-white text-sm">{previewVideo.fps} fps</div>
              </div>
              <div className="bg-gray-900 rounded p-3">
                <div className="text-gray-400 text-xs mb-1">时长</div>
                <div className="text-white text-sm">{previewVideo.duration} 秒</div>
              </div>
              <div className="bg-gray-900 rounded p-3">
                <div className="text-gray-400 text-xs mb-1">来源</div>
                <div className="text-white text-sm uppercase">{previewVideo.source}</div>
              </div>
            </div>
            
            {/* 标签 */}
            <div className="mb-4">
              <div className="text-gray-400 text-xs mb-2">标签</div>
              <div className="flex flex-wrap gap-2">
                {previewVideo.tags.map(tag => (
                  <span key={tag} className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => {
                  handleAddToTimeline(previewVideo);
                  setPreviewVideo(null);
                }}
                className="flex-1 py-2.5 bg-orange-600 hover:bg-orange-500 text-white rounded font-medium transition"
              >
                添加到时间轴
              </button>
              <button
                onClick={() => setPreviewVideo(null)}
                className="flex-1 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded transition"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}