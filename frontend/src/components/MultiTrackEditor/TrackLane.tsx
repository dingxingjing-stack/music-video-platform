/**
 * TrackLane — 单个轨道行（支持剪辑操作）
 */

import { useState, useCallback } from 'react';
import { Track, AudioClip } from '../../types/trackStudio';
import { AudioClipView } from './AudioClipView';
import { Zoom } from './Toolbar';

interface Props {
  track: Track;
  zoom: Zoom;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onClipChange: (clipId: string, updates: Partial<AudioClip>) => void;
  onAddClip: () => void;
}

export function TrackLane({
  track,
  zoom,
  isSelected,
  onSelect,
  onDelete,
  onClipChange,
  onAddClip,
}: Props) {
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [localMute, setLocalMute] = useState(track.muted);
  const [localSolo, setLocalSolo] = useState(track.solo);
  const [localVolume, setLocalVolume] = useState(track.volume ?? 1);
  const [localPan, setLocalPan] = useState(track.pan ?? 0);

  const handleToggleMute = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setLocalMute(prev => !prev);
  }, []);

  const handleToggleSolo = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setLocalSolo(prev => !prev);
  }, []);

  const handleVolumeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    e.stopPropagation();
    setLocalVolume(parseFloat(e.target.value));
  }, []);

  const handlePanChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    e.stopPropagation();
    setLocalPan(parseFloat(e.target.value));
  }, []);

  return (
    <div
      className={`flex border-b border-[#2a2a2a] ${isSelected ? 'bg-[#2a2a2a]/50' : 'bg-[#1e1e1e]'}`}
      style={{ height: `${zoom.y}px` }}
      onClick={onSelect}
    >
      {/* Track Header */}
      <div className="w-48 flex-shrink-0 border-r border-[#2a2a2a] p-2 flex flex-col justify-center">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-[#e0e0e0] truncate">{track.name}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="text-[#777777] hover:text-[#ef4444] text-xs"
          >
            ✕
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={handleToggleMute}
            className={`px-1.5 py-0.5 text-xs rounded transition-colors ${
              localMute ? 'bg-[#ef4444] text-white' : 'bg-[#3a3a3a] text-[#e0e0e0]'
            }`}
          >
            M
          </button>
          <button
            onClick={handleToggleSolo}
            className={`px-1.5 py-0.5 text-xs rounded transition-colors ${
              localSolo ? 'bg-[#eab308] text-black' : 'bg-[#3a3a3a] text-[#e0e0e0]'
            }`}
          >
            S
          </button>
        </div>

        {/* Volume/Pan */}
        <div className="flex items-center gap-2 mt-1">
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={localVolume}
            onChange={handleVolumeChange}
            className="w-full h-1 bg-[#3a3a3a] rounded-lg appearance-none cursor-pointer accent-orange-500"
            title="音量"
          />
          <input
            type="range"
            min="-1"
            max="1"
            step="0.01"
            value={localPan}
            onChange={handlePanChange}
            className="w-full h-1 bg-[#3a3a3a] rounded-lg appearance-none cursor-pointer accent-orange-500"
            title="声像"
          />
        </div>
      </div>

      {/* Track Timeline Area */}
      <div className="flex-1 relative overflow-hidden bg-[#121212]/50">
        {/* Grid lines */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(to right, #2a2a2a 1px, transparent 1px)`,
            backgroundSize: `${zoom.x}px 100%`,
          }}
        />

        {/* Clips */}
        {track.clips?.map((clip) => (
          <AudioClipView
            key={clip.id}
            clip={clip}
            zoom={zoom}
            isSelected={selectedClipId === clip.id}
            onSelect={() => {
              setSelectedClipId(clip.id);
            }}
            onChange={(updates) => onClipChange(clip.id, updates)}
          />
        ))}

        {/* Add clip button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onAddClip();
          }}
          className="absolute top-1/2 left-2 -translate-y-1/2 px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs transition-colors"
        >
          + 片段
        </button>
      </div>
    </div>
  );
}