/**
 * TrackStudio types and constants.
 *
 * Centralized so sub-components can import without circular deps.
 */

// ── Domain Types ────────────────────────────────────────────────────────────

export interface AudioClip {
  id: string;
  name: string;
  startTime: number; // seconds
  duration: number; // seconds
  url?: string;
  color?: string;
  fadeIn?: number; // seconds
  fadeOut?: number; // seconds
  gain?: number; // dB
  muted?: boolean;
}

export interface Track {
  id: string;
  name: string;
  type: 'music' | 'tts' | 'stem' | 'stem_zip' | 'audio' | 'midi';
  status: 'queued' | 'running' | 'completed' | 'failed' | 'ready';
  url: string | null;
  progress: number;
  color: string;
  createdAt?: number;
  trimStart?: number;
  trimEnd?: number;
  // Multi-track properties
  clips?: AudioClip[];
  muted?: boolean;
  solo?: boolean;
  armed?: boolean;
  volume?: number; // 0-1
  pan?: number; // -1 to 1
}

export interface PersistedSession {
  version: number;
  activeWorkflow: {
    path: 'a' | 'b' | 'c' | 'd' | null;
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
  id: 'a' | 'b' | 'c' | 'd';
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

// ── MIDI / Piano Roll (Path D) ────────────────────────────────────────────────

export type MidiNoteName = 'C' | 'C#' | 'D' | 'D#' | 'E' | 'F' | 'F#' | 'G' | 'G#' | 'A' | 'A#' | 'B';

export interface MidiNote {
  id: string;           // Unique identifier for the note
  pitch: number;        // MIDI note number (0-127)
  velocity: number;     // 0-127
  startTick: number;    // Start position in ticks
  durationTicks: number; // Duration in ticks
  channel: number;      // MIDI channel (0-15)
}

export interface MidiTrack {
  id: string;
  name: string;
  instrument: number;   // General MIDI program number (0-127)
  channel: number;      // MIDI channel (0-15)
  notes: MidiNote[];
  color: string;
  solo: boolean;
  mute: boolean;
  volume: number;       // 0-1
  pan: number;          // -1 to 1
}

export interface MidiProject {
  id: string;
  name: string;
  tempo: number;        // BPM
  timeSignature: { numerator: number; denominator: number };
  ticksPerQuarter: number; // PPQ (usually 480)
  tracks: MidiTrack[];
  loopStartTick?: number;
  loopEndTick?: number;
  createdAt: number;
  updatedAt: number;
}

export type InstrumentCategory = 'piano' | 'keys' | 'organ' | 'guitar' | 'bass' | 'strings' | 'ensemble' | 'brass' | 'reed' | 'pipe' | 'synth_lead' | 'synth_pad' | 'synth_effects' | 'ethnic' | 'percussive' | 'sound_effects' | 'drums';

export interface InstrumentInfo {
  program: number;      // General MIDI program (0-127)
  name: string;
  category: InstrumentCategory;
  isDrumKit: boolean;
}

export const GM_INSTRUMENTS: InstrumentInfo[] = [
  // Piano
  { program: 0, name: 'Acoustic Grand Piano', category: 'piano', isDrumKit: false },
  { program: 1, name: 'Bright Acoustic Piano', category: 'piano', isDrumKit: false },
  { program: 2, name: 'Electric Grand Piano', category: 'piano', isDrumKit: false },
  { program: 3, name: 'Honky-tonk Piano', category: 'piano', isDrumKit: false },
  { program: 4, name: 'Electric Piano 1', category: 'keys', isDrumKit: false },
  { program: 5, name: 'Electric Piano 2', category: 'keys', isDrumKit: false },
  { program: 6, name: 'Harpsichord', category: 'keys', isDrumKit: false },
  { program: 7, name: 'Clavi', category: 'keys', isDrumKit: false },
  // Chromatic Percussion
  { program: 8, name: 'Celesta', category: 'percussive', isDrumKit: false },
  { program: 9, name: 'Glockenspiel', category: 'percussive', isDrumKit: false },
  { program: 10, name: 'Music Box', category: 'percussive', isDrumKit: false },
  { program: 11, name: 'Vibraphone', category: 'percussive', isDrumKit: false },
  { program: 12, name: 'Marimba', category: 'percussive', isDrumKit: false },
  { program: 13, name: 'Xylophone', category: 'percussive', isDrumKit: false },
  { program: 14, name: 'Tubular Bells', category: 'percussive', isDrumKit: false },
  { program: 15, name: 'Dulcimer', category: 'percussive', isDrumKit: false },
  // Organ
  { program: 16, name: 'Drawbar Organ', category: 'organ', isDrumKit: false },
  { program: 17, name: 'Percussive Organ', category: 'organ', isDrumKit: false },
  { program: 18, name: 'Rock Organ', category: 'organ', isDrumKit: false },
  { program: 19, name: 'Church Organ', category: 'organ', isDrumKit: false },
  { program: 20, name: 'Reed Organ', category: 'organ', isDrumKit: false },
  { program: 21, name: 'Accordion', category: 'reed', isDrumKit: false },
  { program: 22, name: 'Harmonica', category: 'reed', isDrumKit: false },
  { program: 23, name: 'Tango Accordion', category: 'reed', isDrumKit: false },
  // Guitar
  { program: 24, name: 'Nylon Guitar', category: 'guitar', isDrumKit: false },
  { program: 25, name: 'Steel Guitar', category: 'guitar', isDrumKit: false },
  { program: 26, name: 'Jazz Guitar', category: 'guitar', isDrumKit: false },
  { program: 27, name: 'Clean Guitar', category: 'guitar', isDrumKit: false },
  { program: 28, name: 'Muted Guitar', category: 'guitar', isDrumKit: false },
  { program: 29, name: 'Overdriven Guitar', category: 'guitar', isDrumKit: false },
  { program: 30, name: 'Distortion Guitar', category: 'guitar', isDrumKit: false },
  { program: 31, name: 'Guitar Harmonics', category: 'guitar', isDrumKit: false },
  // Bass
  { program: 32, name: 'Acoustic Bass', category: 'bass', isDrumKit: false },
  { program: 33, name: 'Finger Bass', category: 'bass', isDrumKit: false },
  { program: 34, name: 'Pick Bass', category: 'bass', isDrumKit: false },
  { program: 35, name: 'Fretless Bass', category: 'bass', isDrumKit: false },
  { program: 36, name: 'Slap Bass 1', category: 'bass', isDrumKit: false },
  { program: 37, name: 'Slap Bass 2', category: 'bass', isDrumKit: false },
  { program: 38, name: 'Synth Bass 1', category: 'synth_lead', isDrumKit: false },
  { program: 39, name: 'Synth Bass 2', category: 'synth_lead', isDrumKit: false },
  // Strings
  { program: 40, name: 'Violin', category: 'strings', isDrumKit: false },
  { program: 41, name: 'Viola', category: 'strings', isDrumKit: false },
  { program: 42, name: 'Cello', category: 'strings', isDrumKit: false },
  { program: 43, name: 'Contrabass', category: 'strings', isDrumKit: false },
  { program: 44, name: 'Tremolo Strings', category: 'strings', isDrumKit: false },
  { program: 45, name: 'Pizzicato Strings', category: 'strings', isDrumKit: false },
  { program: 46, name: 'Orchestral Harp', category: 'strings', isDrumKit: false },
  { program: 47, name: 'Timpani', category: 'percussive', isDrumKit: false },
  // Ensemble
  { program: 48, name: 'String Ensemble 1', category: 'ensemble', isDrumKit: false },
  { program: 49, name: 'String Ensemble 2', category: 'ensemble', isDrumKit: false },
  { program: 50, name: 'Synth Strings 1', category: 'ensemble', isDrumKit: false },
  { program: 51, name: 'Synth Strings 2', category: 'ensemble', isDrumKit: false },
  { program: 52, name: 'Choir Aahs', category: 'ensemble', isDrumKit: false },
  { program: 53, name: 'Voice Oohs', category: 'ensemble', isDrumKit: false },
  { program: 54, name: 'Synth Voice', category: 'synth_pad', isDrumKit: false },
  { program: 55, name: 'Orchestra Hit', category: 'ensemble', isDrumKit: false },
  // Brass
  { program: 56, name: 'Trumpet', category: 'brass', isDrumKit: false },
  { program: 57, name: 'Trombone', category: 'brass', isDrumKit: false },
  { program: 58, name: 'Tuba', category: 'brass', isDrumKit: false },
  { program: 59, name: 'Muted Trumpet', category: 'brass', isDrumKit: false },
  { program: 60, name: 'French Horn', category: 'brass', isDrumKit: false },
  { program: 61, name: 'Brass Section', category: 'brass', isDrumKit: false },
  { program: 62, name: 'Synth Brass 1', category: 'synth_pad', isDrumKit: false },
  { program: 63, name: 'Synth Brass 2', category: 'synth_pad', isDrumKit: false },
  // Reed
  { program: 64, name: 'Soprano Sax', category: 'reed', isDrumKit: false },
  { program: 65, name: 'Alto Sax', category: 'reed', isDrumKit: false },
  { program: 66, name: 'Tenor Sax', category: 'reed', isDrumKit: false },
  { program: 67, name: 'Baritone Sax', category: 'reed', isDrumKit: false },
  { program: 68, name: 'Oboe', category: 'reed', isDrumKit: false },
  { program: 69, name: 'English Horn', category: 'reed', isDrumKit: false },
  { program: 70, name: 'Bassoon', category: 'reed', isDrumKit: false },
  { program: 71, name: 'Clarinet', category: 'reed', isDrumKit: false },
  // Pipe
  { program: 72, name: 'Piccolo', category: 'pipe', isDrumKit: false },
  { program: 73, name: 'Flute', category: 'pipe', isDrumKit: false },
  { program: 74, name: 'Recorder', category: 'pipe', isDrumKit: false },
  { program: 75, name: 'Pan Flute', category: 'pipe', isDrumKit: false },
  { program: 76, name: 'Blown Bottle', category: 'pipe', isDrumKit: false },
  { program: 77, name: 'Shakuhachi', category: 'pipe', isDrumKit: false },
  { program: 78, name: 'Whistle', category: 'pipe', isDrumKit: false },
  { program: 79, name: 'Ocarina', category: 'pipe', isDrumKit: false },
  // Synth Lead
  { program: 80, name: 'Lead 1 (Square)', category: 'synth_lead', isDrumKit: false },
  { program: 81, name: 'Lead 2 (Sawtooth)', category: 'synth_lead', isDrumKit: false },
  { program: 82, name: 'Lead 3 (Calliope)', category: 'synth_lead', isDrumKit: false },
  { program: 83, name: 'Lead 4 (Chiff)', category: 'synth_lead', isDrumKit: false },
  { program: 84, name: 'Lead 5 (Charang)', category: 'synth_lead', isDrumKit: false },
  { program: 85, name: 'Lead 6 (Voice)', category: 'synth_lead', isDrumKit: false },
  { program: 86, name: 'Lead 7 (Fifths)', category: 'synth_lead', isDrumKit: false },
  { program: 87, name: 'Lead 8 (Bass + Lead)', category: 'synth_lead', isDrumKit: false },
  // Synth Pad
  { program: 88, name: 'Pad 1 (New Age)', category: 'synth_pad', isDrumKit: false },
  { program: 89, name: 'Pad 2 (Warm)', category: 'synth_pad', isDrumKit: false },
  { program: 90, name: 'Pad 3 (Polysynth)', category: 'synth_pad', isDrumKit: false },
  { program: 91, name: 'Pad 4 (Choir)', category: 'synth_pad', isDrumKit: false },
  { program: 92, name: 'Pad 5 (Bowed)', category: 'synth_pad', isDrumKit: false },
  { program: 93, name: 'Pad 6 (Metallic)', category: 'synth_pad', isDrumKit: false },
  { program: 94, name: 'Pad 7 (Halo)', category: 'synth_pad', isDrumKit: false },
  { program: 95, name: 'Pad 8 (Sweep)', category: 'synth_pad', isDrumKit: false },
  // Synth Effects
  { program: 96, name: 'FX 1 (Rain)', category: 'synth_effects', isDrumKit: false },
  { program: 97, name: 'FX 2 (Soundtrack)', category: 'synth_effects', isDrumKit: false },
  { program: 98, name: 'FX 3 (Crystal)', category: 'synth_effects', isDrumKit: false },
  { program: 99, name: 'FX 4 (Atmosphere)', category: 'synth_effects', isDrumKit: false },
  { program: 100, name: 'FX 5 (Brightness)', category: 'synth_effects', isDrumKit: false },
  { program: 101, name: 'FX 6 (Goblins)', category: 'synth_effects', isDrumKit: false },
  { program: 102, name: 'FX 7 (Echoes)', category: 'synth_effects', isDrumKit: false },
  { program: 103, name: 'FX 8 (Sci-fi)', category: 'synth_effects', isDrumKit: false },
  // Ethnic
  { program: 104, name: 'Sitar', category: 'ethnic', isDrumKit: false },
  { program: 105, name: 'Banjo', category: 'ethnic', isDrumKit: false },
  { program: 106, name: 'Shamisen', category: 'ethnic', isDrumKit: false },
  { program: 107, name: 'Koto', category: 'ethnic', isDrumKit: false },
  { program: 108, name: 'Kalimba', category: 'ethnic', isDrumKit: false },
  { program: 109, name: 'Bagpipe', category: 'ethnic', isDrumKit: false },
  { program: 110, name: 'Fiddle', category: 'ethnic', isDrumKit: false },
  { program: 111, name: 'Shanai', category: 'ethnic', isDrumKit: false },
  // Percussive
  { program: 112, name: 'Tinkle Bell', category: 'percussive', isDrumKit: false },
  { program: 113, name: 'Agogo', category: 'percussive', isDrumKit: false },
  { program: 114, name: 'Steel Drums', category: 'percussive', isDrumKit: false },
  { program: 115, name: 'Woodblock', category: 'percussive', isDrumKit: false },
  { program: 116, name: 'Taiko Drum', category: 'percussive', isDrumKit: false },
  { program: 117, name: 'Melodic Tom', category: 'percussive', isDrumKit: false },
  { program: 118, name: 'Synth Drum', category: 'percussive', isDrumKit: false },
  { program: 119, name: 'Reverse Cymbal', category: 'percussive', isDrumKit: false },
  // Sound Effects
  { program: 120, name: 'Guitar Fret Noise', category: 'sound_effects', isDrumKit: false },
  { program: 121, name: 'Breath Noise', category: 'sound_effects', isDrumKit: false },
  { program: 122, name: 'Seashore', category: 'sound_effects', isDrumKit: false },
  { program: 123, name: 'Bird Tweet', category: 'sound_effects', isDrumKit: false },
  { program: 124, name: 'Telephone Ring', category: 'sound_effects', isDrumKit: false },
  { program: 125, name: 'Helicopter', category: 'sound_effects', isDrumKit: false },
  { program: 126, name: 'Applause', category: 'sound_effects', isDrumKit: false },
  { program: 127, name: 'Gunshot', category: 'sound_effects', isDrumKit: false },
  // Drum Kit (program 128, channel 9)
  { program: 128, name: 'Standard Drum Kit', category: 'drums', isDrumKit: true },
  { program: 129, name: 'Room Drum Kit', category: 'drums', isDrumKit: true },
  { program: 130, name: 'Power Drum Kit', category: 'drums', isDrumKit: true },
  { program: 131, name: 'Electronic Drum Kit', category: 'drums', isDrumKit: true },
  { program: 132, name: 'Analog Drum Kit', category: 'drums', isDrumKit: true },
  { program: 133, name: 'Jazz Drum Kit', category: 'drums', isDrumKit: true },
  { program: 134, name: 'Brush Drum Kit', category: 'drums', isDrumKit: true },
  { program: 135, name: 'Orchestral Drum Kit', category: 'drums', isDrumKit: true },
  { program: 136, name: 'Sound FX Kit', category: 'drums', isDrumKit: true },
];

export function getInstrumentByProgram(program: number): InstrumentInfo | undefined {
  return GM_INSTRUMENTS.find(i => i.program === program);
}

export function getInstrumentsByCategory(category: InstrumentCategory): InstrumentInfo[] {
  return GM_INSTRUMENTS.filter(i => i.category === category);
}

// ── MIDI Render API ───────────────────────────────────────────────────────────

export interface MidiRenderRequest {
  project: MidiProject;
  outputFormat: 'wav' | 'mp3';
  soundfontPath?: string; // optional custom soundfont
}

export interface MidiRenderResult {
  taskId: string;
  status: string;
  websocket: string;
  audioUrl?: string;
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
  {
    id: 'd',
    label: 'Path D — Original Creation',
    desc: 'Multi-track from Scratch, Piano Roll + MIDI',
    icon: '🎹',
    prompt: '',
    inputLabel: 'MIDI Editor',
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

// ── Lyrics type (shared with LyricsVisualizer) ─────────────────────────

export type LyricLine = {
  time: number;
  text: string;
  duration?: number;
};
