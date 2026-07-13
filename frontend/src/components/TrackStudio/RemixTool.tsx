/**
 * RemixTool — Audio modification panel for completed tracks.
 * Pitch shift, tempo, timbre presets. WebSocket progress.
 * Renders as an expandable section inside a completed track card.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { Track, RemixParameters } from '../../types/trackStudio';

type TimbrePreset = RemixParameters['timbreTransform'];

interface Props {
  track: Track;
  onRemixComplete: (newTrack: Track) => void;
  onRemixError: (error: string) => void;
  onRemixDone?: (sourceTrackId: string, params: RemixParameters) => void;
}

const TIMBRE_PRESETS: NonNullable<RemixParameters['timbreTransform']>[] = ['warm', 'bright', 'dark', 'thin', 'heavy'];

export function RemixTool({ track, onRemixComplete, onRemixError, onRemixDone }: Props) {
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
              color: '#ff6a10',
              createdAt: Date.now(),
            };
            const remixParams: RemixParameters = { pitchShift: pitch, tempoMultiplier: tempo, timbreTransform: timbre };
            onRemixDone?.(track.id, remixParams);
            onRemixComplete(newTrack);
            setCollapsed(true);
            setSubmitting(false);
          } else if (msg.status === 'failed') {
            const errMsg = (msg.error as string) ?? 'Remix failed';
            onRemixError(errMsg);
            setSubmitting(false);
            ws.close();
          }
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        onRemixError('WebSocket connection error');
        setSubmitting(false);
        ws.close();
      };
    } catch (err) {
      onRemixError(err instanceof Error ? err.message : 'Unknown remix error');
      setSubmitting(false);
    }
  }, [track, pitch, tempo, timbre, onRemixComplete, onRemixError, onRemixDone]);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <div className="mt-2 border-t border-[#2a2a38] pt-2">
      {/* Toggle button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-1 text-[10px] font-medium text-[#ff6a10] hover:text-[#ff6a10] transition-colors"
        title="Remix this track"
      >
        <span className="text-xs">{collapsed ? '➕' : '➖'}</span>
        <span style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Remix</span>
      </button>

      {/* Controls panel */}
      {!collapsed && (
        <div className="mt-2 space-y-2.5">
          {/* Pitch slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-[#777777] w-10 text-right">Pitch</label>
            <input
              type="range" min={-12} max={12} step={1}
              value={pitch}
              onChange={(e) => setPitch(Number(e.target.value))}
              className="flex-1 h-1.5 accent-[#ff6a10]"
            />
            <span className="text-[10px] font-mono text-[#ff6a10] w-8 text-right">
              {pitch > 0 ? `+${pitch}` : pitch}st
            </span>
          </div>

          {/* Tempo slider */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-[#777777] w-10 text-right">Tempo</label>
            <input
              type="range" min={0.5} max={2} step={0.1}
              value={tempo}
              onChange={(e) => setTempo(Number(e.target.value))}
              className="flex-1 h-1.5 accent-[#38bdf8]"
            />
            <span className="text-[10px] font-mono text-[#38bdf8] w-10 text-right">
              {tempo.toFixed(1)}x
            </span>
          </div>

          {/* Timbre dropdown */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-[#777777] w-10 text-right">Timbre</label>
            <select
              value={timbre}
              onChange={(e) => setTimbre(e.target.value as TimbrePreset)}
              className="flex-1 px-2 py-1 bg-[#2a2a38] border border-[#2a2a38] rounded text-xs text-[#b0b0b0] focus:outline-none focus:ring-1 focus:ring-[#ff6a10]/50"
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
            className="w-full px-3 py-1.5 text-xs font-semibold rounded-lg transition-all
              bg-[#ff6a10] text-white
              hover:bg-[#ff6a10] disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ fontFamily: "'Space Grotesk', sans-serif" }}
          >
            {submitting ? '⏳ Processing...' : '🎛️ Generate Remix'}
          </button>
        </div>
      )}
    </div>
  );
}
