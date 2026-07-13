/**
 * ProvenanceTimeline — Visualizes the complete operation chain
 * from generation → remix → trim → export for each track.
 *
 * Displays a vertical timeline with color-coded operation nodes,
 * timestamps, parameter summaries, and links to related tracks.
 */

import { useMemo } from 'react';
import type {
  ProjectProvenance,
  ProvenanceOperation,
  ProvenanceOperationType,
} from '../../types/trackStudio';
import { formatDate } from '../../types/trackStudio';

// ── Operation Metadata ──────────────────────────────────────────────────────

interface OpMeta {
  label: string;
  icon: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

const OP_META: Record<ProvenanceOperationType, OpMeta> = {
  generate: {
    label: '生成',
    icon: '✨',
    color: 'text-[#76b900]',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/40',
  },
  remix_pitch_shift: {
    label: '移调',
    icon: '🎚️',
    color: 'text-violet-400',
    bgColor: 'bg-violet-500/10',
    borderColor: 'border-violet-500/40',
  },
  remix_tempo_change: {
    label: '变速',
    icon: '⏱️',
    color: 'text-sky-400',
    bgColor: 'bg-sky-500/10',
    borderColor: 'border-sky-500/40',
  },
  remix_timbre_transform: {
    label: '音色变换',
    icon: '🎨',
    color: 'text-[#febc2e]',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/40',
  },
  trim: {
    label: '裁剪',
    icon: '✂️',
    color: 'text-rose-400',
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-rose-500/40',
  },
  download: {
    label: '下载',
    icon: '📥',
    color: 'text-teal-400',
    bgColor: 'bg-teal-500/10',
    borderColor: 'border-teal-500/40',
  },
  mv_generate: {
    label: 'MV 生成',
    icon: '🎬',
    color: 'text-fuchsia-400',
    bgColor: 'bg-fuchsia-500/10',
    borderColor: 'border-fuchsia-500/40',
  },
};

// ── Helper: extract param summary from operation ────────────────────────────

function getParamSummary(op: ProvenanceOperation): string {
  const { type, params } = op;
  switch (type) {
    case 'generate':
      return params.prompt
        ? `"${String(params.prompt).slice(0, 60)}${String(params.prompt).length > 60 ? '…' : ''}"`
        : '';
    case 'remix_pitch_shift':
      return `±${params.pitchShift ?? 0}st`;
    case 'remix_tempo_change':
      return `${params.tempoMultiplier ?? 1}×`;
    case 'remix_timbre_transform':
      return params.timbreTransform
        ? `${params.timbreTransform}`
        : '';
    case 'trim':
      return `${params.start ?? 0}s – ${params.end ?? 0}s`;
    case 'download':
      return 'Exported';
    case 'mv_generate':
      return `${params.resolution ?? '1080p'}, ${params.style ?? 'auto'}`;
    default:
      return '';
  }
}

// ── Component ───────────────────────────────────────────────────────────────

interface ProvenanceTimelineProps {
  provenance: ProjectProvenance;
  compact?: boolean;
}

export function ProvenanceTimeline({
  provenance,
  compact = false,
}: ProvenanceTimelineProps) {
  const sortedOps = useMemo(
    () => [...provenance.operations].sort((a, b) => a.timestamp - b.timestamp),
    [provenance.operations],
  );

  if (sortedOps.length === 0) {
    return (
      <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f]/50 p-6 text-center">
        <p className="text-sm text-[#777777]">暂无操作记录</p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-[#2a2a38] bg-[#1f1f1f]/50 ${compact ? 'p-4' : 'p-6'}`}
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔗</span>
          <h3 className="text-sm font-semibold text-[#e0e0e0]">
            溯源时间轴
          </h3>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
              provenance.originality === 'original'
                ? 'bg-emerald-500/20 text-[#76b900]'
                : 'bg-amber-500/20 text-[#febc2e]'
            }`}
          >
            {provenance.originality === 'original' ? '原创' : '衍生'}
          </span>
        </div>
        <span className="text-[11px] text-[#777777] font-mono">
          {provenance.projectId.slice(0, 8)}
        </span>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[15px] top-2 bottom-2 w-px bg-gradient-to-b from-gray-700 via-gray-600 to-gray-700" />

        <div className="space-y-3">
          {sortedOps.map((op, idx) => {
            const meta = OP_META[op.type];
            const hasResult = !!op.resultTrackId;

            return (
              <div key={`${op.type}-${op.timestamp}-${idx}`} className="relative flex gap-4">
                {/* Node dot */}
                <div
                  className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${meta.borderColor} ${meta.bgColor}`}
                >
                  <span className="text-xs">{meta.icon}</span>
                </div>

                {/* Content card */}
                <div className={`flex-1 rounded-lg border ${meta.borderColor} ${meta.bgColor} p-3`}>
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-semibold ${meta.color}`}>
                      {meta.label}
                    </span>
                    <span className="text-[11px] text-[#777777] font-mono">
                      {formatDate(op.timestamp)}
                    </span>
                  </div>

                  {/* Param summary */}
                  {getParamSummary(op) && (
                    <p className="mt-1 text-xs text-[#b0b0b0] truncate">
                      {getParamSummary(op)}
                    </p>
                  )}

                  {/* Result track link */}
                  {hasResult && (
                    <span className="mt-1 inline-block rounded bg-[#262626]/60 px-1.5 py-0.5 text-[10px] font-mono text-[#777777]">
                      → {op.resultTrackId}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer: hash & proof */}
      {(provenance.outputHash || provenance.proofDocument) && (
        <div className="mt-4 border-t border-[#2a2a38] pt-3">
          {provenance.outputHash && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-[#777777]">指纹:</span>
              <code className="text-[10px] font-mono text-[#777777] truncate max-w-[200px]">
                {provenance.outputHash}
              </code>
            </div>
          )}
          {provenance.proofDocument && (
            <button
              className="mt-2 text-[11px] text-[#777777] hover:text-[#e0e0e0] transition-colors"
              onClick={() => {
                const blob = new Blob(
                  [JSON.stringify(provenance.proofDocument, null, 2)],
                  { type: 'application/json' },
                );
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `provenance-${provenance.projectId.slice(0, 8)}.jsonld`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              📄 导出 JSON-LD 证明文档
            </button>
          )}
        </div>
      )}
    </div>
  );
}
