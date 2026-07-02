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
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
        Active Sessions
      </h2>

      {/* Grid of track cards */}
      <div
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(${Math.min(tracks.length, 3)}, minmax(0, 1fr))` }}
      >
        {tracks.map((track, idx) => (
          <button
            key={track.id}
            onClick={() =>
              onTrackSelect(track.id === selectedTrack ? null : track.id)
            }
            className={`relative rounded-xl border-2 p-4 text-left transition-all overflow-hidden ${
              selectedTrack === track.id
                ? 'border-blue-500 bg-blue-500/10'
                : track.status === 'completed'
                  ? 'border-emerald-800 bg-emerald-950/30 hover:border-emerald-600'
                  : track.status === 'failed'
                    ? 'border-red-800 bg-red-950/30'
                    : 'border-gray-800 bg-gray-900/50 hover:border-gray-600'
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
                <p className="text-xs text-gray-500 capitalize">{track.status}</p>
              </div>
            </div>

            {track.status === 'running' && (
              <div className="mt-2">
                <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${TRACK_COLORS[idx % TRACK_COLORS.length]}`}
                    style={{ width: `${track.progress}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">{track.progress}%</p>
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
              <p className="text-xs text-gray-500 mt-2">No audio URL</p>
            )}
          </button>
        ))}
      </div>

      {/* Live Status Banner */}
      {(wsStatus || wsMessage) && (
        <div className="rounded-xl border border-blue-800 bg-blue-950/30 p-4">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-blue-300">
                  {wsStatus === 'loading' && '🔄 Loading model...'}
                  {wsStatus === 'running' && '🎵 Generating...'}
                  {wsStatus === 'pending' && '⏳ Queued...'}
                  {wsStatus === 'completed' && '✅ Done!'}
                  {wsStatus === 'failed' && '❌ Failed'}
                  {!wsStatus && '⏳ Starting...'}
                </span>
                <span className="text-sm font-bold text-blue-400">
                  {wsProgress}%
                </span>
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-violet-500 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${wsProgress}%` }}
                />
              </div>
              {wsMessage && <p className="text-xs text-gray-500 mt-1">{wsMessage}</p>}
              {wsElapsedTime !== null && wsElapsedTime > 0 && (
                <p className="text-xs text-gray-600 mt-1">
                  Elapsed: {formatDuration(wsElapsedTime)}
                </p>
              )}
            </div>
            {wsConnected && (
              <span className="text-xs text-blue-400 animate-pulse">● LIVE</span>
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
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300">
          Track Detail: {track.name}
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          ✕ Close
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <span className="text-gray-500">Type:</span>{' '}
          <span className="capitalize text-gray-300">{track.type}</span>
        </div>
        <div>
          <span className="text-gray-500">Status:</span>{' '}
          <span
            className={`capitalize ${
              track.status === 'completed'
                ? 'text-emerald-400'
                : track.status === 'failed'
                  ? 'text-red-400'
                  : track.status === 'running'
                    ? 'text-amber-400'
                    : 'text-gray-400'
            }`}
          >
            {track.status}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Progress:</span>{' '}
          <span className="text-gray-300">{track.progress}%</span>
        </div>
        <div>
          <span className="text-gray-500">URL:</span>{' '}
          <span className="text-gray-300 font-mono truncate block max-w-[200px]">
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
