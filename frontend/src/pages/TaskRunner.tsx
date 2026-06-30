/**
 * TaskRunner — Production-ready TTS + Mock demo.
 *
 * Flow:
 *   1. User selects "Mock" or "TTS" mode
 *   2. TTS: user uploads a .wav reference audio file → base64 encode
 *   3. POST /api/v1/tts/run → task_id → WebSocket /ws/progress/{task_id}
 *   4. TaskProgressBar mounts → animates progress in real-time
 *   5. On completed → audio player shows result_url with elapsed_time
 */

import { useState, useCallback, useRef } from 'react';
import { TaskProgressBar } from '../components/TaskProgressBar';

interface TaskInfo {
  taskId: string | null;
  status: 'idle' | 'running' | 'done';
}

interface UploadedAudio {
  name: string;
  size: number;
  base64: string;
}

const API_BASE = import.meta.env.DEV ? '' : 'http://localhost:8000';

type TaskMode = 'mock' | 'tts';

export function TaskRunner() {
  const [task, setTask] = useState<TaskInfo>({
    taskId: null,
    status: 'idle',
  });
  const [mode, setMode] = useState<TaskMode>('mock');
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [ttsText, setTtsText] = useState('你好世界，这是一段语音合成测试');
  const [uploadedAudio, setUploadedAudio] = useState<UploadedAudio | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ── File upload handler ──────────────────────────────────────────────
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      setUploadedAudio(null);
      setUploadError(null);
      return;
    }

    // Validate extension
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !['wav', 'mp3', 'mp4', 'flac', 'ogg', 'm4a'].includes(ext)) {
      setUploadError('Only .wav / .mp3 / .flac / .ogg / .m4a files are accepted.');
      setUploadedAudio(null);
      return;
    }

    // Validate size (max 10 MB)
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('File too large. Maximum size is 10 MB.');
      setUploadedAudio(null);
      return;
    }

    setUploadError(null);

    // Read as base64
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result as string;
      // FileReader returns data URI: "data:audio/wav;base64,xxxx"
      // Strip the prefix for JSON transmission
      const pureBase64 = base64.includes(',')
        ? base64.split(',')[1]
        : base64;
      setUploadedAudio({
        name: file.name,
        size: file.size,
        base64: pureBase64,
      });
    };
    reader.onerror = () => {
      setUploadError('Failed to read file.');
    };
    reader.readAsDataURL(file);
  }, []);

  // ── Start task ───────────────────────────────────────────────────────
  const startTask = useCallback(async () => {
    setLoading(true);
    try {
      let url: string;
      let body: Record<string, unknown>;

      if (mode === 'mock') {
        url = `${API_BASE}/api/v1/mock/run`;
        body = {
          task_id: `demo-${Date.now()}`,
          duration: 5,
          tick_interval: 0.5,
        };
      } else {
        url = `${API_BASE}/api/v1/tts/run`;

        if (!uploadedAudio) {
          throw new Error('Please upload a reference audio file first.');
        }

        body = {
          task_id: `tts-${Date.now()}`,
          text: ttsText,
          language: 'zh',
          reference_audio: uploadedAudio.base64,
        };
      }

      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${err}`);
      }

      const data = await resp.json();

      if (!data.task_id) {
        throw new Error('No task_id in response');
      }

      setTask({ taskId: data.task_id, status: 'running' });
      setLastResult(data);
    } catch (err) {
      console.error('Failed to start task:', err);
      alert(
        `Failed to start task.\n\n${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setLoading(false);
    }
  }, [mode, ttsText, uploadedAudio]);

  const resetTask = useCallback(() => {
    setTask({ taskId: null, status: 'idle' });
    setLastResult(null);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl p-8 space-y-6">
        {/* Title */}
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-gray-900">
            WebSocket Progress Demo
          </h1>
          <p className="text-sm text-gray-500">
            Real-time task progress via WebSocket
          </p>
        </div>

        {/* Mode selector */}
        <div className="flex gap-2">
          <button
            onClick={() => setMode('mock')}
            className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              mode === 'mock'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Mock Task
          </button>
          <button
            onClick={() => setMode('tts')}
            className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              mode === 'tts'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            TTS Synthesis
          </button>
        </div>

        {/* TTS mode: text + file upload */}
        {mode === 'tts' && (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-600">Synthesis Text</label>
              <input
                type="text"
                value={ttsText}
                onChange={(e) => setTtsText(e.target.value)}
                className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-600">Reference Audio</label>
              <div className="mt-1 flex items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".wav,.mp3,.mp4,.flac,.ogg,.m4a"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  {uploadedAudio ? 'Change File' : 'Choose File'}
                </button>
                {uploadedAudio && (
                  <span className="text-xs text-green-600 truncate max-w-[200px]">
                    ✓ {uploadedAudio.name} ({(uploadedAudio.size / 1024).toFixed(0)} KB)
                  </span>
                )}
              </div>
              {uploadError && (
                <p className="mt-1 text-xs text-red-500">{uploadError}</p>
              )}
            </div>
          </div>
        )}

        {/* Last REST response */}
        {lastResult && (
          <details className="bg-gray-50 rounded-lg p-3 text-xs font-mono">
            <summary className="cursor-pointer text-gray-600 font-medium">
              Last REST Response
            </summary>
            <pre className="mt-2 text-gray-700 whitespace-pre-wrap">
              {JSON.stringify(lastResult, null, 2)}
            </pre>
          </details>
        )}

        {/* Controls */}
        <div className="flex gap-3">
          <button
            onClick={startTask}
            disabled={loading || task.status === 'running' || (mode === 'tts' && !uploadedAudio)}
            className="flex-1 px-4 py-3 bg-blue-600 text-white font-medium rounded-lg
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            {loading ? 'Starting...' : mode === 'mock' ? '🚀 Start Mock Task' : '🎤 Start TTS'}
          </button>

          {task.status === 'running' && (
            <button
              onClick={resetTask}
              className="px-4 py-3 text-gray-600 border border-gray-300 rounded-lg
                         hover:bg-gray-50 transition-colors"
            >
              Reset
            </button>
          )}
        </div>

        {/* Progress Bar */}
        {task.taskId && (
          <div className="border-t pt-6">
            <TaskProgressBar taskId={task.taskId} />
          </div>
        )}

        {/* Idle state hint */}
        {task.status === 'idle' && !task.taskId && (
          <div className="text-center py-4 text-gray-400 text-sm">
            Select a mode and click to begin
          </div>
        )}
      </div>
    </div>
  );
}
