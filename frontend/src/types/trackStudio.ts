/**
 * TrackStudio types and constants.
 *
 * Centralized so sub-components can import without circular deps.
 */

// ── Domain Types ────────────────────────────────────────────────────────────

export interface Track {
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

export interface PersistedSession {
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

export interface ApiResult {
  task_id: string;
  status: string;
  websocket: string;
  path?: string;
}

export interface BatchResult {
  batch_id: string;
  path: string;
  total: number;
  status: string;
  websocket: string;
}

// ── Workflow Path Definition ────────────────────────────────────────────────

export interface PathDefinition {
  id: 'a' | 'b' | 'c';
  label: string;
  desc: string;
  icon: string;
  prompt?: string;
  inputLabel?: string;
  musicLabel?: string;
  ttsLabel?: string;
  ttsDefault?: string;
}

// ── Batch Progress State ───────────────────────────────────────────────────

export interface BatchState {
  batchId: string | null;
  path: string | null;
  total: number;
  completed: number;
  failed: number;
  currentPrompt: string;
  running: boolean;
  error: string | null;
}

// ── Copyright / Provenance ──────────────────────────────────────────────────

export type OriginalityLevel = 'original' | 'derivative';

export interface ProjectProvenance {
  /** Unique project identifier (UUID) */
  projectId: string;
  /** Timestamp of project creation */
  createdAt: number;
  /** Originality classification */
  originality: OriginalityLevel;
  /** Source track ID if derivative (null for original works) */
  sourceTrackId: string | null;
  /** Chain of operations applied to this project */
  operations: ProvenanceOperation[];
  /** Cryptographic fingerprint of final output */
  outputHash?: string;
  /** Exportable JSON-LD proof document */
  proofDocument?: Record<string, unknown>;
}

export type ProvenanceOperationType =
  | 'generate'
  | 'remix_pitch_shift'
  | 'remix_tempo_change'
  | 'remix_timbre_transform'
  | 'trim'
  | 'download'
  | 'mv_generate';

export interface ProvenanceOperation {
  type: ProvenanceOperationType;
  timestamp: number;
  params: Record<string, unknown>;
  resultTrackId?: string;
}

// ── Remix Tool Parameters ───────────────────────────────────────────────────

export interface RemixParameters {
  /** Pitch shift in semitones (-12 to +12) */
  pitchShift?: number;
  /** Tempo multiplier (0.5x to 2.0x) */
  tempoMultiplier?: number;
  /** Timbre transformation preset */
  timbreTransform?: 'warm' | 'bright' | 'dark' | 'thin' | 'heavy';
  /** Random seed for reproducibility */
  seed?: number;
}

// ── MV Generator ────────────────────────────────────────────────────────────

export interface BeatDetectionResult {
  bpm: number;
  beatTimestamps: number[];
  energyProfile: { time: number; energy: number }[];
}

export interface MVConfig {
  resolution: '720p' | '1080p' | '4K';
  aspectRatio: '16:9' | '9:16' | '1:1';
  transitionStyle: 'cut' | 'fade' | 'zoom' | 'pan';
  backgroundColor: string;
  waveformVisualization: boolean;
}

export interface VideoRenderJob {
  jobId: string;
  sourceTrackId: string;
  beatResult: BeatDetectionResult;
  config: MVConfig;
  status: 'queued' | 'analyzing' | 'rendering' | 'completed' | 'failed';
  progress: number;
  outputPath?: string;
  error?: string;
}

// ── Constants ───────────────────────────────────────────────────────────────

export const STORAGE_KEY = 'music-workbench-session';
export const STORAGE_VERSION = 1;

export const TRACK_COLORS = [
  'bg-violet-500',
  'bg-sky-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-indigo-500',
];

export const PATHS: PathDefinition[] = [
  {
    id: 'a',
    label: 'Path A — Suno Style',
    desc: 'Prompt → MusicGen → Full Audio',
    icon: '🎵',
    prompt: 'upbeat electronic dance music with synth lead',
    inputLabel: 'Music Prompt',
  },
  {
    id: 'b',
    label: 'Path B — Hybrid',
    desc: 'Music Gen + TTS Vocals → Combined Track',
    icon: '🎤',
    prompt: 'chill lofi hip hop beat',
    musicLabel: 'Music Prompt',
    ttsLabel: 'TTS Text',
    ttsDefault: '今天天气真好，阳光明媚',
  },
  {
    id: 'c',
    label: 'Path C — Remix',
    desc: 'Upload Audio → Demucs Stem Separation',
    icon: '🎛️',
    inputLabel: 'Audio File',
  },
];

// ── Mix Console (DAW-style multi-track mixer) ────────────────────────────────

export interface MixTrackParams {
  trackId: string;
  volume: number;
  pan: number;
  eqLow: number;
  eqMid: number;
  eqHigh: number;
  solo: boolean;
  mute: boolean;
  reverbSend: number;
}

export interface MixSession {
  tracks: MixTrackParams[];
  masterVolume: number;
  outputFormat: 'wav' | 'mp3';
}

export const mixDefaults: MixTrackParams = {
  trackId: '',
  volume: 0,
  pan: 0,
  eqLow: 0,
  eqMid: 0,
  eqHigh: 0,
  solo: false,
  mute: false,
  reverbSend: 0,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}

export function formatDate(timestamp: number): string {
  const d = new Date(timestamp);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function defaultPersisted(): PersistedSession {
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
