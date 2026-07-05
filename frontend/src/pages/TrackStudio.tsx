/**
 * TrackStudio — AI Music Workbench DAW Interface
 *
 * Entry point: aggregates state, wires callbacks, composes sub-components.
 * All business logic (API calls, WS sync, localStorage) lives here.
 *
 * Layout:
 *   [Header]
 *   [PathSelector]
 *   [TrackInputArea]
 *   [BatchProgressDashboard]
 *   [TrackList] (+ live status banner)
 *   [HistoryPanel]
 *   [IdleState]
 *   [Footer]
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useWebSocketProgress } from '../hooks/useWebSocketProgress';
import { useSessionStorage } from '../hooks/useSessionStorage';
import { useTranslation } from '../i18n/useTranslation';
import type {
  Track,
  PersistedSession,
  MidiProject,
  ProjectProvenance,
  ProvenanceOperation,
  ProvenanceOperationType,
  RemixParameters,
} from '../types/trackStudio';
import {
  PATHS,
  TRACK_COLORS,
  STORAGE_VERSION,
} from '../types/trackStudio';

import { TrackStudioHeader } from '../components/TrackStudio/TrackStudioHeader';
import { PathSelector } from '../components/TrackStudio/PathSelector';
import { TrackInputArea } from '../components/TrackStudio/TrackInputArea';
import { TrackList } from '../components/TrackStudio/TrackList';
import { HistoryPanel } from '../components/TrackStudio/HistoryPanel';
import { IdleState } from '../components/TrackStudio/IdleState';
import { BatchProgressDashboard } from '../components/TrackStudio/BatchProgressDashboard';
import { MixConsole } from '../components/TrackStudio/MixConsole';
import { MVGenerator } from '../components/TrackStudio/MVGenerator';
import { ProvenanceTimeline } from '../components/TrackStudio/ProvenanceTimeline';

// ── Fetch with Retry & Concurrency Limit ──────────────────────────────────
const MAX_CONCURRENT = 4;
const runningCount = { current: 0 };
const waitQueue: Array<() => void> = [];

function acquireSlot(): Promise<void> {
  return new Promise((resolve) => {
    if (runningCount.current < MAX_CONCURRENT) {
      runningCount.current++;
      resolve();
    } else {
      waitQueue.push(resolve);
    }
  });
}

function releaseSlot() {
  runningCount.current--;
  const next = waitQueue.shift();
  if (next) {
    runningCount.current++;
    next();
  }
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retries = 3,
  baseDelay = 1000,
): Promise<Response> {
  await acquireSlot();
  try {
    for (let i = 0; i <= retries; i++) {
      const resp = await fetch(url, options);
      if (resp.status !== 429) return resp;
      if (i === retries) return resp;
      const delay = baseDelay * 2 ** i + Math.random() * 500;
      await new Promise((r) => setTimeout(r, delay));
    }
    throw new Error('Unexpected fetchWithRetry exit');
  } finally {
    releaseSlot();
  }
}

// ── API Types ──────────────────────────────────────────────────────────────

interface ApiResult {
  task_id: string;
  status: string;
  websocket: string;
  path?: string;
}

interface BatchApiResult {
  batch_id: string;
  path: string;
  total: number;
  status: string;
  websocket: string;
}

// ── Main Component ─────────────────────────────────────────────────────────

export function TrackStudio() {
  const { t } = useTranslation();

  // ── Session persistence ──────────────────────────────────────────────
  const { session, setSession } = useSessionStorage();
  const workflow = session.activeWorkflow;
  const history = session.history;

  // ── Workflow / History setters via session ───────────────────────────
  const setWorkflow = useCallback(
    (
      fn:
        | ((
            prev: PersistedSession['activeWorkflow'],
          ) => PersistedSession['activeWorkflow'])
        | PersistedSession['activeWorkflow'],
    ) => {
      setSession({
        activeWorkflow:
          typeof fn === 'function'
            ? fn(workflow)
            : (fn as PersistedSession['activeWorkflow']),
      });
    },
    [setSession, workflow],
  );

  const setHistoryState = useCallback(
    (fn: (prev: Track[]) => Track[]) => {
      setSession({ history: fn(history) });
    },
    [setSession, history],
  );

  // ── Local state ──────────────────────────────────────────────────────
  const [selectedPath, setSelectedPath] = useState<'a' | 'b' | 'c' | 'd'>('a');
  const [prompt, setPrompt] = useState(PATHS[0].prompt);
  const [ttsText, setTtsText] = useState('');
  const [uploadedFile, setUploadedFile] = useState<{
    name: string;
    base64: string;
    size: number;
  } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedTrack, setSelectedTrack] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // ── Provenance Tracking ────────────────────────────────────────────────
  const [provenance, setProvenance] = useState<ProjectProvenance | null>(null);

  const createProvenance = useCallback(
    (): ProjectProvenance => ({
      projectId: `prov-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createdAt: Date.now(),
      originality: 'original',
      sourceTrackId: null,
      operations: [],
    }),
    [],
  );

  const recordOp = useCallback(
    (type: ProvenanceOperationType, params: Record<string, unknown>, resultTrackId?: string) => {
      setProvenance((prev) => {
        if (!prev) {
          return createProvenance();
        }
        const op: ProvenanceOperation = {
          type,
          timestamp: Date.now(),
          params,
          resultTrackId,
        };
        return { ...prev, operations: [...prev.operations, op] };
      });
    },
    [createProvenance],
  );

  const markDerivative = useCallback(
    (sourceTrackId: string) => {
      setProvenance((prev) => {
        if (!prev) return prev;
        return { ...prev, originality: 'derivative', sourceTrackId };
      });
    },
    [],
  );

  // ── Path D: MIDI Project ─────────────────────────────────────────────────
  const [midiProject, setMidiProject] = useState<MidiProject | null>(null);

  // ── Batch mode ───────────────────────────────────────────────────────
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
  const [batchDuration, setBatchDuration] = useState(10);
  const [batchTemperature, setBatchTemperature] = useState(0.8);

  // ── WebSocket progress hook ──────────────────────────────────────────
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

  // ── Persist state on changes ─────────────────────────────────────────
  useEffect(() => {
    if (!workflow.taskId && !workflow.running && !workflow.completed) return;
    setSession({
      version: STORAGE_VERSION,
      activeWorkflow: { ...workflow },
      history,
    });
  }, [workflow, history]);

  // ── Batch ETA helper ─────────────────────────────────────────────────
  const getBatchETA = useCallback(() => {
    if (!batchState || !batchStartTime || batchState.completed === 0) return '';
    const elapsed = (Date.now() - batchStartTime) / 1000;
    const avgPerItem = elapsed / batchState.completed;
    const remaining =
      (batchState.total - batchState.completed - batchState.failed) * avgPerItem;
    if (remaining > 60)
      return `${Math.ceil(remaining / 60)}m ${Math.ceil(remaining % 60)}s`;
    return `${Math.ceil(remaining)}s`;
  }, [batchState, batchStartTime]);

  // ── File Upload Handler ──────────────────────────────────────────────
  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) {
        setUploadedFile(null);
        setUploadError(null);
        return;
      }

      const ext = file.name.split('.').pop()?.toLowerCase();
      if (
        !ext ||
        !['wav', 'mp3', 'mp4', 'flac', 'ogg', 'm4a', 'aac'].includes(ext)
      ) {
        setUploadError(t('errors.unsupportedFormat'));
        setUploadedFile(null);
        return;
      }

      if (file.size > 50 * 1024 * 1024) {
        setUploadError(t('errors.fileTooLarge'));
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
      reader.onerror = () => setUploadError(t('errors.uploadFailed'));
      reader.readAsDataURL(file);
    },
    [t],
  );

  const handleFileRemove = useCallback(() => {
    setUploadedFile(null);
    setUploadError(null);
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
        body.tts_text = ttsText || t('common.helloWorld');
        body.duration = 10;
        if (uploadedFile) {
          body.reference_audio = uploadedFile.base64;
        }
      } else if (selectedPath === 'c') {
        if (!uploadedFile) {
          throw new Error(t('errors.audioRequired'));
        }
        body.audio_base64 = uploadedFile.base64;
        body.stem_count = t('common.stemCount4');
      } else if (selectedPath === 'd') {
        if (!midiProject) {
          throw new Error(t('errors.midiProjectRequired'));
        }
        body.midi_project = midiProject;
      }

      const resp = await fetchWithRetry(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${err}`);
      }

      const data: ApiResult = await resp.json();
      const path = (data.path || selectedPath) as 'a' | 'b' | 'c' | 'd';

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
        error: err instanceof Error ? err.message : t('errors.unknownError'),
      }));
    } finally {
      setLoading(false);
    }
  }, [selectedPath, prompt, ttsText, uploadedFile, t, setWorkflow]);

  // ── Batch Start Handler ────────────────────────────────────────────
  const startBatch = useCallback(async () => {
    const lines = batchPrompts.trim().split('\n').filter((l) => l.trim());
    if (lines.length === 0) {
      alert(t('errors.batchEmpty'));
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
        const texts = ttsText.trim()
          ? ttsText.split('\n')
          : lines.map((_, i) => t('common.trackNum', { n: i + 1 }));
        body = {
          items: lines.map((p, i) => ({
            prompt: p.trim(),
            tts_text: texts[i % texts.length]?.trim() || t('common.trackNum', { n: i + 1 }),
            duration: batchDuration,
          })),
        };
      } else {
        throw new Error(t('errors.batchNotSupported'));
      }

      const resp = await fetchWithRetry(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${err}`);
      }

      const data: BatchApiResult = await resp.json();

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
      const ws = new WebSocket(
        `ws://${window.location.host}/ws/progress/${data.batch_id}`,
      );
      batchWsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as Record<string, unknown>;
          const metadata = (msg.metadata ?? {}) as Record<string, unknown>;
          const current =
            metadata.current_item as Record<string, unknown> | undefined;
          const batchCompleted = Number(
            (metadata as Record<string, unknown>).batch_completed ?? 0,
          );
          const batchFailed = Number(
            (metadata as Record<string, unknown>).batch_failed ?? 0,
          );
          const batchPath = (
            metadata as Record<string, unknown>
          ).path as string | undefined;

          setBatchState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              path: batchPath || prev.path,
              completed: batchCompleted,
              failed: batchFailed,
              currentPrompt: current?.prompt
                ? String(current.prompt)
                : prev.currentPrompt,
              running: msg.status !== 'completed' && msg.status !== 'failed',
            };
          });
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setBatchState((prev) =>
          prev ? { ...prev, running: false } : null,
        );
      };

      ws.onerror = () => {
        setBatchState((prev) =>
          prev ? { ...prev, error: t('errors.networkError') } : null,
        );
      };
    } catch (err) {
      console.error('Batch failed:', err);
      setBatchState((prev) =>
        prev
          ? {
              ...prev,
              error: err instanceof Error ? err.message : t('errors.unknownError'),
              running: false,
            }
          : null,
      );
    } finally {
      setLoading(false);
    }
  }, [
    batchMode,
    batchPrompts,
    selectedPath,
    batchDuration,
    batchTemperature,
    ttsText,
    startWorkflow,
    t,
  ]);

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
          const name =
            prev.path === 'a'
              ? `${t('ui.musicGenPrefix')}${(prompt || '').slice(0, 30)}`
              : prev.path === 'b'
              ? `${t('ui.hybridPrefix')}${(prompt || '').slice(0, 20)}`
              : t('ui.remixProcessing');
          return {
            ...prev,
            tracks: [
              {
                id: `track-${prev.taskId}`,
                name,
                type: prev.path === 'b' ? 'tts' : 'music',
                status: mappedStatus,
                url: wsResultUrl || null,
                progress: wsProgress,
                color: TRACK_COLORS[0],
              },
            ],
            running: !isTerminal,
            completed: wsStatus === 'completed',
            error:
              wsStatus === 'failed'
                ? wsError || t('errors.generationFailed')
                : prev.error,
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
          error:
            wsStatus === 'failed'
              ? wsError || t('errors.generationFailed')
              : prev.error,
        };
      });
    }
  }, [
    wsStatus,
    wsProgress,
    wsMessage,
    wsResultUrl,
    wsError,
    workflow.taskId,
    prompt,
    t,
    setWorkflow,
  ]);

  // ── Completed tracks → history ───────────────────────────────────────
  useEffect(() => {
    if (workflow.completed && workflow.tracks.length > 0) {
      const completedTracks = workflow.tracks
        .filter((t) => t.status === 'completed' && t.url)
        .map((t) => ({ ...t, createdAt: Date.now() }));

      if (completedTracks.length > 0) {
        // Record generate operation in provenance
        const firstTrack = completedTracks[0];
        const opType: ProvenanceOperationType = 'generate';
        const pathParams: Record<string, unknown> = { path: workflow.path };
        if (prompt) pathParams.prompt = prompt;
        recordOp(opType, pathParams, firstTrack.id);

        setHistoryState((prev) =>
          [...completedTracks, ...prev].slice(0, 50),
        );
      }

      // Clear active workflow after delay so user sees completion
      setTimeout(() => {
        setWorkflow((prev) => ({
          ...prev,
          running: false,
          tracks: [],
          taskId: null,
        }));
      }, 2000);
    }
  }, [workflow.completed, setHistoryState, setWorkflow]);

  // ── Track Actions ────────────────────────────────────────────────────
  const handleRenameTrack = useCallback((trackId: string, newName: string) => {
    setWorkflow((prev) => ({
      ...prev,
      tracks: prev.tracks.map((t) =>
        t.id === trackId ? { ...t, name: newName } : t,
      ),
    }));
    setHistoryState((prev) =>
      prev.map((t) => (t.id === trackId ? { ...t, name: newName } : t)),
    );
  }, [setWorkflow, setHistoryState]);

  const handleDeleteTrack = useCallback((trackId: string) => {
    setWorkflow((prev) => ({
      ...prev,
      tracks: prev.tracks.filter((t) => t.id !== trackId),
    }));
    setHistoryState((prev) => prev.filter((t) => t.id !== trackId));
    if (selectedTrack === trackId) setSelectedTrack(null);
  }, [selectedTrack, setWorkflow, setHistoryState]);

  const handleTrimChange = useCallback(
    (trackId: string, start: number, end: number) => {
      setHistoryState((prev) =>
        prev.map((t) =>
          t.id === trackId ? { ...t, trimStart: start, trimEnd: end } : t,
        ),
      );
    },
    [setHistoryState],
  );

  const handleClearHistory = useCallback(() => {
    if (confirm(t('common.clearConfirm'))) {
      setHistoryState(() => []);
    }
  }, [t, setHistoryState]);

  // ── Reset ────────────────────────────────────────────────────────────
  const resetStudio = useCallback(() => {
    setWorkflow(() => ({
      path: null,
      taskId: null,
      tracks: [],
      running: false,
      completed: false,
      error: null,
    }));
    setSelectedTrack(null);
    setBatchState(null);
    setBatchStartTime(null);
    setProvenance(null);
    if (batchWsRef.current) {
      batchWsRef.current.onclose = null;
      batchWsRef.current.close();
    }
  }, [setWorkflow]);

  // ── Path selection handler ───────────────────────────────────────────
  const handleTrackSelect = useCallback((trackId: string | null) => {
    setSelectedTrack(trackId);
  }, []);

  const handleSelectPath = useCallback(
    (path: 'a' | 'b' | 'c' | 'd') => {
      setSelectedPath(path);
      const def = PATHS.find((p) => p.id === path)!;
      setPrompt(def.prompt || '');
      setTtsText(def.ttsDefault || '');
      setUploadedFile(null);
      setUploadError(null);
      setBatchMode(false);
      setBatchPrompts('');
      
      // Initialize MIDI project for Path D
      if (path === 'd') {
        const defaultProject: MidiProject = {
          id: `midi-${Date.now()}`,
          name: 'New MIDI Project',
          tempo: 120,
          timeSignature: { numerator: 4, denominator: 4 },
          ticksPerQuarter: 480,
          tracks: [
            {
              id: `track-${Date.now()}-1`,
              name: 'Piano',
              instrument: 0, // Acoustic Grand Piano
              channel: 0,
              notes: [],
              color: TRACK_COLORS[0],
              solo: false,
              mute: false,
              volume: 1,
              pan: 0,
            },
          ],
          loopStartTick: 0,
          loopEndTick: 480 * 16, // 4 bars
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        setMidiProject(defaultProject);
      } else {
        setMidiProject(null);
      }
      
      resetStudio();
    },
    [resetStudio],
  );

  // ── Remix completion handlers ───────────────────────────────────────
  const handleRemixComplete = useCallback(
    (newTrack: Track) => {
      // Add new remix track to history
      setHistoryState((prev) => [newTrack, ...prev].slice(0, 50));
    },
    [setHistoryState],
  );

  const handleRemixDone = useCallback(
    (sourceTrackId: string, params: RemixParameters) => {
      // Mark as derivative and record remix operation with detailed params
      markDerivative(sourceTrackId);

      let opType: ProvenanceOperationType = 'remix_timbre_transform';
      if (params.pitchShift && Math.abs(params.pitchShift) > 0) {
        opType = 'remix_pitch_shift';
      } else if (params.tempoMultiplier && Math.abs(params.tempoMultiplier - 1) > 0.01) {
        opType = 'remix_tempo_change';
      }

      recordOp(opType, {
        sourceTrackId,
        pitchShift: params.pitchShift,
        tempoMultiplier: params.tempoMultiplier,
        timbreTransform: params.timbreTransform,
      });
    },
    [markDerivative, recordOp],
  );

  const handleRemixError = useCallback(
    (error: string) => {
      console.error('Remix failed:', error);
    },
    [],
  );

  // ── Derived values ───────────────────────────────────────────────────
  const isGenerateDisabled =
    loading ||
    workflow.running ||
    (selectedPath === 'c' && !uploadedFile) ||
    (selectedPath === 'd' && !midiProject) ||
    (!batchMode && selectedPath === 'b' && !prompt);

  const hasWorkflowResult = workflow.completed || workflow.error;

  // ── Render ───────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white">
      <TrackStudioHeader
        workflow={workflow}
        historyLength={history.length}
        wsConnected={wsConnected}
        wsStatus={wsStatus}
      />

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Path Selector */}
        <PathSelector
          selectedPath={selectedPath}
          running={workflow.running}
          onSelectPath={handleSelectPath}
        />

        {/* Input Area */}
        <TrackInputArea
          pathDef={currentPathDef}
          batchMode={batchMode}
          batchPrompts={batchPrompts}
          ttsText={ttsText}
          uploadedFile={
            uploadedFile ? { name: uploadedFile.name, size: uploadedFile.size } : null
          }
          uploadError={uploadError}
          batchDuration={batchDuration}
          batchTemperature={batchTemperature}
          onPromptChange={setPrompt}
          onTtsTextChange={setTtsText}
          onBatchPromptsChange={setBatchPrompts}
          onFileUpload={handleFileUpload}
          onFileRemove={handleFileRemove}
          onBatchModeToggle={(batch) => {
            setBatchMode(batch);
            if (!batch) setBatchPrompts('');
          }}
          onDurationChange={setBatchDuration}
          onTemperatureChange={setBatchTemperature}
          disabled={isGenerateDisabled}
          loading={loading}
          onStart={batchMode ? startBatch : startWorkflow}
          onReset={resetStudio}
          hasWorkflowResult={Boolean(hasWorkflowResult)}
          midiProject={midiProject ?? undefined}
          onMidiProjectChange={setMidiProject}
        />

        {/* Batch Progress Dashboard */}
        {batchState && (batchState.running || batchState.error) && (
          <BatchProgressDashboard
            batchState={batchState}
            getETA={getBatchETA}
          />
        )}

        {/* Error Display */}
        {workflow.error && (
          <div className="rounded-xl border border-red-800 bg-red-950/50 p-4">
            <p className="text-sm text-red-300 font-medium">{t('common.error')}</p>
            <p className="text-xs text-red-400 mt-1 font-mono">
              {workflow.error}
            </p>
          </div>
        )}

        {/* Active Tracks */}
        <TrackList
          tracks={workflow.tracks}
          selectedTrack={selectedTrack}
          wsStatus={wsStatus}
          wsProgress={wsProgress}
          wsMessage={wsMessage}
          wsConnected={wsConnected}
          wsElapsedTime={wsElapsedTime}
          onTrackSelect={setSelectedTrack}
          onRename={handleRenameTrack}
          onDelete={handleDeleteTrack}
          onTrimChange={handleTrimChange}
          onRemixComplete={handleRemixComplete}
          onRemixError={handleRemixError}
        />

        {/* Mix Console */}
        <MixConsole history={history} />

        {/* MV Generator */}
        <MVGenerator history={history} onTrackSelect={(track) => handleTrackSelect(track.id)} />

        {/* Provenance Timeline */}
        {provenance && provenance.operations.length > 0 && (
          <ProvenanceTimeline provenance={provenance} />
        )}

        {/* History */}
        <HistoryPanel
          history={history}
          onClear={handleClearHistory}
          onRename={handleRenameTrack}
          onDelete={handleDeleteTrack}
          onTrimChange={handleTrimChange}
          onRemixComplete={handleRemixComplete}
          onRemixError={handleRemixError}
          onRemixDone={handleRemixDone}
        />

        {/* Idle State */}
        {!workflow.running &&
          !workflow.completed &&
          !workflow.error &&
          workflow.tracks.length === 0 &&
          history.length === 0 && <IdleState />}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-12 py-4 text-center text-xs text-gray-600">
        {t('common.appName')} v3.1 · Built with React + Vite + FastAPI
      </footer>
    </div>
  );
}