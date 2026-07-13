/**
 * AudioPlayer — Full-featured audio playback UI with trim, rename, download.
 *
 * Features:
 *   - Play/pause with custom controls
 *   - Trim range (start/end sliders + numeric inputs)
 *   - Trimmed snippet download via /api/v1/audio/trim
 *   - Full-file download
 *   - Inline rename
 *   - Delete with confirmation
 *
 * Uses MiniWaveform internally for visual feedback.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import type { Track } from '../../types/trackStudio';
import { MiniWaveform } from './MiniWaveform';

interface Props {
  track: Track;
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
  onTrimChange: (trackId: string, start: number, end: number) => void;
}

export function AudioPlayer({ track, onRename, onDelete, onTrimChange }: Props) {
  const [showRename, setShowRename] = useState(false);
  const [renameValue, setRenameValue] = useState(track.name);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [trimStart, setTrimStart] = useState(track.trimStart ?? 0);
  const [trimEnd, setTrimEnd] = useState(track.trimEnd ?? 0);
  const [showTrim, setShowTrim] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Reset trim when track changes
  useEffect(() => {
    setTrimStart(track.trimStart ?? 0);
    setTrimEnd(track.trimEnd ?? 0);
  }, [track.trimStart, track.trimEnd]);

  // Debounced trim persistence
  useEffect(() => {
    const timer = setTimeout(() => {
      onTrimChange(track.id, trimStart, trimEnd);
    }, 300);
    return () => clearTimeout(timer);
  }, [trimStart, trimEnd, track.id, onTrimChange]);

  // Load audio duration on mount
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !track.url) return;
    const metaHandler = () => {
      setDuration(audio.duration);
      setTrimEnd(audio.duration);
      setTrimStart(0);
    };
    if (audio.readyState >= 1) {
      metaHandler();
    } else {
      audio.addEventListener('loadedmetadata', metaHandler);
      return () => audio.removeEventListener('loadedmetadata', metaHandler);
    }
  }, [track.url]);

  // Sync current time with audio element
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const tick = () => setCurrentTime(audio.currentTime);
    audio.addEventListener('timeupdate', tick);
    return () => audio.removeEventListener('timeupdate', tick);
  }, []);

  // Apply trim range when playing
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !isPlaying) return;
    if (audio.currentTime >= trimEnd) {
      audio.currentTime = trimStart;
    }
  }, [trimStart, trimEnd, isPlaying]);

  const setTrimState = useCallback(
    (s: number, e: number) => {
      setTrimStart(s);
      setTrimEnd(e);
      onTrimChange(track.id, s, e);
    },
    [track.id, onTrimChange],
  );

  const handlePlayPause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.currentTime = trimStart;
      audio.play().catch(() => {});
    }
    setIsPlaying(!isPlaying);
  }, [isPlaying, trimStart]);

  const handleDownload = useCallback(() => {
    if (!track.url) return;
    const a = document.createElement('a');
    a.href = track.url;
    a.download = `${renameValue || 'track'}.wav`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [track.url, renameValue]);

  const handleDownloadSnippet = useCallback(async () => {
    if (!track.url) return;
    if (trimEnd - trimStart <= 0.5) {
      alert('Trim range too short. Select at least 0.5 seconds.');
      return;
    }

    setDownloading(true);
    try {
      const params = new URLSearchParams({
        url: track.url,
        start: trimStart.toString(),
        end: trimEnd.toString(),
        fmt: 'wav',
      });
      const resp = await fetch(`/api/v1/audio/trim?${params}`);
      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText}`);
      }
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${renameValue || 'track'}_${Math.round(trimStart)}s-${Math.round(trimEnd)}s.wav`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (err) {
      console.error('Trim download failed:', err);
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('ffmpeg')) {
        alert(
          'Audio trimming requires ffmpeg to be installed on the server.\n\n' +
            'Please install ffmpeg and restart the backend.\n' +
            'Download: https://ffmpeg.org/download.html',
        );
      } else {
        alert(`Download failed: ${msg}`);
      }
    } finally {
      setDownloading(false);
    }
  }, [track.url, track.name, renameValue, trimStart, trimEnd]);

  const handleRenameSave = useCallback(() => {
    if (renameValue.trim()) {
      onRename(track.id, renameValue.trim());
    }
    setShowRename(false);
  }, [renameValue, track.id, onRename]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m > 0 ? `${m}:${sec.toString().padStart(2, '0')}` : `${sec}s`;
  };

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;
  const trimLeftPct = duration > 0 ? (trimStart / duration) * 100 : 0;
  const trimRightPct = duration > 0 ? (trimEnd / duration) * 100 : 100;

  return (
    <div className="mt-3 space-y-2">
      {/* Waveform visualization */}
      <MiniWaveform url={track.url || ''} />

      {/* Audio element (hidden controls, custom UI) */}
      <audio
        ref={audioRef}
        src={track.url || undefined}
        preload="metadata"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
        className="hidden"
      />

      {/* Progress bar with trim overlay */}
      <div className="relative h-6 bg-[#262626] rounded-md overflow-hidden group">
        {/* Trim dim zones (left of start) */}
        <div
          className="absolute inset-y-0 left-0 bg-[#121212]/70"
          style={{ width: `${trimLeftPct}%` }}
        />
        {/* Trim dim zones (right of end) */}
        <div
          className="absolute inset-y-0 right-0 bg-[#121212]/70"
          style={{ width: `${100 - trimRightPct}%` }}
        />
        {/* Active trim zone */}
        <div
          className="absolute inset-y-0 bg-indigo-950/40"
          style={{ left: `${trimLeftPct}%`, width: `${trimRightPct - trimLeftPct}%` }}
        />
        {/* Playback progress */}
        <div
          className="absolute inset-y-0 bg-indigo-500/60"
          style={{ width: `${progressPercent}%` }}
        />
        {/* Start handle */}
        <div
          className="absolute top-0 bottom-0 w-1 bg-emerald-400 cursor-col-resize hover:bg-emerald-300 z-10"
          style={{ left: `${trimLeftPct}%` }}
          title={`Start: ${formatTime(trimStart)}`}
        />
        {/* End handle */}
        <div
          className="absolute top-0 bottom-0 w-1 bg-rose-400 cursor-col-resize hover:bg-rose-300 z-10"
          style={{ left: `${trimRightPct}%` }}
          title={`End: ${formatTime(trimEnd)}`}
        />
        {/* Time labels */}
        <span className="absolute bottom-0.5 left-1 text-[9px] text-[#76b900] font-mono">
          {formatTime(trimStart)}
        </span>
        <span className="absolute bottom-0.5 right-1 text-[9px] text-rose-400 font-mono">
          {formatTime(trimEnd)}
        </span>
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-2">
        {/* Play/Pause */}
        <button
          onClick={handlePlayPause}
          className="w-8 h-8 flex items-center justify-center rounded-full bg-indigo-600 hover:bg-indigo-500 text-[#e0e0e0] text-sm transition-colors"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? '⏸' : '▶'}
        </button>

        {/* Track name */}
        {showRename ? (
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={handleRenameSave}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRenameSave();
              if (e.key === 'Escape') {
                setShowRename(false);
                setRenameValue(track.name);
              }
            }}
            className="flex-1 px-2 py-1 bg-[#262626] border border-indigo-500 rounded text-xs text-[#e0e0e0] focus:outline-none"
          />
        ) : (
          <button
            onClick={() => {
              setShowRename(true);
              setRenameValue(track.name);
            }}
            className="flex-1 text-left text-xs text-[#b0b0b0] hover:text-[#e0e0e0] truncate"
            title="Click to rename"
          >
            {track.name}
          </button>
        )}

        {/* Trim toggle */}
        <button
          onClick={() => setShowTrim(!showTrim)}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            showTrim ? 'bg-indigo-600 text-[#e0e0e0]' : 'text-[#b0b0b0] hover:text-[#e0e0e0]'
          }`}
          title="Toggle trim mode"
        >
          ✂
        </button>

        {/* Download full */}
        <button
          onClick={handleDownload}
          className="px-2 py-1 text-xs text-[#b0b0b0] hover:text-[#e0e0e0] transition-colors"
          title="Download full"
        >
          ⬇
        </button>

        {/* Delete */}
        <button
          onClick={() => {
            if (confirm(`Delete "${track.name}"?`)) onDelete(track.id);
          }}
          className="px-2 py-1 text-xs text-[#b0b0b0] hover:text-[#ef4444] transition-colors"
          title="Delete"
        >
          🗑
        </button>
      </div>

      {/* Trim controls */}
      {showTrim && (
        <div className="space-y-2 pt-1 border-t border-[#2a2a38]">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#777777]">Trim Range</span>
            <span className="text-xs font-mono text-indigo-400">
              {formatTime(trimStart)} → {formatTime(trimEnd)} ({formatTime(trimEnd - trimStart)})
            </span>
          </div>

          {/* Start slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-[#76b900] w-8">Start</label>
            <input
              type="range"
              min={0}
              max={Math.max(duration - 0.5, 0)}
              step={0.1}
              value={trimStart}
              onChange={(e) => {
                const v = Number(e.target.value);
                setTrimState(Math.min(v, trimEnd - 0.5), trimEnd);
              }}
              className="flex-1 h-1 accent-emerald-400"
            />
            <input
              type="number"
              min={0}
              step={0.1}
              value={trimStart.toFixed(1)}
              onChange={(e) =>
                setTrimState(Math.min(Number(e.target.value), trimEnd - 0.5), trimEnd)
              }
              className="w-16 px-1 py-0.5 bg-[#262626] border border-[#2a2a38] rounded text-[10px] text-[#e0e0e0] text-right font-mono"
            />
          </div>

          {/* End slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-rose-400 w-8">End</label>
            <input
              type="range"
              min={0.5}
              max={duration}
              step={0.1}
              value={trimEnd}
              onChange={(e) => {
                const v = Number(e.target.value);
                setTrimState(trimStart, Math.max(v, trimStart + 0.5));
              }}
              className="flex-1 h-1 accent-rose-400"
            />
            <input
              type="number"
              min={0}
              step={0.1}
              value={trimEnd.toFixed(1)}
              onChange={(e) =>
                setTrimState(trimStart, Math.max(Number(e.target.value), trimStart + 0.5))
              }
              className="w-16 px-1 py-0.5 bg-[#262626] border border-[#2a2a38] rounded text-[10px] text-[#e0e0e0] text-right font-mono"
            />
          </div>

          {/* Download snippet button */}
          <button
            onClick={handleDownloadSnippet}
            disabled={downloading}
            className="w-full px-3 py-1.5 text-xs bg-gradient-to-r from-indigo-600 to-violet-600 text-[#e0e0e0] rounded-lg hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 transition-all"
          >
            {downloading
              ? '⏳ Trimming...'
              : `✂ Download Snippet (${formatTime(trimEnd - trimStart)})`}
          </button>
        </div>
      )}
    </div>
  );
}
