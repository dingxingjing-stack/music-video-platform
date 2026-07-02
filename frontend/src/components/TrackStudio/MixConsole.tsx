/**
 * MixConsole — Cubase-style multi-track mixing console.
 *
 * Provides per-track volume faders, pan knobs, 3-band EQ, mute/solo,
 * reverb send, master volume, and export-to-stereo via /api/v1/mix/render.
 *
 * Renders as a collapsible panel above HistoryPanel.
 */

import { useState, useCallback, useMemo } from 'react';
import type { Track, MixTrackParams } from '../../types/trackStudio';
import { mixDefaults } from '../../types/trackStudio';

interface Props {
  history: Track[];
}

export function MixConsole({ history }: Props) {
  const completed = useMemo(
    () => history.filter((t) => t.status === 'completed' && t.url),
    [history],
  );

  const [mixTracks, setMixTracks] = useState<MixTrackParams[]>([]);
  const [masterVolume, setMasterVolume] = useState(0);
  const [outputFormat, setOutputFormat] = useState<'wav' | 'mp3'>('wav');
  const [collapsed, setCollapsed] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [renderResult, setRenderResult] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const initMix = useCallback(() => {
    const params = completed.map((t) => ({
      ...mixDefaults,
      trackId: t.id,
    }));
    setMixTracks(params);
    setCollapsed(false);
  }, [completed]);

  const updateTrack = useCallback(
    (trackId: string, patch: Partial<MixTrackParams>) => {
      setMixTracks((prev) =>
        prev.map((mt) => (mt.trackId === trackId ? { ...mt, ...patch } : mt)),
      );
    },
    [],
  );

  const handleExport = useCallback(async () => {
    setRendering(true);
    setRenderError(null);
    setRenderResult(null);

    try {
      const body = {
        tracks: mixTracks.map((mt) => {
          const trk = completed.find((t) => t.id === mt.trackId);
          return {
            url: trk?.url ?? '',
            volume: mt.volume,
            pan: mt.pan,
            eq: { low: mt.eqLow, mid: mt.eqMid, high: mt.eqHigh },
            solo: mt.solo,
            mute: mt.mute,
            reverb_send: mt.reverbSend,
          };
        }),
        master_volume: masterVolume,
        output_format: outputFormat,
      };

      const resp = await fetch('/api/v1/mix/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText}`);
      }

      const data = (await resp.json()) as { task_id: string; websocket: string; result_url?: string };

      const ws = new WebSocket(`ws://${window.location.host}${data.websocket}`);

      await new Promise<void>((resolve, reject) => {
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data) as Record<string, unknown>;
            if (msg.status === 'completed') {
              setRenderResult((msg.result_url as string) ?? null);
              ws.close();
              resolve();
            } else if (msg.status === 'failed') {
              setRenderError((msg.error as string) ?? 'Mix failed');
              ws.close();
              reject(new Error((msg.error as string) ?? 'Mix failed'));
            }
          } catch {
            /* ignore parse errors */
          }
        };
        ws.onerror = () => {
          setRenderError('WebSocket connection error');
          ws.close();
          reject(new Error('WebSocket error'));
        };
        setTimeout(() => {
          ws.close();
          reject(new Error('Mix render timed out'));
        }, 300000);
      });
    } catch (err) {
      setRenderError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setRendering(false);
    }
  }, [mixTracks, masterVolume, outputFormat, completed]);

  if (completed.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🎚️</span>
          <h2 className="text-sm font-semibold text-gray-300">Mix Console</h2>
          <span className="text-xs text-gray-600">({completed.length} tracks)</span>
        </div>
        <div className="flex items-center gap-2">
          {!collapsed && (
            <button
              onClick={handleExport}
              disabled={rendering || mixTracks.length === 0}
              className="px-3 py-1 text-xs bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition-all"
            >
              {rendering ? '⏳ Rendering...' : '🔊 Export Mix'}
            </button>
          )}
          <button
            onClick={() => {
              if (collapsed) {
                initMix();
              } else {
                setCollapsed(true);
                setMixTracks([]);
                setRenderResult(null);
                setRenderError(null);
              }
            }}
            className="text-xs text-gray-400 hover:text-white transition-colors"
          >
            {collapsed ? '▶ Open' : '▲ Close'}
          </button>
        </div>
      </div>

      {/* Render result */}
      {renderResult && (
        <div className="mb-3 rounded-lg border border-emerald-800 bg-emerald-950/30 p-3">
          <p className="text-xs text-emerald-400 font-medium">Mix exported successfully</p>
          <audio controls src={renderResult} className="mt-2 w-full" preload="metadata" />
          <div className="flex gap-2 mt-2">
            <a
              href={renderResult}
              download={`mix_master.${outputFormat}`}
              className="px-3 py-1 text-xs bg-emerald-700 text-white rounded hover:bg-emerald-600 transition-colors"
            >
              ⬇ Download
            </a>
          </div>
        </div>
      )}

      {renderError && (
        <div className="mb-3 rounded-lg border border-red-800 bg-red-950/30 p-3">
          <p className="text-xs text-red-400">{renderError}</p>
        </div>
      )}

      {/* Console body */}
      {!collapsed && (
        <div className="space-y-4">
          {/* Master section */}
          <div className="flex items-center gap-4 p-3 rounded-lg border border-gray-700 bg-gray-800/50">
            <span className="text-xs font-medium text-gray-400 w-12">Master</span>
            {/* Master Volume Fader */}
            <div className="flex-1 flex items-center gap-2">
              <input
                type="range"
                min={-30}
                max={6}
                step={0.5}
                value={masterVolume}
                onChange={(e) => setMasterVolume(Number(e.target.value))}
                className="flex-1 h-2 accent-amber-500"
              />
              <span className="text-xs font-mono text-amber-400 w-10 text-right">
                {masterVolume > 0 ? `+${masterVolume}` : masterVolume} dB
              </span>
            </div>
            {/* Format selector */}
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value as 'wav' | 'mp3')}
              className="px-2 py-0.5 bg-gray-700 border border-gray-600 rounded text-xs text-white"
            >
              <option value="wav">WAV</option>
              <option value="mp3">MP3</option>
            </select>
          </div>

          {/* Per-track channel strips */}
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(280px, 1fr))` }}>
            {mixTracks.map((mt) => {
              const trk = completed.find((t) => t.id === mt.trackId);
              if (!trk) return null;

              return (
                <div
                  key={mt.trackId}
                  className={`rounded-lg border p-3 space-y-3 transition-colors ${
                    mt.solo
                      ? 'border-amber-600 bg-amber-950/20'
                      : mt.mute
                        ? 'border-red-800 bg-red-950/15 opacity-60'
                        : 'border-gray-700 bg-gray-800/30'
                  }`}
                >
                  {/* Channel header */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-300 truncate max-w-[140px]">
                      {trk.name}
                    </span>
                    <div className="flex items-center gap-1">
                      {/* Solo */}
                      <button
                        onClick={() =>
                          updateTrack(mt.trackId, {
                            solo: !mt.solo,
                            mute: mt.solo ? false : mt.mute,
                          })
                        }
                        className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${
                          mt.solo
                            ? 'bg-amber-600 text-white'
                            : 'bg-gray-800 text-gray-500 hover:text-amber-400'
                        }`}
                        title="Solo"
                      >
                        S
                      </button>
                      {/* Mute */}
                      <button
                        onClick={() =>
                          updateTrack(mt.trackId, {
                            mute: !mt.mute,
                            solo: mt.mute ? false : mt.solo,
                          })
                        }
                        className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${
                          mt.mute
                            ? 'bg-red-600 text-white'
                            : 'bg-gray-800 text-gray-500 hover:text-red-400'
                        }`}
                        title="Mute"
                      >
                        M
                      </button>
                    </div>
                  </div>

                  {/* Volume fader */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-500 w-6">Vol</span>
                    <input
                      type="range"
                      min={-60}
                      max={12}
                      step={0.5}
                      value={mt.volume}
                      onChange={(e) =>
                        updateTrack(mt.trackId, { volume: Number(e.target.value) })
                      }
                      className="flex-1 h-1.5 accent-blue-400"
                    />
                    <span className="text-[10px] font-mono text-blue-400 w-10 text-right">
                      {mt.volume > 0 ? `+${mt.volume}` : mt.volume}
                    </span>
                  </div>

                  {/* Pan slider */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-500 w-6">Pan</span>
                    <input
                      type="range"
                      min={-1}
                      max={1}
                      step={0.1}
                      value={mt.pan}
                      onChange={(e) =>
                        updateTrack(mt.trackId, { pan: Number(e.target.value) })
                      }
                      className="flex-1 h-1 accent-green-400"
                    />
                    <span className="text-[10px] font-mono text-green-400 w-10 text-right">
                      {mt.pan === 0
                        ? 'C'
                        : mt.pan < 0
                          ? `L${Math.abs(mt.pan * 100).toFixed(0)}`
                          : `R${(mt.pan * 100).toFixed(0)}`}
                    </span>
                  </div>

                  {/* 3-band EQ */}
                  <div className="grid grid-cols-3 gap-1">
                    {/* Low */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-gray-500">Lo</span>
                      <input
                        type="range"
                        min={-12}
                        max={12}
                        step={1}
                        value={mt.eqLow}
                        onChange={(e) =>
                          updateTrack(mt.trackId, { eqLow: Number(e.target.value) })
                        }
                        className="w-full h-1 accent-rose-400"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '48px' }}
                      />
                      <span
                        className={`text-[9px] font-mono ${
                          mt.eqLow > 0
                            ? 'text-rose-400'
                            : mt.eqLow < 0
                              ? 'text-rose-600'
                              : 'text-gray-500'
                        }`}
                      >
                        {mt.eqLow > 0 ? `+${mt.eqLow}` : mt.eqLow || '0'}
                      </span>
                    </div>
                    {/* Mid */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-gray-500">Mid</span>
                      <input
                        type="range"
                        min={-12}
                        max={12}
                        step={1}
                        value={mt.eqMid}
                        onChange={(e) =>
                          updateTrack(mt.trackId, { eqMid: Number(e.target.value) })
                        }
                        className="w-full h-1 accent-amber-400"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '48px' }}
                      />
                      <span
                        className={`text-[9px] font-mono ${
                          mt.eqMid > 0
                            ? 'text-amber-400'
                            : mt.eqMid < 0
                              ? 'text-amber-600'
                              : 'text-gray-500'
                        }`}
                      >
                        {mt.eqMid > 0 ? `+${mt.eqMid}` : mt.eqMid || '0'}
                      </span>
                    </div>
                    {/* High */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-gray-500">Hi</span>
                      <input
                        type="range"
                        min={-12}
                        max={12}
                        step={1}
                        value={mt.eqHigh}
                        onChange={(e) =>
                          updateTrack(mt.trackId, { eqHigh: Number(e.target.value) })
                        }
                        className="w-full h-1 accent-sky-400"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '48px' }}
                      />
                      <span
                        className={`text-[9px] font-mono ${
                          mt.eqHigh > 0
                            ? 'text-sky-400'
                            : mt.eqHigh < 0
                              ? 'text-sky-600'
                              : 'text-gray-500'
                        }`}
                      >
                        {mt.eqHigh > 0 ? `+${mt.eqHigh}` : mt.eqHigh || '0'}
                      </span>
                    </div>
                  </div>

                  {/* Reverb send */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-500 w-6">Rev</span>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={mt.reverbSend}
                      onChange={(e) =>
                        updateTrack(mt.trackId, { reverbSend: Number(e.target.value) })
                      }
                      className="flex-1 h-1 accent-purple-400"
                    />
                    <span className="text-[10px] font-mono text-purple-400 w-8 text-right">
                      {(mt.reverbSend * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}