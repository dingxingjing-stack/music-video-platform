/**
 * Community — 社区排行榜页面
 * 
 * 功能:
 * - 热门排行榜 (按播放量)
 * - 新歌榜 (按创建时间)
 * - 趋势榜 (综合算法)
 * - 搜索功能
 * - 风格筛选
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { SocialSystem } from '../components/SocialSystem';

interface CommunityTrack {
  id: string;
  title: string;
  artist: string;
  audio_url: string;
  plays: number;
  likes: number;
  comments: number;
  duration: number;
  genre: string;
  tags: string[];
  is_trending: boolean;
}

interface ChartData {
  chart_type: string;
  tracks: CommunityTrack[];
  total: number;
}

type ChartType = 'hot' | 'new' | 'trending';

const CHART_LABELS: Record<ChartType, string> = {
  hot: '🔥 热门榜',
  new: '🆕 新歌榜',
  trending: '📈 趋势榜',
};

const GENRES = ['pop', 'rock', 'jazz', 'electronic', 'hip-hop', 'classical', 'ambient', 'lo-fi', 'cinematic', 'r&b'];

export function Community() {
  const navigate = useNavigate();
  const [chartType, setChartType] = useState<ChartType>('hot');
  const [data, setData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedGenre, setSelectedGenre] = useState<string>('all');
  const [currentPlaying, setCurrentPlaying] = useState<string | null>(null);

  // 加载排行榜数据
  useEffect(() => {
    loadChart(chartType);
  }, [chartType]);

  const loadChart = async (type: ChartType) => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/v1/community/${type}`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Failed to load chart:', error);
    } finally {
      setLoading(false);
    }
  };

  // 搜索功能
  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadChart(chartType);
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams({ q: searchQuery });
      if (selectedGenre !== 'all') {
        params.append('genre', selectedGenre);
      }
      const response = await fetch(`http://localhost:8000/api/v1/community/search?${params}`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  // 播放歌曲
  const handlePlay = (track: CommunityTrack) => {
    if (currentPlaying === track.id) {
      setCurrentPlaying(null); // 停止
    } else {
      setCurrentPlaying(track.id);
      // 实际播放逻辑需要一个全局音频播放器
      // 这里仅做演示
      const audio = new Audio(track.audio_url);
      audio.play();
      audio.onended = () => setCurrentPlaying(null);
    }
  };

  // 点赞歌曲
  const handleLike = async (trackId: string) => {
    try {
      await fetch(`http://localhost:8000/api/v1/community/${trackId}/like`, { method: 'POST' });
      if (data) {
        setData({
          ...data,
          tracks: data.tracks.map(t =>
            t.id === trackId ? { ...t, likes: t.likes + 1 } : t
          ),
        });
      }
    } catch (error) {
      console.error('Like failed:', error);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-[#e0e0e0]">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-[#1a1a1a]/95 backdrop-blur border-b border-[#2a2a2a]">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white">🎵 社区排行榜</h1>
              <p className="text-xs text-[#777777] mt-1">发现热门 AI 音乐作品</p>
            </div>
            <button
              onClick={() => navigate('/')}
              className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#333333] text-white rounded-lg text-sm transition"
            >
              ← 返回
            </button>
          </div>

          {/* 搜索栏 */}
          <div className="mt-4 flex gap-3">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="搜索歌曲或艺术家..."
              className="flex-1 bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-4 py-2 text-sm text-white placeholder-[#777777]"
            />
            <select
              value={selectedGenre}
              onChange={(e) => setSelectedGenre(e.target.value)}
              className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-4 py-2 text-sm text-white"
            >
              <option value="all">全部风格</option>
              {GENRES.map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
            <button
              onClick={handleSearch}
              className="px-6 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition"
            >
              搜索
            </button>
          </div>

          {/* 榜单切换 */}
          <div className="mt-4 flex gap-2">
            {(Object.keys(CHART_LABELS) as ChartType[]).map(type => (
              <button
                key={type}
                onClick={() => setChartType(type)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  chartType === type
                    ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                    : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333]'
                }`}
              >
                {CHART_LABELS[type]}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 内容区 */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {loading ? (
          <div className="text-center py-20">
            <div className="text-4xl mb-4">🎵</div>
            <p className="text-[#777777]">加载中...</p>
          </div>
        ) : data ? (
          <>
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">
                {CHART_LABELS[chartType]} · {data.total} 首歌曲
              </h2>
            </div>

            <div className="grid gap-3">
              {data.tracks.map((track, index) => (
                <div
                  key={track.id}
                  className={`flex items-center gap-4 p-4 bg-[#1a1a1a] hover:bg-[#222222] rounded-xl transition group ${
                    currentPlaying === track.id ? 'ring-2 ring-orange-500' : ''
                  }`}
                >
                  {/* 排名 */}
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                    index < 3 ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white' : 'bg-[#2a2a2a] text-[#777777]'
                  }`}>
                    {index + 1}
                  </div>

                  {/* 播放按钮 */}
                  <button
                    onClick={() => handlePlay(track)}
                    className="w-12 h-12 rounded-full bg-[#2a2a2a] hover:bg-orange-500 flex items-center justify-center transition"
                  >
                    {currentPlaying === track.id ? '⏸️' : '▶️'}
                  </button>

                  {/* 歌曲信息 */}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-white font-medium truncate">{track.title}</h3>
                    <p className="text-sm text-[#777777]">{track.artist}</p>
                  </div>

                  {/* 风格标签 */}
                  <div className="hidden md:block">
                    <span className="px-2 py-1 bg-[#2a2a2a] rounded text-xs text-[#777777]">
                      {track.genre}
                    </span>
                  </div>

                  {/* 统计 */}
                  <div className="flex items-center gap-4 text-sm text-[#777777]">
                    <div className="text-center">
                      <div className="text-white font-medium">{track.plays.toLocaleString()}</div>
                      <div className="text-xs">播放</div>
                    </div>
                    {/* 社交按钮 */}
                    <div className="flex items-center gap-2">
                      <SocialSystem workId={track.id} authorId={track.artist} showFollow={false} />
                    </div>
                    <div className="text-xs text-[#555555] w-16">
                      {Math.floor(track.duration / 60)}:{(track.duration % 60).toString().padStart(2, '0')}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {data.tracks.length === 0 && (
              <div className="text-center py-20">
                <div className="text-4xl mb-4">🔍</div>
                <p className="text-[#777777]">没有找到相关歌曲</p>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-20">
            <div className="text-4xl mb-4">😕</div>
            <p className="text-[#777777]">加载失败，请刷新重试</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Community;