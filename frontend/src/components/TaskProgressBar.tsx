/**
 * TaskProgressBar — Visual progress indicator driven by WebSocket state.
 *
 * Colors:
 *   running   → blue   (animate pulse)
 *   loading   → yellow
 *   completed → green
 *   failed    → red
 *   cancelled → gray
 *   default   → gray
 *
 * On completed: renders an audio player if resultUrl is audio,
 * or shows elapsed_time if available.
 */

import { useWebSocketProgress } from '../hooks/useWebSocketProgress';

interface Props {
  taskId: string | null;
  className?: string;
}

const STATUS_COLORS: Record<string, string> = {
  running: 'bg-blue-500',
  loading: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-gray-400',
  pending: 'bg-gray-300',
};

const STATUS_LABELS: Record<string, string> = {
  running: 'Running',
  loading: 'Loading...',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  pending: 'Pending',
};

const AUDIO_EXTENSIONS = /\.(wav|mp3|m4a|ogg|flac)$/i;

function isAudioUrl(url: string): boolean {
  return AUDIO_EXTENSIONS.test(url);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}

export function TaskProgressBar({ taskId, className = '' }: Props) {
  const { progress, status, message, error, resultUrl, elapsedTime } =
    useWebSocketProgress(taskId);

  const colorClass = STATUS_COLORS[status] || 'bg-gray-300';
  const label = STATUS_LABELS[status] || status || 'Waiting';

  return (
    <div className={`w-full max-w-xl mx-auto ${className}`}>
      {/* Header: label + percentage */}
      <div className="flex justify-between items-center mb-2">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="text-sm font-bold text-gray-900">{progress}%</span>
      </div>

      {/* Progress bar track */}
      <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${colorClass}`}
          style={{ width: `${progress}%` }}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>

      {/* Status message + elapsed time */}
      <div className="mt-2 flex justify-between items-center">
        {message && (
          <p className="text-xs text-gray-500 truncate">{message}</p>
        )}
        {elapsedTime !== null && (
          <p className="text-xs text-gray-400 ml-2">Elapsed: {formatDuration(elapsedTime)}</p>
        )}
      </div>

      {/* Error overlay */}
      {error && (
        <p className="mt-2 text-xs text-red-600 font-medium">{error}</p>
      )}

      {/* Audio player on completion */}
      {status === 'completed' && resultUrl && (
        <div className="mt-3 space-y-2">
          {isAudioUrl(resultUrl) ? (
            <audio
              controls
              src={resultUrl}
              className="w-full"
            >
              Your browser does not support the audio element.
            </audio>
          ) : (
            <a
              href={resultUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-sm text-blue-600 hover:underline"
            >
              Download result →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ── Re-export the hook for convenience ─────────────────────────────────────
export { useWebSocketProgress };
