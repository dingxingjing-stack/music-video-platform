/**
 * 视频时间轴组件
 * 
 * 功能:
 * - 显示多轨道视频剪辑
 * - 拖拽剪辑调整位置/时长
 * - 播放头同步
 * - 音频波形背景
 * - 节拍标记显示
 */

import { useState, useRef } from 'react';
import { VideoTrack, BeatMarker, WaveformData } from '../types/video-sync';

interface Props {
  tracks: VideoTrack[];
  waveformData?: WaveformData;
  beatMarkers?: BeatMarker[];
  currentTime: number;
  duration: number;
  onTimeChange: (time: number) => void;
  onClipMove?: (clipId: string, trackId: string, startTime: number) => void;
  onClipResize?: (clipId: string, duration: number) => void;
  onTrackAdd?: () => void;
  zoom: number;
}

export function VideoTimeline({
  tracks,
  waveformData,
  beatMarkers = [],
  currentTime,
  duration,
  onTimeChange,
  onClipMove,
  onTrackAdd,
  zoom = 50
}: Props) {
  const timelineRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [draggedClip, setDraggedClip] = useState<string | null>(null);

  // 将时间转换为像素位置
  const timeToPixels = (time: number) => time * zoom;
  const pixelsToTime = (pixels: number) => pixels / zoom;

  // 处理时间轴点击 (跳转播放头)
  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current || isDragging) return;
    
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const time = pixelsToTime(x);
    
    if (time >= 0 && time <= duration) {
      onTimeChange(time);
    }
  };

  // 处理剪辑拖拽开始
  const handleClipDragStart = (clipId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDraggedClip(clipId);
    setIsDragging(true);
  };

  // 处理剪辑拖拽移动
  const handleClipDrag = (
    clipId: string,
    trackId: string,
    e: React.MouseEvent<HTMLDivElement>
  ) => {
    if (!timelineRef.current || !onClipMove) return;
    
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const newStartTime = pixelsToTime(x);
    const clampedTime = Math.max(0, Math.min(newStartTime, duration - 1));
    
    onClipMove(clipId, trackId, clampedTime);
  };

  // 渲染时间标尺
  const renderTimeRuler = () => {
    const markers = [];
    const interval = duration < 30 ? 1 : (duration < 60 ? 5 : 10);
    
    for (let i = 0; i <= duration; i += interval) {
      const x = timeToPixels(i);
      markers.push(
        <div
          key={i}
          className="absolute top-0 text-xs text-gray-400"
          style={{ left: x }}
        >
          <div className="border-l border-gray-600 h-3" />
          <div className="mt-1">
            {formatTime(i)}
          </div>
        </div>
      );
    }
    
    return markers;
  };

  // 渲染音频波形
  const renderWaveform = () => {
    if (!waveformData) return null;
    
    const { peaks } = waveformData;
    const width = timeToPixels(duration);
    const barWidth = width / peaks.length;
    
    return (
      <div className="h-16 bg-gray-900/50 rounded">
        <svg width={width} height={64} className="absolute">
          {peaks.map((peak, i) => {
            const height = peak * 32;
            const x = i * barWidth;
            return (
              <rect
                key={i}
                x={x}
                y={32 - height / 2}
                width={barWidth - 1}
                height={height}
                fill="#f97316"
                opacity={0.6}
              />
            );
          })}
        </svg>
      </div>
    );
  };

  // 渲染节拍标记
  const renderBeatMarkers = () => {
    return beatMarkers.map((marker, i) => {
      const x = timeToPixels(marker.time);
      const isBar = marker.type === 'bar';
      const isDownbeat = marker.type === 'downbeat';
      
      return (
        <div
          key={i}
          className={`absolute top-0 bottom-0 border-l pointer-events-none ${
            isBar ? 'border-orange-500' : (isDownbeat ? 'border-orange-400' : 'border-gray-600')
          }`}
          style={{ left: x, height: isBar ? '100%' : '4px' }}
        >
          {isBar && marker.label && (
            <div className="text-xs text-orange-400 mt-1">{marker.label}</div>
          )}
        </div>
      );
    });
  };

  // 渲染播放头
  const renderPlayhead = () => {
    const x = timeToPixels(currentTime);
    return (
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-50 pointer-events-none"
        style={{ left: x }}
      >
        <div className="w-3 h-3 bg-red-500 rounded-full -ml-1.5" />
      </div>
    );
  };

  // 渲染视频轨道
  const renderTracks = () => {
    return tracks.map((track) => (
      <div
        key={track.id}
        className="relative h-24 border-b border-gray-700"
        style={{ backgroundColor: track.color + '20' }}
      >
        {/* 轨道名称 */}
        <div className="absolute left-0 top-0 p-1 text-xs text-gray-400 z-10">
          {track.name}
        </div>
        
        {/* 剪辑 */}
        {track.clips.map((clip) => {
          const left = timeToPixels(clip.startTime);
          const width = timeToPixels(clip.duration);
          
          return (
            <div
              key={clip.id}
              className={`absolute top-2 h-20 rounded cursor-move ${
                draggedClip === clip.id ? 'opacity-50' : 'opacity-100'
              }`}
              style={{
                left,
                width,
                backgroundColor: track.color
              }}
              onMouseDown={(e) => handleClipDragStart(clip.id, e)}
              onMouseMove={(e) => handleClipDrag(clip.id, track.id, e)}
            >
              {/* 剪辑缩略图 */}
              {clip.thumbnailUrl && (
                <img
                  src={clip.thumbnailUrl}
                  alt={clip.name}
                  className="w-full h-full object-cover rounded opacity-50"
                />
              )}
              
              {/* 剪辑名称 */}
              <div className="absolute bottom-1 left-2 text-xs text-white truncate">
                {clip.name}
              </div>
              
              {/* 时长调整手柄 */}
              <div className="absolute right-0 top-0 bottom-0 w-4 cursor-e-resize hover:bg-white/20" />
            </div>
          );
        })}
      </div>
    ));
  };

  // 格式化时间显示
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 rounded-lg overflow-hidden">
      {/* 时间标尺 */}
      <div className="h-8 border-b border-gray-700 relative flex-shrink-0">
        {renderTimeRuler()}
      </div>
      
      {/* 主时间轴区域 */}
      <div 
        ref={timelineRef}
        className="flex-1 overflow-x-auto overflow-y-auto relative"
        onClick={handleTimelineClick}
        style={{ width: timeToPixels(duration) + 200 }}
      >
        {/* 波形背景 */}
        {renderWaveform()}
        
        {/* 节拍标记 */}
        {renderBeatMarkers()}
        
        {/* 播放头 */}
        {renderPlayhead()}
        
        {/* 视频轨道 */}
        {renderTracks()}
      </div>
      
      {/* 添加轨道按钮 */}
      {onTrackAdd && (
        <button
          onClick={onTrackAdd}
          className="mt-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded text-sm"
        >
          + 添加轨道
        </button>
      )}
    </div>
  );
}