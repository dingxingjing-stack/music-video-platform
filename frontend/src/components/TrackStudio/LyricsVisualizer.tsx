/**
 * LyricsVisualizer — synced waveform + lyrics subtitle display
 *
 * Features:
 *  - Waveform visualization with lyric-sync markers
 *  - LRC / JSON timestamp-based lyric rendering
 *  - Scrolling subtitle view with current line highlight
 *  - Playback sync via audio player ref
 */

import { useEffect, useRef } from 'react';
import { Music, Clock } from 'lucide-react';

// ---- Types ----------------------------------------------------------------

interface LyricLine {
  time: number;        // start time in seconds
  text: string;
  duration?: number;   // line duration in seconds (optional)
}

interface Props {
  lyrics: LyricLine[];
  currentTime: number;         // Current playback position in seconds
  duration: number;            // Total audio duration in seconds
  compact?: boolean;
}

// ---- Constants ------------------------------------------------------------

const WAVEFORM_BARS = 64;
const BAR_MAX_HEIGHT = 40;
const COLORS = {
  waveform: '#6366f1',       // Indigo
  waveformBg: '#e0e7ff',     // Indigo-100
  cursor: '#ef4444',         // Red
  currentLyric: '#1d4ed8',   // Blue-700
  pastLyric: '#6b7280',      // Gray-500
  futureLyric: '#9ca3af',    // Gray-400
};

// ---- Waveform (simple bar-based, no Web Audio) -----------------------------

function WaveformBars({ progress, compact }: { progress: number; compact: boolean }) {
  // Generate pseudo-waveform bars based on a deterministic pattern
  const bars = Array.from({ length: WAVEFORM_BARS }, (_, i) => {
    const seed = Math.sin(i * 3.7 + 1.2) * 0.5 + 0.5;
    const pos = (i / WAVEFORM_BARS) * progress * 2;
    const amp = Math.sin(pos * Math.PI * 3) * 0.4 + seed * 0.6;
    return Math.max(0.12, Math.min(1.0, Math.abs(amp)));
  });

  const barWidth = compact ? 2.5 : 4;
  const gap = compact ? 0.5 : 1;

  return (
    <div className="flex items-end" style={{ height: BAR_MAX_HEIGHT, gap }}>
      {bars.map((h, i) => {
        const isPast = (i / WAVEFORM_BARS) < progress;
        return (
          <div
            key={i}
            style={{
              width: barWidth,
              height: h * BAR_MAX_HEIGHT,
              backgroundColor: isPast ? COLORS.waveform : COLORS.waveformBg,
              borderRadius: 1,
              transition: 'background-color 0.15s',
            }}
          />
        );
      })}
    </div>
  );
}

// ---- Current time indicator -----------------------------------------------

function TimeCursor({ progress, compact }: { progress: number; compact: boolean }) {
  const leftPct = progress * 100;
  return (
    <div className="relative" style={{ height: compact ? 4 : 8 }}>
      <div
        className="absolute top-0 w-0.5 bg-red-500 rounded"
        style={{
          left: `${leftPct}%`,
          height: '100%',
          transition: 'left 0.1s linear',
        }}
      />
    </div>
  );
}

// ---- Lyric display --------------------------------------------------------

function LyricsDisplay({
  lyrics,
  currentTime,
  compact,
}: {
  lyrics: LyricLine[];
  currentTime: number;
  compact: boolean;
}) {
  const activeRef = useRef<HTMLDivElement>(null);

  // Find the current lyric line
  let activeIdx = -1;
  for (let i = lyrics.length - 1; i >= 0; i--) {
    if (currentTime >= lyrics[i].time) {
      activeIdx = i;
      break;
    }
  }

  // Auto-scroll to active line
  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [activeIdx]);

  if (lyrics.length === 0) {
    return (
      <p className="text-xs text-gray-400 italic">
        No lyrics loaded. Generate or paste lyrics above.
      </p>
    );
  }

  const showCount = compact ? 4 : 8;
  const startIdx = Math.max(0, activeIdx - Math.floor(showCount / 2));
  const endIdx = Math.min(lyrics.length, startIdx + showCount);
  const visibleLyrics = lyrics.slice(startIdx, endIdx);

  return (
    <div
      className="overflow-hidden rounded border border-gray-200"
      style={{ maxHeight: compact ? 70 : 140 }}
    >
      <div className="space-y-0.5 p-1">
        {visibleLyrics.map((line, i) => {
          const globalIdx = startIdx + i;
          const isCurrent = globalIdx === activeIdx;
          const isPast = globalIdx < activeIdx;

          return (
            <div
              key={globalIdx}
              ref={isCurrent ? activeRef : undefined}
              className={`px-1.5 py-0.5 rounded transition-colors ${
                isCurrent
                  ? 'bg-blue-100 font-semibold'
                  : isPast
                  ? ''
                  : ''
              }`}
              style={{ fontSize: compact ? 11 : 13 }}
            >
              {isPast && (
                <span
                  className="inline-block w-8 text-right mr-1"
                  style={{ color: COLORS.pastLyric, fontSize: 10 }}
                >
                  {formatTime(line.time)}
                </span>
              )}
              {isCurrent && (
                <span
                  className="inline-block w-8 text-right mr-1 font-bold"
                  style={{ color: COLORS.currentLyric, fontSize: 10 }}
                >
                  {formatTime(line.time)}
                </span>
              )}
              <span
                style={{
                  color: isPast
                    ? COLORS.pastLyric
                    : isCurrent
                    ? COLORS.currentLyric
                    : COLORS.futureLyric,
                }}
              >
                {line.text}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(0).padStart(2, '0');
  return `${m}:${s}`;
}

// ---- Main component --------------------------------------------------------

export default function LyricsVisualizer({ lyrics, currentTime, duration, compact = false }: Props) {
  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;

  return (
    <div className="lyrics-visualizer" style={{ width: '100%' }}>
      {/* Header */}
      {!compact && (
        <div className="flex items-center gap-2 mb-1">
          <Music size={14} className="text-indigo-500" />
          <span className="text-xs font-medium text-gray-600">Lyrics Sync</span>
          <span className="text-[10px] text-gray-400">
            {lyrics.length} lines · {formatTime(currentTime)} / {formatTime(duration)}
          </span>
        </div>
      )}

      {/* Waveform area */}
      <div className="mb-1">
        <WaveformBars progress={progress} compact={compact} />
        <TimeCursor progress={progress} compact={compact} />
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-1 text-[10px] text-gray-400 mb-1">
        <Clock size={10} />
        <span>{formatTime(currentTime)}</span>
        <div className="flex-1 h-1 bg-gray-200 rounded mx-1">
          <div
            className="h-full bg-indigo-500 rounded transition-all duration-100"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <span>{formatTime(duration)}</span>
      </div>

      {/* Lyrics */}
      <LyricsDisplay lyrics={lyrics} currentTime={currentTime} compact={compact} />
    </div>
  );
}

// ---- Parser: LRC string → LyricLine[] --------------------------------------

export function parseLRC(lrcText: string): LyricLine[] {
  const lines: LyricLine[] = [];
  const timeRegex = /\[(\d{2}):(\d{2})(?:\.(\d{1,3}))?\]/g;

  for (const rawLine of lrcText.split('\n')) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;

    const times: number[] = [];
    let match: RegExpExecArray | null;
    let lastMatchEnd = 0;

    // Collect all timestamps in this line
    while ((match = timeRegex.exec(trimmed)) !== null) {
      const minutes = parseInt(match[1], 10);
      const seconds = parseInt(match[2], 10);
      const ms = match[3] ? parseInt(match[3].padEnd(3, '0'), 10) : 0;
      times.push(minutes * 60 + seconds + ms / 1000);
      lastMatchEnd = match.index + match[0].length;
    }

    if (times.length === 0) continue;

    // Text after all timestamps
    const text = trimmed.slice(lastMatchEnd).trim();
    if (!text) continue;

    for (const t of times) {
      lines.push({ time: t, text });
    }
  }

  // Sort by time
  lines.sort((a, b) => a.time - b.time);

  // Compute durations
  for (let i = 0; i < lines.length; i++) {
    if (i < lines.length - 1) {
      lines[i].duration = Math.max(0.5, lines[i + 1].time - lines[i].time);
    }
  }

  return lines;
}

// ---- Parser: JSON → LyricLine[] -------------------------------------------

export function parseLyricJSON(json: { lines: { time: number; text: string }[] }): LyricLine[] {
  return (json.lines || []).map((l, i, arr) => ({
    time: l.time,
    text: l.text,
    duration: i < arr.length - 1 ? arr[i + 1].time - l.time : undefined,
  }));
}