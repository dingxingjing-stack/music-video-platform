/**
 * MixConsole — Enterprise-grade multi-track mixing console.
 * Per-track volume faders, pan, 3-band EQ, mute/solo, reverb send.
 * Master volume + format selector. WebSocket progress streaming.
 */

import { useState, useCallback, useMemo } from 'react';
import type { Track, MixTrackParams } from '../../types/trackStudio';
import { mixDefaults } from '../../types/trackStudio';

interface Props {
  history: Track[];
}

/* ── helpers ─────────────────────────────────────────────────────── */

function fmtDb(v: number): string {
  return v > 0 ? `+${v}` : `${v}`;
}

function fmtPan(v: number): string {
  if (Math.abs(v) < 0.05) return 'C';
  return v < 0 ? `L${Math.abs(v * 100).toFixed(0)}` : `R${(v * 100).toFixed(0)}`;
}

/* ── Component ───────────────────────────────────────────────────── */

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
  const [progress, setProgress] = useState(0);
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
    setProgress(0);
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
              setProgress(100);
              ws.close();
              resolve();
            } else if (msg.status === 'failed') {
              setRenderError((msg.error as string) ?? 'Mix failed');
              ws.close();
              reject(new Error((msg.error as string) ?? 'Mix failed'));
            } else if (typeof msg.progress === 'number') {
              setProgress(msg.progress);
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
    <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f] p-3 sm:p-5 space-y-4" style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-base font-bold text-[#ff6a10]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>◆</span>
          <h2 className="text-sm font-semibold text-[#e0e0e0]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Mix Console</h2>
          <span className="text-xs px-2 py-0.5 bg-[#ff6a10]/10 text-[#ff6a10] rounded-full">
            {completed.length} track{completed.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!collapsed && (
            <>
              <button
                onClick={handleExport}
                disabled={rendering || mixTracks.length === 0}
                className="px-4 py-1.5 text-xs font-semibold rounded-lg transition-all
                  bg-[#ff6a10] text-white
                  hover:bg-[#ff6a10] disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                {rendering ? `⏳ ${progress}%` : '🔊 Export Mix'}
              </button>
              <button
                onClick={() => { setCollapsed(true); setMixTracks([]); setRenderResult(null); setRenderError(null); }}
                className="text-xs text-[#b0b0b0] hover:text-[#e0e0e0] transition-colors"
              >
                ▲ Close
              </button>
            </>
          )}
          {collapsed && (
            <button
              onClick={initMix}
              className="text-xs text-[#b0b0b0] hover:text-[#ff6a10] transition-colors"
            >
              ▶ Open Console
            </button>
          )}
        </div>
      </div>

      {/* ── Render Result ── */}
      {renderResult && (
        <div className="rounded-lg border border-[#76b900]/30 bg-[#76b900]/5 p-3 space-y-2">
          <p className="text-xs font-medium text-[#76b900]">Mix exported successfully</p>
          <audio controls src={renderResult} className="w-full" preload="metadata" />
          <a
            href={renderResult}
            download={`mix_master.${outputFormat}`}
            className="inline-block px-3 py-1 text-xs font-medium bg-[#76b900]/20 text-[#76b900] rounded hover:bg-[#76b900]/30 transition-colors"
          >
            ⬇ Download .{outputFormat}
          </a>
        </div>
      )}

      {renderError && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/20 p-3">
          <p className="text-xs text-red-400">{renderError}</p>
        </div>
      )}

      {/* ── Console Body ── */}
      {!collapsed && (
        <div className="space-y-4">
          {/* Master Section */}
          <div className="flex items-center gap-4 p-3 rounded-lg border border-[#2a2a38] bg-[#262626]">
            <span className="text-xs font-semibold text-[#ff6a10] w-14" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>MASTER</span>
            <div className="flex-1 flex items-center gap-3">
              <span className="text-[10px] text-[#777777] w-8">Vol</span>
              <input
                type="range" min={-30} max={6} step={0.5}
                value={masterVolume}
                onChange={(e) => setMasterVolume(Number(e.target.value))}
                className="flex-1 h-2 accent-[#ff6a10]"
              />
              <span className="text-xs font-mono text-[#ff6a10] w-10 text-right">
                {fmtDb(masterVolume)} dB
              </span>
            </div>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value as 'wav' | 'mp3')}
              className="px-2 py-1 bg-[#2a2a38] border border-[#2a2a38] rounded text-xs text-[#b0b0b0] focus:outline-none focus:ring-1 focus:ring-[#ff6a10]/50"
            >
              <option value="wav">WAV</option>
              <option value="mp3">MP3</option>
            </select>
          </div>

          {/* Progress Bar */}
          {rendering && (
            <div className="h-1.5 bg-[#2a2a38] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[#ff6a10] to-[#ff6a10] rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          {/* Channel Strips */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {mixTracks.map((mt) => {
              const trk = completed.find((t) => t.id === mt.trackId);
              if (!trk) return null;

              const borderColor = mt.solo ? '#ff6a10' : mt.mute ? '#ef4444' : '#2a2a38';
              const bgColor = mt.solo ? 'rgba(230,90,11,0.08)' : mt.mute ? 'rgba(239,68,68,0.05)' : 'transparent';

              return (
                <div
                  key={mt.trackId}
                  className="rounded-lg border p-3 space-y-2.5 transition-all"
                  style={{ borderColor, backgroundColor: bgColor }}
                >
                  {/* Channel Header */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-[#e0e0e0] truncate max-w-[120px]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                      {trk.name}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => updateTrack(mt.trackId, { solo: !mt.solo, mute: mt.solo ? false : mt.mute })}
                        className={`px-1.5 py-0.5 text-[10px] font-bold rounded transition-colors ${
                          mt.solo
                            ? 'bg-[#ff6a10] text-white'
                            : 'bg-[#262626] text-[#777777] hover:text-[#ff6a10]'
                        }`}
                        title="Solo"
                      >
                        S
                      </button>
                      <button
                        onClick={() => updateTrack(mt.trackId, { mute: !mt.mute, solo: mt.mute ? false : mt.solo })}
                        className={`px-1.5 py-0.5 text-[10px] font-bold rounded transition-colors ${
                          mt.mute
                            ? 'bg-red-600 text-white'
                            : 'bg-[#262626] text-[#777777] hover:text-red-400'
                        }`}
                        title="Mute"
                      >
                        M
                      </button>
                    </div>
                  </div>

                  {/* Volume Fader */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[#777777] w-6">Vol</span>
                    <input
                      type="range" min={-60} max={12} step={0.5}
                      value={mt.volume}
                      onChange={(e) => updateTrack(mt.trackId, { volume: Number(e.target.value) })}
                      className="flex-1 h-1.5 accent-[#ff6a10]"
                    />
                    <span className="text-[10px] font-mono text-[#ff6a10] w-10 text-right">
                      {fmtDb(mt.volume)}
                    </span>
                  </div>

                  {/* Pan Slider */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[#777777] w-6">Pan</span>
                    <input
                      type="range" min={-1} max={1} step={0.1}
                      value={mt.pan}
                      onChange={(e) => updateTrack(mt.trackId, { pan: Number(e.target.value) })}
                      className="flex-1 h-1 accent-[#38bdf8]"
                    />
                    <span className="text-[10px] font-mono text-[#38bdf8] w-10 text-right">
                      {fmtPan(mt.pan)}
                    </span>
                  </div>

                  {/* 3-Band EQ */}
                  <div className="grid grid-cols-3 gap-1.5">
                    {/* Low */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[8px] text-[#777777]">Lo</span>
                      <input
                        type="range" min={-12} max={12} step={1}
                        value={mt.eqLow}
                        onChange={(e) => updateTrack(mt.trackId, { eqLow: Number(e.target.value) })}
                        className="accent-rose-400"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '40px', width: '16px' }}
                      />
                      <span className={`text-[8px] font-mono ${mt.eqLow > 0 ? 'text-rose-400' : mt.eqLow < 0 ? 'text-rose-600' : 'text-[#777777]'}`}>
                        {mt.eqLow > 0 ? `+${mt.eqLow}` : mt.eqLow || '0'}
                      </span>
                    </div>
                    {/* Mid */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[8px] text-[#777777]">Mid</span>
                      <input
                        type="range" min={-12} max={12} step={1}
                        value={mt.eqMid}
                        onChange={(e) => updateTrack(mt.trackId, { eqMid: Number(e.target.value) })}
                        className="accent-[#ff6a10]"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '40px', width: '16px' }}
                      />
                      <span className={`text-[8px] font-mono ${mt.eqMid > 0 ? 'text-[#ff6a10]' : mt.eqMid < 0 ? 'text-orange-700' : 'text-[#777777]'}`}>
                        {mt.eqMid > 0 ? `+${mt.eqMid}` : mt.eqMid || '0'}
                      </span>
                    </div>
                    {/* High */}
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-[8px] text-[#777777]">Hi</span>
                      <input
                        type="range" min={-12} max={12} step={1}
                        value={mt.eqHigh}
                        onChange={(e) => updateTrack(mt.trackId, { eqHigh: Number(e.target.value) })}
                        className="accent-sky-400"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl', height: '40px', width: '16px' }}
                      />
                      <span className={`text-[8px] font-mono ${mt.eqHigh > 0 ? 'text-sky-400' : mt.eqHigh < 0 ? 'text-sky-600' : 'text-[#777777]'}`}>
                        {mt.eqHigh > 0 ? `+${mt.eqHigh}` : mt.eqHigh || '0'}
                      </span>
                    </div>
                  </div>

                  {/* Reverb Send */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[#777777] w-6">Rev</span>
                    <input
                      type="range" min={0} max={1} step={0.05}
                      value={mt.reverbSend}
                      onChange={(e) => updateTrack(mt.trackId, { reverbSend: Number(e.target.value) })}
                      className="flex-1 h-1 accent-[#f96bee]"
                    />
                    <span className="text-[10px] font-mono text-[#f96bee] w-8 text-right">
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
