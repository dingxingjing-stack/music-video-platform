/**
 * 歌词字幕编辑器组件
 * 
 * 功能:
 * - 导入/编辑歌词
 * - 自动时间对齐
 * - 歌词样式编辑
 * - 卡拉 OK 式高亮
 */

import { useState } from 'react';
import { LyricLine, LyricStyle } from '../types/video-sync';

interface Props {
  lyrics: LyricLine[];
  currentTime: number;
  duration: number;
  onLyricsChange: (lyrics: LyricLine[]) => void;
  onStyleChange?: (style: LyricStyle) => void;
}

export function LyricEditor({
  lyrics,
  currentTime,
  duration,
  onLyricsChange,
  onStyleChange
}: Props) {
  const [rawLyrics, setRawLyrics] = useState('');
  const [autoSync, setAutoSync] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState<LyricStyle>({
    fontSize: 24,
    fontFamily: 'Arial',
    color: '#ffffff',
    position: 'bottom',
    offsetY: -50,
    animation: 'karaoke'
  });

  // 导入纯文本歌词并自动分配时间
  const handleImportLyrics = () => {
    const lines = rawLyrics.split('\n').filter(line => line.trim());
    const averageLineDuration = duration / lines.length;
    
    const newLyrics: LyricLine[] = lines.map((text, index) => ({
      id: `lyric-${index}`,
      text: text.trim(),
      startTime: index * averageLineDuration,
      endTime: (index + 1) * averageLineDuration,
      trackId: 'lyric-track-1',
      style: selectedStyle
    }));
    
    onLyricsChange(newLyrics);
  };

  // 手动调整歌词时间
  const handleTimeAdjust = (id: string, field: 'startTime' | 'endTime', value: number) => {
    const updated = lyrics.map(lyric => 
      lyric.id === id ? { ...lyric, [field]: value } : lyric
    );
    onLyricsChange(updated);
  };

  // 获取当前高亮的歌词行
  const getCurrentLyric = () => {
    return lyrics.find(
      lyric => currentTime >= lyric.startTime && currentTime < lyric.endTime
    );
  };

  const currentLyric = getCurrentLyric();

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full flex flex-col">
      <h3 className="text-white font-semibold mb-3">歌词字幕</h3>
      
      {/* 歌词预览 */}
      <div className="mb-4 p-4 bg-gray-800 rounded h-40 relative overflow-hidden">
        <div className="text-center">
          {lyrics.map((lyric) => {
            const isActive = lyric.id === currentLyric?.id;
            return (
              <div
                key={lyric.id}
                className={`transition-all ${
                  isActive
                    ? 'text-orange-400 text-2xl font-bold'
                    : 'text-gray-500 text-lg'
                }`}
              >
                {lyric.text}
              </div>
            );
          })}
        </div>
      </div>
      
      {/* 原始歌词输入 */}
      <div className="mb-4">
        <label className="text-gray-300 text-sm block mb-2">
          导入歌词 (每行一句)
        </label>
        <textarea
          value={rawLyrics}
          onChange={(e) => setRawLyrics(e.target.value)}
          className="w-full h-32 bg-gray-800 text-white p-2 rounded resize-none"
          placeholder="在这里粘贴歌词..."
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={handleImportLyrics}
            className="px-3 py-1 bg-orange-600 hover:bg-orange-500 text-white rounded text-sm"
          >
            自动同步时间
          </button>
          <label className="flex items-center text-sm text-gray-400">
            <input
              type="checkbox"
              checked={autoSync}
              onChange={(e) => setAutoSync(e.target.checked)}
              className="mr-2"
            />
            启用手动微调
          </label>
        </div>
      </div>
      
      {/* 歌词列表编辑 */}
      <div className="flex-1 overflow-y-auto">
        <h4 className="text-white text-sm font-medium mb-2">歌词时间轴</h4>
        {lyrics.map((lyric, index) => (
          <div
            key={lyric.id}
            className={`p-2 mb-2 rounded flex items-center gap-2 ${
              lyric.id === currentLyric?.id ? 'bg-orange-900/50' : 'bg-gray-800'
            }`}
          >
            <span className="text-gray-400 text-xs w-6">{index + 1}</span>
            <input
              type="text"
              value={lyric.text}
              onChange={(e) => {
                const updated = lyrics.map((l, i) =>
                  i === index ? { ...l, text: e.target.value } : l
                );
                onLyricsChange(updated);
              }}
              className="flex-1 bg-transparent text-white text-sm"
            />
            {autoSync && (
              <>
                <input
                  type="number"
                  value={lyric.startTime}
                  onChange={(e) => handleTimeAdjust(lyric.id, 'startTime', parseFloat(e.target.value))}
                  className="w-20 bg-gray-700 text-white text-xs p-1 rounded"
                  step="0.1"
                  placeholder="开始"
                />
                <input
                  type="number"
                  value={lyric.endTime}
                  onChange={(e) => handleTimeAdjust(lyric.id, 'endTime', parseFloat(e.target.value))}
                  className="w-20 bg-gray-700 text-white text-xs p-1 rounded"
                  step="0.1"
                  placeholder="结束"
                />
              </>
            )}
          </div>
        ))}
      </div>
      
      {/* 样式设置 */}
      <div className="mt-4 border-t border-gray-700 pt-4">
        <h4 className="text-white text-sm font-medium mb-2">字幕样式</h4>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-gray-400 text-xs">字体大小</label>
            <input
              type="range"
              min="12"
              max="48"
              value={selectedStyle.fontSize}
              onChange={(e) => {
                const newStyle = { ...selectedStyle, fontSize: parseInt(e.target.value) };
                setSelectedStyle(newStyle);
                onStyleChange?.(newStyle);
              }}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-gray-400 text-xs">位置</label>
            <select
              value={selectedStyle.position}
              onChange={(e) => {
                const newStyle = { ...selectedStyle, position: e.target.value as any };
                setSelectedStyle(newStyle);
                onStyleChange?.(newStyle);
              }}
              className="w-full bg-gray-700 text-white text-xs p-1 rounded"
            >
              <option value="top">顶部</option>
              <option value="center">中间</option>
              <option value="bottom">底部</option>
            </select>
          </div>
          <div>
            <label className="text-gray-400 text-xs">动画</label>
            <select
              value={selectedStyle.animation}
              onChange={(e) => {
                const newStyle = { ...selectedStyle, animation: e.target.value as any };
                setSelectedStyle(newStyle);
                onStyleChange?.(newStyle);
              }}
              className="w-full bg-gray-700 text-white text-xs p-1 rounded"
            >
              <option value="none">无</option>
              <option value="karaoke">卡拉 OK</option>
              <option value="scroll">滚动</option>
            </select>
          </div>
          <div>
            <label className="text-gray-400 text-xs">颜色</label>
            <input
              type="color"
              value={selectedStyle.color}
              onChange={(e) => {
                const newStyle = { ...selectedStyle, color: e.target.value };
                setSelectedStyle(newStyle);
                onStyleChange?.(newStyle);
              }}
              className="w-full h-6 rounded"
            />
          </div>
        </div>
      </div>
    </div>
  );
}