/**
 * TrackStudio — AI Music Workbench DAW Interface
 *
 * Features:
 *   - Three workflow paths: A (Suno), B (Hybrid), C (Remix)
 *   - Visual track lanes with real-time progress
 *   - Audio playback per track with waveform visualization
 *   - Download, rename, and delete tracks
 *   - Persistent history via localStorage
 *   - WebSocket-driven progress updates with reconnect + backoff
 *   - Collapsible track panels with stem listing
 *   - Live status banner
 *
 * Layout:
 *   [Header] [Path Selector] [Prompt/Input Area]
 *   [Live Status Banner]
 *   [Track Lanes — horizontal timeline view]
 *   [Selected Track Detail Panel]
 *   [History Panel — persisted tracks]
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useWebSocketProgress } from '../hooks/useWebSocketProgress';

// ── Types ──────────────────────────────────────────────────────────────────

interface Track {
  id: string;
  name: string;
  type: 'music' | 'tts' | 'stem' | 'stem_zip';
  status: 'queued' | 'running' | 'completed' | 'failed';
  url: string | null;
  progress: number;
  color: string;
  createdAt?: number;
  trimStart?: number;
  trimEnd?: number;
}

interface PersistedSession {
  version: number;
  activeWorkflow: {
    path: 'a' | 'b' | 'c' | null;
    taskId: string | null;
    tracks: Track[];
    running: boolean;
    completed: boolean;
    error: string | null;
  };
  history: Track[];
}

const STORAGE_KEY = 'music-workbench-session';
const STORAGE_VERSION = 1;

function loadPersisted(): PersistedSession {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultPersisted();
    const parsed = JSON.parse(raw);
    return { ...defaultPersisted(), ...parsed, version: STORAGE_VERSION };
  } catch {
    return defaultPersisted();
  }
}

function defaultPersisted(): PersistedSession {
  return {
    version: STORAGE_VERSION,
    activeWorkflow: {
      path: null,
      taskId: null,
      tracks: [],
      running: false,
      completed: false,
      error: null,
    },
    history: [],
  };
}

function savePersisted(session: PersistedSession): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage full or unavailable — silent fail
  }
}

interface ApiResult {
  task_id: string;
  status: string;
  websocket: string;
  path?: string;
}

interface BatchResult {
  batch_id: string;
  path: string;
  total: number;
  status: string;
  websocket: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

const TRACK_COLORS = [
  'bg-violet-500',
  'bg-sky-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-indigo-500',
];

const PATHS = [
  {
    id: 'a' as const,
    label: 'Path A — Suno Style',
    desc: 'Prompt → MusicGen → Full Audio',
    icon: '🎵',
    prompt: 'upbeat electronic dance music with synth lead',
    inputLabel: 'Music Prompt',
  },
  {
    id: 'b' as const,
    label: 'Path B — Hybrid',
    desc: 'Music Gen + TTS Vocals → Combined Track',
    icon: '🎤',
    prompt: 'chill lofi hip hop beat',
    musicLabel: 'Music Prompt',
    ttsLabel: 'TTS Text',
    ttsDefault: '今天天气真好，阳光明媚',
  },
  {
    id: 'c' as const,
    label: 'Path C — Remix',
    desc: 'Upload Audio → Demucs Stem Separation',
    icon: '🎛️',
    inputLabel: 'Audio File',
  },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}

function formatDate(timestamp: number): string {
  const d = new Date(timestamp);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ── Mini Waveform Component ────────────────────────────────────────────────

function MiniWaveform({ url, className = '' }: { url: string; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Draw placeholder waveform
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, w, h);

    // Generate synthetic waveform bars
    const barCount = 40;
    const barWidth = 2;
    const gap = (w - barCount * barWidth) / (barCount - 1);
    ctx.fillStyle = '#6366f1';

    for (let i = 0; i < barCount; i++) {
      const x = i * (barWidth + gap);
      // Simulate audio amplitude pattern
      const amp = Math.sin(i * 0.3) * 0.3 + Math.sin(i * 0.7) * 0.2 + Math.random() * 0.5;
      const barH = Math.max(4, Math.abs(amp) * h * 0.8);
      const y = (h - barH) / 2;
      ctx.globalAlpha = 0.4 + Math.abs(amp) * 0.6;
      ctx.fillRect(x, y, barWidth, barH);
    }
    ctx.globalAlpha = 1;
  }, [url]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={40}
      className={`rounded ${className}`}
      style={{ imageRendering: 'pixelated' }}
    />
  );
}

// ── Audio Player with Controls ─────────────────────────────────────────────

function AudioPlayer({
  track,
  onRename,
  onDelete,
  onTrimChange,
}: {
  track: Track;
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
  onTrimChange: (trackId: string, start: number, end: number) => void;
}) {
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

  // Persist trim state to parent on change
  const setTrimState = useCallback((s: number, e: number) => {
    setTrimStart(s);
    setTrimEnd(e);
    onTrimChange(track.id, s, e);
  }, [track.id, onTrimChange]);

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
          'Download: https://ffmpeg.org/download.html'
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
      <div className="relative h-6 bg-gray-800 rounded-md overflow-hidden group">
        {/* Trim dim zones (left of start) */}
        <div
          className="absolute inset-y-0 left-0 bg-gray-950/70"
          style={{ width: `${trimLeftPct}%` }}
        />
        {/* Trim dim zones (right of end) */}
        <div
          className="absolute inset-y-0 right-0 bg-gray-950/70"
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
        <span className="absolute bottom-0.5 left-1 text-[9px] text-emerald-400 font-mono">
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
          className="w-8 h-8 flex items-center justify-center rounded-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm transition-colors"
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
              if (e.key === 'Escape') { setShowRename(false); setRenameValue(track.name); }
            }}
            className="flex-1 px-2 py-1 bg-gray-800 border border-indigo-500 rounded text-xs text-white focus:outline-none"
          />
        ) : (
          <button
            onClick={() => { setShowRename(true); setRenameValue(track.name); }}
            className="flex-1 text-left text-xs text-gray-400 hover:text-white truncate"
            title="Click to rename"
          >
            {track.name}
          </button>
        )}

        {/* Trim toggle */}
        <button
          onClick={() => setShowTrim(!showTrim)}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            showTrim ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
          }`}
          title="Toggle trim mode"
        >
          ✂
        </button>

        {/* Download full */}
        <button
          onClick={handleDownload}
          className="px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
          title="Download full"
        >
          ⬇
        </button>

        {/* Delete */}
        <button
          onClick={() => {
            if (confirm(`Delete "${track.name}"?`)) onDelete(track.id);
          }}
          className="px-2 py-1 text-xs text-gray-400 hover:text-red-400 transition-colors"
          title="Delete"
        >
          🗑
        </button>
      </div>

      {/* Trim controls */}
      {showTrim && (
        <div className="space-y-2 pt-1 border-t border-gray-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Trim Range</span>
            <span className="text-xs font-mono text-indigo-400">
              {formatTime(trimStart)} → {formatTime(trimEnd)} ({formatTime(trimEnd - trimStart)})
            </span>
          </div>

          {/* Start slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-emerald-400 w-8">Start</label>
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
              onChange={(e) => setTrimState(Math.min(Number(e.target.value), trimEnd - 0.5), trimEnd)}
              className="w-16 px-1 py-0.5 bg-gray-800 border border-gray-700 rounded text-[10px] text-white text-right font-mono"
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
              onChange={(e) => setTrimState(trimStart, Math.max(Number(e.target.value), trimStart + 0.5))}
              className="w-16 px-1 py-0.5 bg-gray-800 border border-gray-700 rounded text-[10px] text-white text-right font-mono"
            />
          </div>

          {/* Download snippet button */}
          <button
            onClick={handleDownloadSnippet}
            disabled={downloading}
            className="w-full px-3 py-1.5 text-xs bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-lg hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 transition-all"
          >
            {downloading ? '⏳ Trimming...' : `✂ Download Snippet (${formatTime(trimEnd - trimStart)})`}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export function TrackStudio() {
  // Load persisted state
  const [persisted] = useState(loadPersisted);

  const [selectedPath, setSelectedPath] = useState<'a' | 'b' | 'c'>('a');
  const [prompt, setPrompt] = useState(PATHS[0].prompt);
  const [ttsText, setTtsText] = useState('');
  const [uploadedFile, setUploadedFile] = useState<{ name: string; base64: string; size: number } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState(persisted.activeWorkflow);
  const [history, setHistory] = useState<Track[]>(persisted.history);
  const [selectedTrack, setSelectedTrack] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ── Batch Mode State ───────────────────────────────────────────────
  const [batchMode, setBatchMode] = useState(false);
  const [batchPrompts, setBatchPrompts] = useState<string>('');
  const [batchStartTime, setBatchStartTime] = useState<number | null>(null);
  const [batchState, setBatchState] = useState<{
    batchId: string | null;
    path: string | null;
    total: number;
    completed: number;
    failed: number;
    currentPrompt: string;
    running: boolean;
    error: string | null;
  } | null>(null);
  const batchWsRef = useRef<WebSocket | null>(null);

  // ── Duration / Temperature for batch ────────────────────────────────
  const [batchDuration, setBatchDuration] = useState(10);
  const [batchTemperature, setBatchTemperature] = useState(0.8);

  // ── Batch ETA helper ───────────────────────────────────────────────
  const getBatchETA = useCallback(() => {
    if (!batchState || !batchStartTime || batchState.completed === 0) return '';
    const elapsed = (Date.now() - batchStartTime) / 1000;
    const avgPerItem = elapsed / batchState.completed;
    const remaining = (batchState.total - batchState.completed - batchState.failed) * avgPerItem;
    if (remaining > 60) return `${Math.ceil(remaining / 60)}m ${Math.ceil(remaining % 60)}s`;
    return `${Math.ceil(remaining)}s`;
  }, [batchState, batchStartTime]);

  // Use the shared WS hook for live progress
  const {
    status: wsStatus,
    progress: wsProgress,
    message: wsMessage,
    resultUrl: wsResultUrl,
    elapsedTime: wsElapsedTime,
    error: wsError,
    connected: wsConnected,
  } = useWebSocketProgress(workflow.taskId);

  const currentPathDef = PATHS.find((p) => p.id === selectedPath)!;

  // Persist state on changes
  useEffect(() => {
    if (!workflow.taskId && !workflow.running && !workflow.completed) return;
    savePersisted({
      version: STORAGE_VERSION,
      activeWorkflow: { ...workflow },
      history,
    });
  }, [workflow, history]);

  // ── File Upload Handler ──────────────────────────────────────────────
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      setUploadedFile(null);
      setUploadError(null);
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !['wav', 'mp3', 'mp4', 'flac', 'ogg', 'm4a', 'aac'].includes(ext)) {
      setUploadError('Unsupported format. Use WAV, MP3, FLAC, OGG, M4A, or AAC.');
      setUploadedFile(null);
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setUploadError('File too large. Maximum 50 MB.');
      setUploadedFile(null);
      return;
    }

    setUploadError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = reader.result as string;
      const pure = b64.includes(',') ? b64.split(',')[1] : b64;
      setUploadedFile({ name: file.name, base64: pure, size: file.size });
    };
    reader.onerror = () => setUploadError('Failed to read file.');
    reader.readAsDataURL(file);
  }, []);

  // ── Start Workflow ───────────────────────────────────────────────────
  const startWorkflow = useCallback(async () => {
    setLoading(true);
    setWorkflow((prev) => ({ ...prev, error: null }));

    try {
      const endpoint = `/api/v1/workflow/${selectedPath}`;
      const body: Record<string, unknown> = { task_id: `studio-${Date.now()}` };

      if (selectedPath === 'a') {
        body.prompt = prompt;
        body.duration = 10;
      } else if (selectedPath === 'b') {
        body.prompt = prompt;
        body.tts_text = ttsText || 'Hello world';
        body.duration = 10;
        if (uploadedFile) {
          body.reference_audio = uploadedFile.base64;
        }
      } else if (selectedPath === 'c') {
        if (!uploadedFile) {
          throw new Error('Please upload an audio file for Path C (Remix).');
        }
        body.audio_base64 = uploadedFile.base64;
        body.stem_count = '4';
      }

      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${err}`);
      }

      const data: ApiResult = await resp.json();
      const path = (data.path || selectedPath) as 'a' | 'b' | 'c';

      setWorkflow({
        path,
        taskId: data.task_id,
        tracks: [],
        running: true,
        completed: false,
        error: null,
      });
    } catch (err) {
      console.error('Workflow failed:', err);
      setWorkflow((prev) => ({
        ...prev,
        running: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }));
    } finally {
      setLoading(false);
    }
  }, [selectedPath, prompt, ttsText, uploadedFile]);

  // ── Batch Start Handler ────────────────────────────────────────────
  const startBatch = useCallback(async () => {
    const lines = batchPrompts.trim().split('\n').filter(l => l.trim());
    if (lines.length === 0) {
      alert('Please enter at least one prompt (one per line).');
      return;
    }

    setLoading(true);
    setBatchState({
      batchId: null,
      path: null,
      total: lines.length,
      completed: 0,
      failed: 0,
      currentPrompt: '',
      running: false,
      error: null,
    });
    setBatchStartTime(Date.now());

    try {
      const endpoint = batchMode
        ? `/api/v1/batch/${selectedPath}`
        : `/api/v1/workflow/${selectedPath}`;

      if (!batchMode) {
        // Single mode — use existing startWorkflow logic
        await startWorkflow();
        return;
      }

      // Batch mode
      let body: Record<string, unknown>;
      if (selectedPath === 'a') {
        body = {
          prompts: lines.map((p) => ({
            prompt: p.trim(),
            duration: batchDuration,
            temperature: batchTemperature,
          })),
        };
      } else if (selectedPath === 'b') {
        const texts = ttsText.trim() ? ttsText.split('\n') : lines.map((_, i) => `Track ${i + 1}`);
        body = {
          items: lines.map((p, i) => ({
            prompt: p.trim(),
            tts_text: texts[i % texts.length]?.trim() || `Track ${i + 1}`,
            duration: batchDuration,
          })),
        };
      } else {
        throw new Error('Batch mode not supported for Path C (Remix).');
      }

      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${err}`);
      }

      const data: BatchResult = await resp.json();

      setBatchState((prev) => ({
        ...prev!,
        batchId: data.batch_id,
        path: data.path || selectedPath,
        running: true,
      }));

      // Connect to WS for batch progress
      if (batchWsRef.current) {
        batchWsRef.current.onclose = null;
        batchWsRef.current.close();
      }
      const ws = new WebSocket(`ws://${window.location.host}/ws/progress/${data.batch_id}`);
      batchWsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as Record<string, unknown>;
          const metadata = (msg.metadata ?? {}) as Record<string, unknown>;
          const current = metadata.current_item as Record<string, unknown> | undefined;
          const batchCompleted = Number((metadata as Record<string, unknown>).batch_completed ?? 0);
          const batchFailed = Number((metadata as Record<string, unknown>).batch_failed ?? 0);
          const batchPath = (metadata as Record<string, unknown>).path as string | undefined;

          setBatchState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              path: batchPath || prev.path,
              completed: batchCompleted,
              failed: batchFailed,
              currentPrompt: current?.prompt ? String(current.prompt) : prev.currentPrompt,
              running: msg.status !== 'completed' && msg.status !== 'failed',
            };
          });
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setBatchState((prev) => prev ? { ...prev, running: false } : null);
      };

      ws.onerror = () => {
        setBatchState((prev) => prev ? { ...prev, error: 'WebSocket connection error' } : null);
      };
    } catch (err) {
      console.error('Batch failed:', err);
      setBatchState((prev) => prev ? { ...prev, error: err instanceof Error ? err.message : 'Unknown error', running: false } : null);
    } finally {
      setLoading(false);
    }
  }, [batchMode, batchPrompts, selectedPath, batchDuration, batchTemperature, ttsText, startWorkflow]);

  // ── Cleanup batch WS on unmount ────────────────────────────────────
  useEffect(() => {
    return () => {
      if (batchWsRef.current) {
        batchWsRef.current.onclose = null;
        batchWsRef.current.close();
      }
    };
  }, []);

  // ── Sync WS updates into workflow state ──────────────────────────────
  useEffect(() => {
    if (!workflow.taskId) return;

    if (wsStatus) {
      const trackStatusMap: Record<string, Track['status']> = {
        pending: 'queued',
        loading: 'queued',
        running: 'running',
        completed: 'completed',
        failed: 'failed',
        cancelled: 'failed',
      };

      const mappedStatus = trackStatusMap[wsStatus] || 'running';
      const isTerminal = wsStatus === 'completed' || wsStatus === 'failed';

      setWorkflow((prev) => {
        if (prev.tracks.length === 0) {
          const name = prev.path === 'a'
            ? `MusicGen: ${(prompt || '').slice(0, 30)}`
            : prev.path === 'b'
            ? `Hybrid: ${(prompt || '').slice(0, 20)}`
            : 'Remix Processing';
          return {
            ...prev,
            tracks: [{
              id: `track-${prev.taskId}`,
              name,
              type: prev.path === 'b' ? 'tts' : 'music',
              status: mappedStatus,
              url: wsResultUrl || null,
              progress: wsProgress,
              color: TRACK_COLORS[0],
            }],
            running: !isTerminal,
            completed: wsStatus === 'completed',
            error: wsStatus === 'failed' ? (wsError || 'Generation failed') : prev.error,
          };
        }

        const updatedTracks = prev.tracks.map((t) => ({
          ...t,
          status: mappedStatus,
          progress: wsProgress,
          url: wsResultUrl || t.url,
        }));

        return {
          ...prev,
          tracks: updatedTracks,
          running: !isTerminal,
          completed: wsStatus === 'completed',
          error: wsStatus === 'failed' ? (wsError || 'Generation failed') : prev.error,
        };
      });
    }
  }, [wsStatus, wsProgress, wsMessage, wsResultUrl, wsError, workflow.taskId, prompt]);

  // ── Persist trim state changes to history ──────────────────────────
  const handleTrimChange = useCallback((trackId: string, start: number, end: number) => {
    setHistory((prev) =>
      prev.map((t) =>
        t.id === trackId ? { ...t, trimStart: start, trimEnd: end } : t
      )
    );
  }, []);
  useEffect(() => {
    if (workflow.completed && workflow.tracks.length > 0) {
      // Move completed tracks to history
      const completedTracks = workflow.tracks
        .filter((t) => t.status === 'completed' && t.url)
        .map((t) => ({ ...t, createdAt: Date.now() }));

      if (completedTracks.length > 0) {
        setHistory((prev) => [...completedTracks, ...prev].slice(0, 50)); // Keep last 50
      }

      // Clear active workflow after a delay so user sees completion
      setTimeout(() => {
        setWorkflow((prev) => ({
          ...prev,
          running: false,
          tracks: [],
          taskId: null,
        }));
      }, 2000);
    }
  }, [workflow.completed]);

  // ── Track Actions ────────────────────────────────────────────────────
  const handleRenameTrack = useCallback((trackId: string, newName: string) => {
    setWorkflow((prev) => ({
      ...prev,
      tracks: prev.tracks.map((t) =>
        t.id === trackId ? { ...t, name: newName } : t
      ),
    }));
    setHistory((prev) =>
      prev.map((t) => t.id === trackId ? { ...t, name: newName } : t)
    );
  }, []);

  const handleDeleteTrack = useCallback((trackId: string) => {
    setWorkflow((prev) => ({
      ...prev,
      tracks: prev.tracks.filter((t) => t.id !== trackId),
    }));
    setHistory((prev) => prev.filter((t) => t.id !== trackId));
    if (selectedTrack === trackId) setSelectedTrack(null);
  }, [selectedTrack]);

  const handleClearHistory = useCallback(() => {
    if (confirm('Clear all saved tracks?')) {
      setHistory([]);
      savePersisted({ ...loadPersisted(), history: [] });
    }
  }, []);

  // ── Reset ────────────────────────────────────────────────────────────
  const resetStudio = useCallback(() => {
    setWorkflow({ path: null, taskId: null, tracks: [], running: false, completed: false, error: null });
    setSelectedTrack(null);
    setBatchState(null);
    setBatchStartTime(null);
    if (batchWsRef.current) {
      batchWsRef.current.onclose = null;
      batchWsRef.current.close();
    }
  }, []);

  // ── Format file size ─────────────────────────────────────────────────
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // ── Render ───────────────────────────────────────────────────────────
  const selectedTrackData = workflow.tracks.find((t) => t.id === selectedTrack);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎛️</span>
            <div>
              <h1 className="text-lg font-bold tracking-tight">AI Music Workbench</h1>
              <p className="text-xs text-gray-500">Generate · Hybrid · Remix</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>Backend: <span className={workflow.running ? 'text-amber-400' : 'text-emerald-400'}>
              {workflow.running ? 'Generating...' : 'Idle'}
            </span></span>
            {workflow.taskId && (
              <span className="text-gray-600 font-mono">
                {wsConnected ? '●' : '○'} {wsStatus ? wsStatus.toUpperCase() : '—'}
                {wsConnected && <span className="ml-1 text-blue-400 animate-pulse">live</span>}
              </span>
            )}
            {history.length > 0 && (
              <span className="text-gray-600">
                📁 {history.length} saved
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* ── Path Selector ─────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-3">
          {PATHS.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                setSelectedPath(p.id);
                setPrompt(p.prompt);
                setTtsText(p.ttsDefault || '');
                setUploadedFile(null);
                setUploadError(null);
                resetStudio();
              }}
              disabled={workflow.running}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                selectedPath === p.id
                  ? 'border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/20'
                  : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'
              } ${workflow.running ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xl">{p.icon}</span>
                <span className="font-semibold text-sm">{p.label.split('—')[0].trim()}</span>
              </div>
              <p className="text-xs text-gray-400">{p.desc}</p>
            </button>
          ))}
        </div>

        {/* ── Input Area ────────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-4">
          {/* Batch Toggle */}
          {selectedPath !== 'c' && (
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-300">Mode</label>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${!batchMode ? 'text-blue-400 font-medium' : 'text-gray-600'}`}>Single</span>
                  <button
                    onClick={() => { setBatchMode(false); setBatchPrompts(''); }}
                    className={`w-10 h-5 rounded-full transition-colors relative ${
                      !batchMode ? 'bg-blue-600' : 'bg-gray-700'
                    }`}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      !batchMode ? 'left-5' : 'left-0.5'
                    }`} />
                  </button>
                  <span className={`text-xs ${batchMode ? 'text-blue-400 font-medium' : 'text-gray-600'}`}>Batch</span>
                </div>
                {batchMode && batchPrompts.trim() && (
                  <span className="text-xs px-2 py-0.5 bg-blue-900/50 text-blue-400 rounded-full">
                    {batchPrompts.trim().split('\n').filter(Boolean).length} prompts
                  </span>
                )}
              </div>
            </div>
          )}

          {selectedPath === 'c' ? (
            <div>
              <label className="text-sm font-medium text-gray-300">{currentPathDef.inputLabel}</label>
              <div className="mt-2 flex items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".wav,.mp3,.mp4,.flac,.ogg,.m4a,.aac"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 text-sm border border-gray-600 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  {uploadedFile ? 'Change File' : 'Choose Audio File'}
                </button>
                {uploadedFile && (
                  <span className="text-xs text-emerald-400">
                    ✓ {uploadedFile.name} ({formatSize(uploadedFile.size)})
                  </span>
                )}
              </div>
              {uploadError && <p className="mt-1 text-xs text-red-400">{uploadError}</p>}
            </div>
          ) : batchMode ? (
            /* ── Batch Mode Input ───────────────────────────────────── */
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-gray-300">
                  Prompts (one per line)
                </label>
                <textarea
                  value={batchPrompts}
                  onChange={(e) => setBatchPrompts(e.target.value)}
                  rows={6}
                  className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600 resize-y font-mono"
                  placeholder={"upbeat electronic dance music\nchill lofi hip hop beat\nambient piano melody\ndark synthwave cyberpunk"}
                />
                {batchPrompts.trim() && (
                  <p className="text-xs text-gray-500 mt-1">
                    {batchPrompts.trim().split('\n').filter(Boolean).length} prompt(s) ready
                  </p>
                )}
              </div>
              {selectedPath === 'b' && (
                <div>
                  <label className="text-sm font-medium text-gray-300">TTS Texts (one per line, optional)</label>
                  <textarea
                    value={ttsText}
                    onChange={(e) => setTtsText(e.target.value)}
                    rows={3}
                    className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600 resize-y font-mono"
                    placeholder={"Line 1 lyrics\nLine 2 lyrics\nLine 3 lyrics"}
                  />
                  <p className="text-xs text-gray-600 mt-1">
                    If fewer lines than prompts, last line repeats cyclically
                  </p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400">Duration (s)</label>
                  <input
                    type="number"
                    value={batchDuration}
                    onChange={(e) => setBatchDuration(Number(e.target.value))}
                    min={1}
                    max={60}
                    className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400">Temperature</label>
                  <input
                    type="number"
                    value={batchTemperature}
                    onChange={(e) => setBatchTemperature(Number(e.target.value))}
                    min={0}
                    max={2}
                    step={0.1}
                    className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>
          ) : (
            /* ── Single Mode Input ──────────────────────────────────── */
            <>
              <div>
                <label className="text-sm font-medium text-gray-300">{currentPathDef.inputLabel || currentPathDef.musicLabel}</label>
                <input
                  type="text"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                  placeholder="Describe the music you want..."
                />
              </div>
              {selectedPath === 'b' && (
                <div>
                  <label className="text-sm font-medium text-gray-300">{currentPathDef.ttsLabel}</label>
                  <input
                    type="text"
                    value={ttsText}
                    onChange={(e) => setTtsText(e.target.value)}
                    className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                    placeholder="Text to synthesize (optional, defaults to Hello World)"
                  />
                  {uploadedFile && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                      <span>📎 {uploadedFile.name} ({formatSize(uploadedFile.size)})</span>
                      <button
                        type="button"
                        onClick={() => { setUploadedFile(null); setUploadError(null); }}
                        className="text-red-400 hover:text-red-300"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Generate / Batch Start Button */}
          <div className="flex gap-3">
            <button
              onClick={batchMode ? startBatch : startWorkflow}
              disabled={loading || workflow.running || (selectedPath === 'c' && !uploadedFile) || (!batchMode && selectedPath === 'b' && !prompt)}
              className="flex-1 px-6 py-3 bg-gradient-to-r from-blue-600 to-violet-600 text-white font-semibold rounded-xl
                         hover:from-blue-500 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-all shadow-lg shadow-blue-500/20"
            >
              {loading
                ? batchMode ? '⏳ Starting Batch...' : '⏳ Starting...'
                : batchMode ? `📦 Start Batch (${batchPrompts.trim().split('\n').filter(Boolean).length})`
                : `✨ ${currentPathDef.icon} Generate`}
            </button>
            {(workflow.completed || workflow.error) && (
              <button
                onClick={resetStudio}
                className="px-6 py-3 text-gray-400 border border-gray-700 rounded-xl hover:bg-gray-800 transition-colors"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        {/* ── Batch Progress Dashboard ─────────────────────────────────── */}
        {batchState && (batchState.running || batchState.error) && (
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
                    {batchState.path === 'a' ? 'Path A' : batchState.path === 'b' ? 'Path B' : 'Batch'} — {batchState.total} tasks
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {batchState.running && (
                  <span className="text-xs text-purple-400 animate-pulse font-mono">● LIVE</span>
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
                <p className="text-lg font-bold text-blue-400">
                  {batchState.running ? getBatchETA() : '—'}
                </p>
                <p className="text-xs text-gray-500">ETA</p>
              </div>
            </div>

            {/* Progress bar */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-purple-400 truncate max-w-[60%]">
                  {batchState.currentPrompt ? `▶ ${batchState.currentPrompt}` : batchState.running ? 'Initializing...' : ''}
                </span>
                <span className="text-xs font-mono text-purple-300">
                  {batchState.completed}/{batchState.total} ({Math.round((batchState.completed / Math.max(batchState.total, 1)) * 100)}%)
                </span>
              </div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-purple-500 via-fuchsia-500 to-pink-500 rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${batchState.total > 0 ? ((batchState.completed + batchState.failed) / batchState.total) * 100 : 0}%` }}
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
        )}

        {/* ── Live Status Banner ────────────────────────────────────── */}
        {(workflow.running || wsMessage) && (
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
                  <span className="text-sm font-bold text-blue-400">{wsProgress}%</span>
                </div>
                <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-violet-500 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${wsProgress}%` }}
                  />
                </div>
                {wsMessage && (
                  <p className="text-xs text-gray-500 mt-1">{wsMessage}</p>
                )}
                {wsElapsedTime !== null && wsElapsedTime > 0 && (
                  <p className="text-xs text-gray-600 mt-1">Elapsed: {formatDuration(wsElapsedTime)}</p>
                )}
              </div>
              {wsConnected && (
                <span className="text-xs text-blue-400 animate-pulse">● LIVE</span>
              )}
            </div>
          </div>
        )}

        {/* ── Error Display ─────────────────────────────────────────── */}
        {workflow.error && (
          <div className="rounded-xl border border-red-800 bg-red-950/50 p-4">
            <p className="text-sm text-red-300 font-medium">Error</p>
            <p className="text-xs text-red-400 mt-1 font-mono">{workflow.error}</p>
          </div>
        )}

        {/* ── Active Tracks ─────────────────────────────────────────── */}
        {workflow.tracks.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
              Active Sessions
            </h2>
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(workflow.tracks.length, 3)}, minmax(0, 1fr))` }}>
              {workflow.tracks.map((track, idx) => (
                <button
                  key={track.id}
                  onClick={() => setSelectedTrack(track.id === selectedTrack ? null : track.id)}
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
                      {track.type === 'music' ? '🎵' : track.type === 'tts' ? '🎤' : '🎛️'}
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

                  {track.status === 'completed' && track.url && track.url !== '' && (
                    <AudioPlayer
                      track={track}
                      onRename={handleRenameTrack}
                      onDelete={handleDeleteTrack}
                      onTrimChange={handleTrimChange}
                    />
                  )}

                  {track.status === 'completed' && !track.url && (
                    <p className="text-xs text-gray-500 mt-2">No audio URL</p>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Saved History ─────────────────────────────────────────── */}
        {history.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                Saved Tracks ({history.length})
              </h2>
              <button
                onClick={handleClearHistory}
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
                      {track.type === 'music' ? '🎵' : track.type === 'tts' ? '🎤' : '🎛️'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium truncate">{track.name}</p>
                      <p className="text-xs text-gray-600">
                        {track.createdAt ? formatDate(track.createdAt) : ''}
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeleteTrack(track.id)}
                      className="text-xs text-gray-600 hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </div>

                  {track.status === 'completed' && track.url && track.url !== '' && (
                    <AudioPlayer
                      track={track}
                      onRename={handleRenameTrack}
                      onDelete={handleDeleteTrack}
                      onTrimChange={handleTrimChange}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Selected Track Detail ─────────────────────────────────── */}
        {selectedTrackData && (
          <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300">
                Track Detail: {selectedTrackData.name}
              </h3>
              <button
                onClick={() => setSelectedTrack(null)}
                className="text-xs text-gray-500 hover:text-gray-300"
              >
                ✕ Close
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-gray-500">Type:</span>{' '}
                <span className="capitalize text-gray-300">{selectedTrackData.type}</span>
              </div>
              <div>
                <span className="text-gray-500">Status:</span>{' '}
                <span className={`capitalize ${
                  selectedTrackData.status === 'completed' ? 'text-emerald-400' :
                  selectedTrackData.status === 'failed' ? 'text-red-400' :
                  selectedTrackData.status === 'running' ? 'text-amber-400' :
                  'text-gray-400'
                }`}>{selectedTrackData.status}</span>
              </div>
              <div>
                <span className="text-gray-500">Progress:</span>{' '}
                <span className="text-gray-300">{selectedTrackData.progress}%</span>
              </div>
              <div>
                <span className="text-gray-500">URL:</span>{' '}
                <span className="text-gray-300 font-mono truncate block max-w-[200px]">
                  {selectedTrackData.url || '—'}
                </span>
              </div>
            </div>
            {selectedTrackData.status === 'completed' && selectedTrackData.url && (
              <div className="mt-3">
                <audio controls src={selectedTrackData.url} className="w-full" preload="metadata" />
              </div>
            )}
          </div>
        )}

        {/* ── Idle State ────────────────────────────────────────────── */}
        {!workflow.running && !workflow.completed && !workflow.error && workflow.tracks.length === 0 && history.length === 0 && (
          <div className="text-center py-12 text-gray-600">
            <p className="text-4xl mb-3">🎧</p>
            <p className="text-sm">Select a workflow path and click Generate to start</p>
            <div className="mt-4 grid grid-cols-3 gap-4 text-xs max-w-lg mx-auto">
              <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
                <p className="text-gray-400 font-medium">Path A</p>
                <p className="text-gray-600 mt-1">Type a prompt, get music</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
                <p className="text-gray-400 font-medium">Path B</p>
                <p className="text-gray-600 mt-1">Music + vocals combined</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
                <p className="text-gray-400 font-medium">Path C</p>
                <p className="text-gray-600 mt-1">Upload audio, get stems</p>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className="border-t border-gray-800 mt-12 py-4 text-center text-xs text-gray-600">
        AI Music Workbench v3.1 · Built with React + Vite + FastAPI
      </footer>
    </div>
  );
}
