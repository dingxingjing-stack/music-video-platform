/**
 * BatchProgressDashboard — Visual dashboard for batch-mode processing.
 *
 * Shows total/done/failed counts, progress bar, current prompt, ETA, and errors.
 */

import { useMemo } from 'react';
import type { BatchState } from '../../types/trackStudio';

interface Props {
  batchState: BatchState;
  getETA: () => string;
}

export function BatchProgressDashboard({ batchState, getETA }: Props) {
  const eta = useMemo(() => getETA(), [getETA]);
  const pathLabel =
    batchState.path === 'a'
      ? 'Path A'
      : batchState.path === 'b'
        ? 'Path B'
        : 'Batch';

  return (
    <div className="rounded-xl border border-purple-800 bg-purple-950/30 p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">📦</span>
          <div>
            <h3 className="text-sm font-semibold text-purple-300">
              {batchState.running ? 'Batch Processing' : 'Batch Error'}
            </h3>
            <p className="text-xs text-purple-400">
              {pathLabel} — {batchState.total} tasks
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {batchState.running && (
            <span className="text-xs text-purple-400 animate-pulse font-mono">
              ● LIVE
            </span>
          )}
          {batchState.error && (
            <span className="text-xs text-red-400 font-mono">✕ ERROR</span>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3 text-center">
        <div className="bg-gray-900/50 rounded-lg p-2">
          <p className="text-lg font-bold text-white">{batchState.total}</p>
          <p className="text-xs text-gray-500">Total</p>
        </div>
        <div className="bg-emerald-950/30 rounded-lg p-2">
          <p className="text-lg font-bold text-emerald-400">{batchState.completed}</p>
          <p className="text-xs text-gray-500">Done</p>
        </div>
        <div className="bg-red-950/30 rounded-lg p-2">
          <p className="text-lg font-bold text-red-400">{batchState.failed}</p>
          <p className="text-xs text-gray-500">Failed</p>
        </div>
        <div className="bg-blue-950/30 rounded-lg p-2">
          <p className="text-lg font-bold text-blue-400">{batchState.running ? eta : '—'}</p>
          <p className="text-xs text-gray-500">ETA</p>
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-purple-400 truncate max-w-[60%]">
            {batchState.currentPrompt
              ? `▶ ${batchState.currentPrompt}`
              : batchState.running
                ? 'Initializing...'
                : ''}
          </span>
          <span className="text-xs font-mono text-purple-300">
            {batchState.completed}/{batchState.total} (
            {Math.round(
              (batchState.completed / Math.max(batchState.total, 1)) * 100,
            )}
            %)
          </span>
        </div>
        <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-purple-500 via-fuchsia-500 to-pink-500 rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${
                batchState.total > 0
                  ? ((batchState.completed + batchState.failed) / batchState.total) * 100
                  : 0
              }%`,
            }}
          />
        </div>
      </div>

      {/* Error detail */}
      {batchState.error && (
        <div className="rounded-lg bg-red-950/50 p-3">
          <p className="text-xs text-red-300 font-mono">{batchState.error}</p>
        </div>
      )}
    </div>
  );
}
