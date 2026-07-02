/**
 * RemixTool — Audio modification panel for completed tracks.
 *
 * Provides pitch (-12..+12 semitones), tempo (0.5x..2.0x), and timbre
 * presets. Submits a remix job to /api/v1/remix/process and reports
 * progress via WebSocket.
 *
 * Renders as a collapsible floating menu inside a completed track card.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { Track, RemixParameters } from '../../types/trackStudio';

type TimbrePreset = RemixParameters['timbreTransform'];

interface Props {
  track: Track;
  onRemixComplete: (newTrack: Track) => void;
  onRemixError: (error: string) => void;
}

const TIMBRE_PRESETS: NonNullable<RemixParameters['timbreTransform']>[] = ['warm', 'bright', 'dark', 'thin', 'heavy'];

export function RemixTool({ track, onRemixComplete, onRemixError }: Props) {
  const [pitch, setPitch] = useState(0);
  const [tempo, setTempo] = useState(1.0);
  const [timbre, setTimbre] = useState<TimbrePreset>('warm');
  const [submitting, setSubmitting] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);

  const handleRemix = useCallback(async () => {
    if (!track.url) return;

    setSubmitting(true);
    const params: RemixParameters = {
      pitchShift: pitch,
      tempoMultiplier: tempo,
      timbreTransform: timbre,
    };

    try {
      const resp = await fetch('/api/v1/remix/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_track_id: track.id,
          source_url: track.url,
          ...params,
        }),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText}`);
      }

      const data = (await resp.json()) as { task_id: string; websocket: string };

      // Connect to WS for remix progress
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
      const ws = new WebSocket(`ws://${window.location.host}${data.websocket}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as Record<string, unknown>;
          if (msg.status === 'completed') {
            const newTrack: Track = {
              id: `remix-${data.task_id}`,
              name: `${track.name} (remixed)`,
              type: track.type,
              status: 'completed',
              url: (msg.result_url as string) || null,
              progress: 100,
              color: '#8b5cf6',
              createdAt: Date.now(),
            };
            onRemixComplete(newTrack);
            setCollapsed(true);
          } else if (msg.status === 'failed') {
            onRemixError(
              (msg.message as string) || 'Remix generation failed',
            );
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        setSubmitting(false);
      };
    } catch (err) {
      console.error('Remix failed:', err);
      onRemixError(
        err instanceof Error ? err.message : 'Unknown error',
      );
      setSubmitting(false);
    }
  }, [track.id, track.name, track.type, track.url, pitch, tempo, timbre]);

  // Cleanup WS on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <div className="mt-2 border-t border-gray-800 pt-2">
      {/* Toggle button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-1 text-[10px] text-purple-400 hover:text-purple-300 transition-colors"
        title="Remix this track"
      >
        <span className="text-xs">{collapsed ? '➕' : '➖'}</span>
        <span>Remix</span>
      </button>

      {/* Controls panel */}
      {!collapsed && (
        <div className="mt-2 space-y-2">
          {/* Pitch slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-gray-400 w-10 text-right">
              Pitch
            </label>
            <input
              type="range"
              min={-12}
              max={12}
              step={1}
              value={pitch}
              onChange={(e) => setPitch(Number(e.target.value))}
              className="flex-1 h-1 accent-purple-400"
            />
            <span className="text-[10px] text-purple-400 font-mono w-8 text-right">
              {pitch > 0 ? `+${pitch}` : pitch}st
            </span>
          </div>

          {/* Tempo slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-gray-400 w-10 text-right">
              Tempo
            </label>
            <input
              type="range"
              min={0.5}
              max={2}
              step={0.1}
              value={tempo}
              onChange={(e) => setTempo(Number(e.target.value))}
              className="flex-1 h-1 accent-purple-400"
            />
            <span className="text-[10px] text-purple-400 font-mono w-12 text-right">
              {tempo.toFixed(1)}x
            </span>
          </div>

          {/* Timbre dropdown */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-gray-400 w-10 text-right">
              Timbre
            </label>
            <select
              value={timbre}
              onChange={(e) => setTimbre(e.target.value as TimbrePreset)}
              className="flex-1 px-1 py-0.5 bg-gray-800 border border-gray-700 rounded text-[10px] text-white focus:outline-none"
            >
              {TIMBRE_PRESETS.map((t) => (
                <option key={t} value={t}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <button
            onClick={handleRemix}
            disabled={submitting}
            className="w-full px-2 py-1 text-[10px] bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white rounded hover:from-purple-500 hover:to-fuchsia-500 disabled:opacity-50 transition-all"
          >
            {submitting ? '⏳ Processing...' : '🎛️ Generate Remix'}
          </button>
        </div>
      )}
    </div>
  );
}
