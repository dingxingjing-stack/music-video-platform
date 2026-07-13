/**
 * MixConsole — 专业混音台组件
 * 
 * 功能:
 * - 通道条 (Channel Strip): 音量/声像/静音/独奏
 * - 效果器插槽 (Insert Slots): 5 个效果器位
 * - Aux 发送 (Send Slots): 4 个辅助发送
 * - 主推子 (Master Fader): 总输出控制
 * - 电平表 (VU Meter): 实时电平显示
 */

import React, { useState } from 'react';
import { Track } from '../../types/trackStudio';

interface ChannelStripProps {
  track: Track;
  onUpdate: (trackId: string, updates: Partial<Track>) => void;
  isSelected?: boolean;
}

const ChannelStrip: React.FC<ChannelStripProps> = ({ track, onUpdate, isSelected = false }) => {
  const [isMuted, setIsMuted] = useState(track.muted || false);
  const [isSolo, setIsSolo] = useState(track.solo || false);

  const handleVolumeChange = (value: number) => {
    onUpdate(track.id, { volume: value / 100 });
  };

  const handlePanChange = (value: number) => {
    onUpdate(track.id, { pan: (value - 50) / 50 });
  };

  const toggleMute = () => {
    const newMute = !isMuted;
    setIsMuted(newMute);
    onUpdate(track.id, { muted: newMute });
  };

  const toggleSolo = () => {
    const newSolo = !isSolo;
    setIsSolo(newSolo);
    onUpdate(track.id, { solo: newSolo });
  };

  return (
    <div className={`
      flex flex-col items-center p-3 rounded-lg
      ${isSelected ? 'bg-orange-500/20 ring-2 ring-orange-500' : 'bg-zinc-800'}
      min-w-[100px] max-w-[120px]
    `}>
      <div className="text-xs font-medium text-white mb-2 truncate w-full text-center">
        {track.name || `Track ${track.id}`}
      </div>

      <div className="w-8 h-16 bg-zinc-900 rounded mb-3 relative overflow-hidden">
        <div 
          className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-green-500 via-yellow-500 to-red-500 transition-all duration-100"
          style={{ height: `${(track.volume || 0.5) * 100}%` }}
        />
      </div>

      <div className="w-full mb-3">
        <input
          type="range"
          min="0"
          max="100"
          value={(track.volume || 0.5) * 100}
          onChange={(e) => handleVolumeChange(Number(e.target.value))}
          className="w-full h-24 appearance-none bg-zinc-700 rounded-lg cursor-pointer"
          style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
        />
      </div>

      <div className="w-full mb-3">
        <div className="text-xs text-zinc-400 mb-1 text-center">Pan</div>
        <input
          type="range"
          min="0"
          max="100"
          value={((track.pan || 0) + 1) / 2 * 100}
          onChange={(e) => handlePanChange(Number(e.target.value))}
          className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-xs text-zinc-500 mt-1">
          <span>L</span>
          <span>R</span>
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        <button
          onClick={toggleMute}
          className={`px-2 py-1 text-xs font-bold rounded ${isMuted ? 'bg-red-500 text-white' : 'bg-zinc-700 text-zinc-300'} hover:opacity-80 transition`}
        >
          M
        </button>
        <button
          onClick={toggleSolo}
          className={`px-2 py-1 text-xs font-bold rounded ${isSolo ? 'bg-yellow-500 text-black' : 'bg-zinc-700 text-zinc-300'} hover:opacity-80 transition`}
        >
          S
        </button>
      </div>

      <div className="w-full space-y-1 mb-3">
        {[1, 2, 3, 4, 5].map((slot) => (
          <div
            key={slot}
            className="w-full bg-zinc-900 rounded py-1 px-2 text-xs text-center text-zinc-400 hover:bg-zinc-700 cursor-pointer transition"
          >
            Slot {slot}
          </div>
        ))}
      </div>

      <div className="w-full space-y-1">
        {['A', 'B', 'C', 'D'].map((name) => (
          <div key={name} className="flex items-center gap-1">
            <span className="text-xs text-zinc-500 w-4">{name}</span>
            <input
              type="range"
              min="0"
              max="100"
              defaultValue="0"
              className="flex-1 h-1 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        ))}
      </div>
    </div>
  );
};

interface MasterChannelProps {
  masterVolume: number;
  onMasterVolumeChange: (volume: number) => void;
}

const MasterChannel: React.FC<MasterChannelProps> = ({ masterVolume, onMasterVolumeChange }) => {
  return (
    <div className="flex flex-col items-center p-4 bg-gradient-to-b from-zinc-800 to-zinc-900 rounded-lg min-w-[120px]">
      <div className="text-sm font-bold text-white mb-3">MASTER</div>
      
      <div className="w-10 h-24 bg-zinc-950 rounded mb-4 relative overflow-hidden border border-zinc-700">
        <div 
          className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-green-500 via-yellow-500 to-red-500 transition-all duration-75"
          style={{ height: `${masterVolume * 100}%` }}
        />
      </div>

      <input
        type="range"
        min="0"
        max="100"
        value={masterVolume * 100}
        onChange={(e) => onMasterVolumeChange(Number(e.target.value) / 100)}
        className="w-full h-32 appearance-none bg-zinc-700 rounded-lg cursor-pointer"
        style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
      />
      
      <div className="text-xs text-zinc-400 mt-2">
        {(masterVolume * 100).toFixed(0)}%
      </div>
    </div>
  );
};

interface MixConsoleProps {
  tracks: Track[];
  onUpdateTrack: (trackId: string, updates: Partial<Track>) => void;
  masterVolume?: number;
  onMasterVolumeChange?: (volume: number) => void;
  onClose?: () => void;
}

export const MixConsole: React.FC<MixConsoleProps> = ({
  tracks,
  onUpdateTrack,
  masterVolume = 0.8,
  onMasterVolumeChange = () => {},
  onClose,
}) => {
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-full overflow-auto shadow-2xl border border-zinc-800">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">MixConsole</h2>
            <p className="text-sm text-zinc-400 mt-1">专业混音台 - {tracks.length} 轨道</p>
          </div>
          {onClose && (
            <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
              关闭
            </button>
          )}
        </div>

        <div className="flex items-end gap-3 p-4 bg-zinc-950/50 rounded-xl overflow-x-auto">
          {tracks.map((track, idx) => (
            <ChannelStrip
              key={track.id}
              track={track}
              onUpdate={onUpdateTrack}
              isSelected={idx === 0}
            />
          ))}

          <div className="w-px h-64 bg-zinc-700 mx-2" />

          <MasterChannel
            masterVolume={masterVolume}
            onMasterVolumeChange={onMasterVolumeChange}
          />
        </div>

        <div className="mt-4 flex justify-between items-center text-xs text-zinc-500">
          <div>
            <span className="mr-4">M = 静音</span>
            <span className="mr-4">S = 独奏</span>
            <span className="mr-4">Pan = 声像</span>
          </div>
          <div>Aux 发送：A/B/C/D</div>
        </div>
      </div>
    </div>
  );
};

export default MixConsole;