/**
 * Toolbar — 多轨编辑器工具栏
 */

import { useCallback } from 'react';

export type Tool = 'select' | 'split' | 'trim' | 'fade';

export interface Zoom {
  x: number;
  y: number;
}

interface Props {
  zoom: Zoom;
  onZoomChange: (zoom: Zoom) => void;
  onAddTrack: () => void;
  isPlaying: boolean;
  onPlay: () => void;
  onStop: () => void;
}

export function Toolbar({
  zoom,
  onZoomChange,
  onAddTrack,
  isPlaying,
  onPlay,
  onStop,
}: Props) {
  const handleZoomIn = useCallback(() => {
    onZoomChange({ ...zoom, x: Math.min(zoom.x * 1.2, 200) });
  }, [zoom, onZoomChange]);

  const handleZoomOut = useCallback(() => {
    onZoomChange({ ...zoom, x: Math.max(zoom.x / 1.2, 10) });
  }, [zoom, onZoomChange]);

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-[#1e1e1e] border-b border-[#2a2a2a]">
      {/* Playback controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={isPlaying ? onStop : onPlay}
          className="px-4 py-1.5 bg-[#ff6a10] hover:bg-[#ff8533] text-[#121212] rounded-lg text-sm font-medium transition-colors"
        >
          {isPlaying ? '⏹ 停止' : '▶ 播放'}
        </button>
      </div>

      {/* Zoom controls */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-[#777777]">缩放:</span>
        <button
          onClick={handleZoomOut}
          className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs"
        >
          −
        </button>
        <span className="text-xs text-[#777777] w-16 text-center">
          {Math.round(zoom.x)} px/s
        </span>
        <button
          onClick={handleZoomIn}
          className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs"
        >
          +
        </button>
      </div>

      {/* Track controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={onAddTrack}
          className="px-4 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
        >
          + 添加轨道
        </button>
      </div>
    </div>
  );
}