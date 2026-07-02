/**
 * HistoryPanel — Grid of saved (completed) tracks with delete and clear actions.
 *
 * Completed tracks can expose a RemixTool for audio modification.
 */

import { useCallback } from 'react';
import type { Track } from '../../types/trackStudio';
import { formatDate } from '../../types/trackStudio';
import { AudioPlayer } from '../Audio/AudioPlayer';
import { RemixTool } from './RemixTool';

interface Props {
  history: Track[];
  onClear: () => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onTrimChange: (trackId: string, start: number, end: number) => void;
  onRemixComplete?: (newTrack: Track) => void;
  onRemixError?: (error: string) => void;
}

export function HistoryPanel({
  history,
  onClear,
  onRename,
  onDelete,
  onTrimChange,
  onRemixComplete,
  onRemixError,
}: Props) {
  if (history.length === 0) return null;

  const handleClear = useCallback(() => {
    if (confirm('Clear all saved tracks?')) {
      onClear();
    }
  }, [onClear]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Saved Tracks ({history.length})
        </h2>
        <button
          onClick={handleClear}
          className="text-xs text-gray-600 hover:text-red-400 transition-colors"
        >
          Clear All
        </button>
      </div>
      <div
        className="grid gap-3 overflow-y-auto pr-1"
        style={{
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          maxHeight: '500px',
        }}
      >
        {/* Custom scrollbar styles */}
        <style>{`
          div::-webkit-scrollbar { width: 6px; }
          div::-webkit-scrollbar-track { background: rgba(31, 41, 55, 0.5); border-radius: 3px; }
          div::-webkit-scrollbar-thumb { background: rgba(107, 114, 128, 0.5); border-radius: 3px; }
          div::-webkit-scrollbar-thumb:hover { background: rgba(156, 163, 175, 0.7); }
        `}</style>
        {history.map((track) => (
          <div
            key={track.id}
            className={`rounded-xl border-2 p-3 text-left transition-all flex-shrink-0 ${
              track.status === 'completed'
                ? 'border-gray-800 bg-gray-900/50 hover:border-gray-600'
                : 'border-red-900 bg-red-950/20'
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">
                {track.type === 'music'
                  ? '🎵'
                  : track.type === 'tts'
                    ? '🎤'
                    : '🎛️'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium truncate">{track.name}</p>
                <p className="text-xs text-gray-600">
                  {track.createdAt ? formatDate(track.createdAt) : ''}
                </p>
              </div>
              <button
                onClick={() => onDelete(track.id)}
                className="text-xs text-gray-600 hover:text-red-400 transition-colors"
                title="Delete"
              >
                ✕
              </button>
            </div>

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
          </div>
        ))}
      </div>
    </div>
  );
}
