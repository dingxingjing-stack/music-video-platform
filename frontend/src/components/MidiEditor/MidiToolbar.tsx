/**
 * MidiToolbar — MIDI 编辑器工具栏
 */

import { useCallback } from 'react';
import { GM_INSTRUMENTS } from '../../types/trackStudio';

interface Zoom {
  x: number;
  y: number;
}

interface Props {
  zoom: Zoom;
  onZoomChange: (zoom: Zoom) => void;
  tempo: number;
  onTempoChange: (tempo: number) => void;
  onPlay: () => void;
  onStop: () => void;
  isPlaying: boolean;
  instrumentName: string;
  onInstrumentChange: (program: number) => void;
}

export function MidiToolbar({
  zoom,
  onZoomChange,
  tempo,
  onTempoChange,
  onPlay,
  onStop,
  isPlaying,
  instrumentName,
  onInstrumentChange,
}: Props) {
  const handleZoomIn = useCallback(() => {
    onZoomChange({ x: Math.min(zoom.x * 1.2, 10), y: Math.min(zoom.y * 1.2, 40) });
  }, [zoom, onZoomChange]);

  const handleZoomOut = useCallback(() => {
    onZoomChange({ x: Math.max(zoom.x / 1.2, 0.5), y: Math.max(zoom.y / 1.2, 15) });
  }, [zoom, onZoomChange]);

  const handleTempoChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onTempoChange(parseInt(e.target.value, 10));
  }, [onTempoChange]);

  return (
    <div className="flex items-center gap-4 p-2 bg-[#1e1e1e] border-b border-[#2a2a2a]">
      {/* Playback */}
      <div className="flex items-center gap-2">
        <button
          onClick={isPlaying ? onStop : onPlay}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            isPlaying
              ? 'bg-[#ef4444] text-white hover:bg-[#dc2626]'
              : 'bg-gradient-to-r from-orange-500 to-pink-500 text-white hover:from-orange-600 hover:to-pink-600'
          }`}
        >
          {isPlaying ? '⏹ 停止' : '▶ 播放'}
        </button>
      </div>

      {/* Zoom */}
      <div className="flex items-center gap-2 border-l border-[#2a2a2a] pl-4">
        <span className="text-xs text-[#777777]">缩放:</span>
        <button
          onClick={handleZoomOut}
          className="w-7 h-7 flex items-center justify-center bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm"
        >
          −
        </button>
        <span className="text-xs text-[#e0e0e0] min-w-[60px] text-center">
          {zoom.x.toFixed(1)} px/tick
        </span>
        <button
          onClick={handleZoomIn}
          className="w-7 h-7 flex items-center justify-center bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm"
        >
          +
        </button>
      </div>

      {/* Tempo */}
      <div className="flex items-center gap-2 border-l border-[#2a2a2a] pl-4">
        <span className="text-xs text-[#777777]">速度:</span>
        <input
          type="range"
          min="40"
          max="200"
          value={tempo}
          onChange={handleTempoChange}
          className="w-24 h-1 bg-[#3a3a3a] rounded-lg appearance-none cursor-pointer accent-orange-500"
        />
        <span className="text-xs text-[#e0e0e0] min-w-[40px]">{tempo} BPM</span>
      </div>

      {/* Instrument */}
      <div className="flex items-center gap-2 border-l border-[#2a2a2a] pl-4">
        <span className="text-xs text-[#777777]">乐器:</span>
        <select
          value={instrumentName}
          onChange={(e) => {
            const program = parseInt(e.target.value, 10);
            onInstrumentChange(program);
          }}
          className="bg-[#2a2a2a] text-[#e0e0e0] text-xs rounded px-2 py-1 border border-[#3a3a3a] focus:outline-none focus:border-orange-500"
        >
          {GM_INSTRUMENTS.slice(0, 40).map((inst) => (
            <option key={inst.program} value={inst.program}>
              {inst.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}