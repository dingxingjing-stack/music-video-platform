/**
 * BatchProgressDashboard — Visual dashboard for batch-mode processing.
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
    <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f] p-5 space-y-4" style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">📦</span>
          <div>
            <h3 className="text-sm font-semibold text-[#ff6a10]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {batchState.running ? 'Batch Processing' : 'Batch Error'}
            </h3>
            <p className="text-xs text-[#b0b0b0]">
              {pathLabel} — {batchState.total} tasks
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {batchState.running && (
            <span className="text-xs text-[#ff6a10] animate-pulse font-mono">
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
        <div className="bg-[#262626] rounded-lg p-2">
          <p className="text-lg font-bold text-[#e0e0e0]">{batchState.total}</p>
          <p className="text-xs text-[#777777]">Total</p>
        </div>
        <div className="bg-[#76b900]/10 rounded-lg p-2">
          <p className="text-lg font-bold text-[#76b900]">{batchState.completed}</p>
          <p className="text-xs text-[#777777]">Done</p>
        </div>
        <div className="bg-red-950/30 rounded-lg p-2">
          <p className="text-lg font-bold text-[#ef4444]">{batchState.failed}</p>
          <p className="text-xs text-[#777777]">Failed</p>
        </div>
        <div className="bg-[#262626] rounded-lg p-2">
          <p className="text-lg font-bold text-[#ff6a10]">{batchState.running ? eta : '—'}</p>
          <p className="text-xs text-[#777777]">ETA</p>
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-[#b0b0b0] truncate max-w-[60%]">
            {batchState.currentPrompt
              ? `▶ ${batchState.currentPrompt}`
              : batchState.running
                ? 'Initializing...'
                : ''}
          </span>
          <span className="text-xs font-mono text-[#ff6a10]">
            {batchState.completed}/{batchState.total} ({Math.round(
              (batchState.completed / Math.max(batchState.total, 1)) * 100,
            )}%)
          </span>
        </div>
        <div className="w-full h-3 bg-[#262626] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-[#ff6a10] to-[#ff6a10] rounded-full transition-all duration-700 ease-out"
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
        <div className="rounded-lg border border-red-800/50 bg-red-950/20 p-3">
          <p className="text-xs text-red-400 font-mono">{batchState.error}</p>
        </div>
      )}
    </div>
  );
}
