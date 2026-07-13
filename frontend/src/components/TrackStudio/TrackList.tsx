/**
 * TrackList — Active tracks grid with inline AudioPlayer and detail panel.
 *
 * Renders a grid of track cards. Each card shows status, progress bar,
 * and an inline AudioPlayer when completed. Clicking a card opens the
 * detail panel below the grid.
 *
 * Completed tracks can expose a RemixTool for audio modification.
 */

import { useMemo } from 'react';
import type { Track } from '../../types/trackStudio';
import { TRACK_COLORS } from '../../types/trackStudio';
import { AudioPlayer } from '../Audio/AudioPlayer';
import { RemixTool } from './RemixTool';

interface Props {
  tracks: Track[];
  selectedTrack: string | null;
  wsStatus: string;
  wsProgress: number;
  wsMessage: string;
  wsConnected: boolean;
  wsElapsedTime: number | null;
  onTrackSelect: (id: string | null) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onTrimChange: (trackId: string, start: number, end: number) => void;
  onRemixComplete?: (newTrack: Track) => void;
  onRemixError?: (error: string) => void;
}

export function TrackList({
  tracks,
  selectedTrack,
  wsStatus,
  wsProgress,
  wsMessage,
  wsConnected,
  wsElapsedTime,
  onTrackSelect,
  onRename,
  onDelete,
  onTrimChange,
  onRemixComplete,
  onRemixError,
}: Props) {
  const selectedTrackData = useMemo(
    () => tracks.find((t) => t.id === selectedTrack),
    [tracks, selectedTrack],
  );

  if (tracks.length === 0) return null;

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-[#b0b0b0] uppercase tracking-wider">
        Active Sessions
      </h2>

      {/* Grid of track cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {tracks.map((track, idx) => (
          <button
            key={track.id}
            onClick={() =>
              onTrackSelect(track.id === selectedTrack ? null : track.id)
            }
            className={`relative rounded-xl border-2 p-4 text-left transition-all overflow-hidden ${
              selectedTrack === track.id
                ? 'border-[#ff6a10] bg-[#ff6a10]/10'
                : track.status === 'completed'
                  ? 'border-[#76b900]/40 bg-[#76b900]/5 hover:border-[#76b900]/60'
                  : track.status === 'failed'
                    ? 'border-red-800/50 bg-red-950/20'
                    : 'border-[#2a2a38] bg-[#1f1f1f]/50 hover:border-[#2a2a38]'
            }`}
          >
            {track.status === 'running' && (
              <div
                className={`absolute bottom-0 left-0 right-0 h-1 ${TRACK_COLORS[idx % TRACK_COLORS.length]}`}
                style={{ width: `${track.progress}%`, transition: 'width 0.3s ease' }}
              />
            )}

            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">
                {track.type === 'music'
                  ? '🎵'
                  : track.type === 'tts'
                    ? '🎤'
                    : '🎛️'}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{track.name}</p>
                <p className="text-xs text-[#777777] capitalize">{track.status}</p>
              </div>
            </div>

            {track.status === 'running' && (
              <div className="mt-2">
                <div className="w-full h-1.5 bg-[#262626] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${TRACK_COLORS[idx % TRACK_COLORS.length]}`}
                    style={{ width: `${track.progress}%` }}
                  />
                </div>
                <p className="text-xs text-[#777777] mt-1">{track.progress}%</p>
              </div>
            )}

            {track.status === 'completed' && track.url && (
              <AudioPlayer
                track={track}
                onRename={onRename}
                onDelete={onDelete}
                onTrimChange={onTrimChange}
              />
            )}

            {track.status === 'completed' && track.url && onRemixComplete && (
              <RemixTool
                track={track}
                onRemixComplete={onRemixComplete}
                onRemixError={(err) => onRemixError?.(err)}
              />
            )}

            {track.status === 'completed' && !track.url && (
              <p className="text-xs text-[#777777] mt-2">No audio URL</p>
            )}
          </button>
        ))}
      </div>

      {/* Live Status Banner */}
      {(wsStatus || wsMessage) && (
        <div className="rounded-xl border border-[#2a2a38] bg-[#262626] p-4">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-[#b0b0b0]">
                  {wsStatus === 'loading' && '🔄 Loading model...'}
                  {wsStatus === 'running' && '🎵 Generating...'}
                  {wsStatus === 'pending' && '⏳ Queued...'}
                  {wsStatus === 'completed' && '✅ Done!'}
                  {wsStatus === 'failed' && '❌ Failed'}
                  {!wsStatus && '⏳ Starting...'}
                </span>
                <span className="text-sm font-bold text-[#ff6a10]">
                  {wsProgress}%
                </span>
              </div>
              <div className="w-full h-2 bg-[#262626] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#ff6a10] to-[#ff6a10] rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${wsProgress}%` }}
                />
              </div>
              {wsMessage && <p className="text-xs text-[#777777] mt-1">{wsMessage}</p>}
              {wsElapsedTime !== null && wsElapsedTime > 0 && (
                <p className="text-xs text-[#777777] mt-1">
                  Elapsed: {formatDuration(wsElapsedTime)}
                </p>
              )}
            </div>
            {wsConnected && (
              <span className="text-xs text-[#ff6a10] animate-pulse">● LIVE</span>
            )}
          </div>
        </div>
      )}

      {/* Selected Track Detail */}
      {selectedTrackData && (
        <TrackDetailPanel
          track={selectedTrackData}
          onClose={() => onTrackSelect(null)}
        />
      )}
    </div>
  );
}

function TrackDetailPanel({
  track,
  onClose,
}: {
  track: Track;
  onClose: () => void;
}) {
  return (
    <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f]/50 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">
          Track Detail: {track.name}
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-[#777777] hover:text-[#e0e0e0]"
        >
          ✕ Close
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <span className="text-[#777777]">Type:</span>{' '}
          <span className="capitalize text-[#e0e0e0]">{track.type}</span>
        </div>
        <div>
          <span className="text-[#777777]">Status:</span>{' '}
          <span
            className={`capitalize ${
              track.status === 'completed'
                ? 'text-[#76b900]'
                : track.status === 'failed'
                  ? 'text-[#ef4444]'
                  : track.status === 'running'
                    ? 'text-[#febc2e]'
                    : 'text-[#b0b0b0]'
            }`}
          >
            {track.status}
          </span>
        </div>
        <div>
          <span className="text-[#777777]">Progress:</span>{' '}
          <span className="text-[#e0e0e0]">{track.progress}%</span>
        </div>
        <div>
          <span className="text-[#777777]">URL:</span>{' '}
          <span className="text-[#e0e0e0] font-mono truncate block max-w-[200px]">
            {track.url || '—'}
          </span>
        </div>
      </div>
      {track.status === 'completed' && track.url && (
        <div className="mt-3">
          <audio controls src={track.url} className="w-full" preload="metadata" />
        </div>
      )}
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}
