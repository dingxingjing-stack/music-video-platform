/**
 * MVGenerator — Music Video generator with beat detection and video rendering.
 *
 * Features:
 *   - Select a track from history
 *   - Detect BPM and beat timestamps
 *   - Configure video settings (resolution, aspect ratio, transitions, etc.)
 *   - Real-time rendering progress via WebSocket
 *   - Preview and download final MV
 */

import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '../../i18n';
import type { Track, BeatDetectionResult, MVConfig, VideoRenderJob } from '../../types/trackStudio';
import { useWebSocketProgress } from '../../hooks/useWebSocketProgress';

const RESOLUTIONS = ['720p', '1080p', '4K'] as const;
const ASPECT_RATIOS = ['16:9', '9:16', '1:1'] as const;
const TRANSITION_STYLES = ['cut', 'fade', 'zoom', 'pan'] as const;

interface Props {
  history: Track[];
  onTrackSelect: (track: Track) => void;
}

export function MVGenerator({ history, onTrackSelect }: Props) {
  const { t } = useTranslation();
  const completedTracks = history.filter(t => t.status === 'completed' && t.url);

  // Track selection
  const [selectedTrack, setSelectedTrack] = useState<Track | null>(null);
  // Beat detection
  const [beatData, setBeatData] = useState<BeatDetectionResult | null>(null);
  const [detectingBeats, setDetectingBeats] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);
  // Video config
  const [config, setConfig] = useState<MVConfig>({
    resolution: '1080p',
    aspectRatio: '16:9',
    transitionStyle: 'cut',
    backgroundColor: '#1a1a2e',
    waveformVisualization: true,
  });
  // Render state
  const [renderJob, setRenderJob] = useState<VideoRenderJob | null>(null);
  const [rendering, setRendering] = useState(false);

  // WebSocket progress hook for render
  const { progress: wsProgress, message: wsMessage, resultUrl: wsResultUrl, error: wsError, connected: wsConnected } = useWebSocketProgress(renderJob?.jobId || null);

  // Track selection handler
  const handleTrackSelect = useCallback((track: Track) => {
    setSelectedTrack(track);
    setBeatData(null);
    setDetectError(null);
    onTrackSelect(track);
  }, [onTrackSelect]);

  // Detect beats
  const handleDetectBeats = useCallback(async () => {
    if (!selectedTrack?.url) return;
    setDetectingBeats(true);
    setDetectError(null);
    try {
      const resp = await fetch('/api/v1/mv/detect-beats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: selectedTrack.id, url: selectedTrack.url }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setBeatData({
        bpm: data.bpm,
        beatTimestamps: data.beat_timestamps,
        energyProfile: data.energy_profile,
      });
    } catch (err) {
      console.error('Beat detection failed:', err);
      setDetectError('Beat detection failed');
    } finally {
      setDetectingBeats(false);
    }
  }, [selectedTrack]);

  // Start video render
  const handleRenderVideo = useCallback(async () => {
    if (!selectedTrack?.url || !beatData) return;
    setRendering(true);
    try {
      const resp = await fetch('/api/v1/mv/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_track_id: selectedTrack.id,
          audio_url: selectedTrack.url,
          beat_data: beatData,
          config,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setRenderJob({
        jobId: data.task_id,
        sourceTrackId: selectedTrack.id,
        beatResult: beatData,
        config,
        status: 'queued',
        progress: 0,
      });
    } catch (err) {
      console.error('MV render failed:', err);
      setRendering(false);
    }
  }, [selectedTrack, beatData, config]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // WebSocket cleanup handled by hook
    };
  }, [renderJob]);

  if (completedTracks.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-8 text-center">
        <span className="text-4xl">🎬</span>
        <h3 className="mt-2 text-lg font-medium text-gray-300">{t('ui.mvGenerator')}</h3>
        <p className="mt-1 text-sm text-gray-500">{t('ui.idleStateDesc')}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🎬</span>
          <h2 className="text-lg font-semibold text-gray-300">{t('ui.mvGenerator')}</h2>
        </div>
        {selectedTrack && (
          <span className="text-xs px-2 py-1 bg-blue-900/50 text-blue-400 rounded-full">
            {selectedTrack.name}
          </span>
        )}
      </div>

      {/* Track Selector */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          {t('ui.activeTracks')}
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {completedTracks.map((track) => (
            <button
            onClick={() => handleTrackSelect(track)}
              className={`p-3 rounded-lg border-2 text-left transition-all ${
                selectedTrack?.id === track.id
                  ? 'border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/20'
                  : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'
              }`}
            >
              <p className="text-sm font-medium truncate">{track.name}</p>
              <p className="text-xs text-gray-500 capitalize">{track.type}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Beat Detection */}
      {selectedTrack && (
        <div className="border-t border-gray-800 pt-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-300">{t('ui.detectBeats')}</h3>
          <div className="flex gap-2">
            <button
              onClick={handleDetectBeats}
              disabled={detectingBeats || !!beatData}
              className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-medium rounded-lg hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition-all"
            >
              {detectingBeats ? `⏳ ${t('common.loading')}` : beatData ? `✅ ${t('ui.detectBeats')}` : `🎵 ${t('ui.detectBeats')}`}
            </button>
            <button
              onClick={handleRenderVideo}
              disabled={rendering || !beatData}
              className="px-4 py-2 bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white font-medium rounded-lg hover:from-purple-500 hover:to-fuchsia-500 disabled:opacity-50 transition-all"
            >
              {rendering ? `⏳ ${t('ui.renderVideo')}` : `🎬 ${t('ui.renderVideo')}`}
            </button>
          </div>
          {beatData && (
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-2xl font-bold text-emerald-400">{beatData.bpm.toFixed(1)}</p>
                <p className="text-xs text-gray-500">{t('ui.bpm')}</p>
              </div>
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-2xl font-bold text-blue-400">{beatData.beatTimestamps.length}</p>
                <p className="text-xs text-gray-500">{t('ui.beatCount')}</p>
              </div>
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-2xl font-bold text-purple-400">{(beatData.beatTimestamps[beatData.beatTimestamps.length - 1] || 0).toFixed(1)}s</p>
                <p className="text-xs text-gray-500">{t('ui.elapsedTime')}</p>
              </div>
            </div>
          )}
          {detectError && <p className="text-xs text-red-400">{detectError}</p>}
        </div>
      )}

      {/* Video Config */}
      {selectedTrack && beatData && (
        <div className="border-t border-gray-800 pt-4 space-y-4">
          <h3 className="text-sm font-semibold text-gray-300">{t('common.settings')}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-400">{t('ui.resolution')}</label>
              <select
                value={config.resolution}
                onChange={(e) => setConfig({...config, resolution: e.target.value as any})}
                className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {RESOLUTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">{t('ui.aspectRatio')}</label>
              <select
                value={config.aspectRatio}
                onChange={(e) => setConfig({...config, aspectRatio: e.target.value as any})}
                className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {ASPECT_RATIOS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">{t('ui.transitionStyle')}</label>
              <select
                value={config.transitionStyle}
                onChange={(e) => setConfig({...config, transitionStyle: e.target.value as any})}
                className="w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {TRANSITION_STYLES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">{t('ui.backgroundColor')}</label>
              <input
                type="color"
                value={config.backgroundColor}
                onChange={(e) => setConfig({...config, backgroundColor: e.target.value})}
                className="w-full h-10 mt-1 bg-gray-800 border border-gray-700 rounded-lg cursor-pointer"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 w-full cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.waveformVisualization}
                  onChange={(e) => setConfig({...config, waveformVisualization: e.target.checked})}
                  className="w-4 h-4 accent-emerald-500"
                />
                <span className="text-sm text-gray-300">{t('ui.waveformVisualization')}</span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Render Progress */}
      {renderJob && (
        <div className="border-t border-gray-800 pt-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-300">{t('ui.renderVideo')}</h3>
          <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-fuchsia-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${renderJob.progress}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>{renderJob.status.toUpperCase()}</span>
            <span>{renderJob.progress}%</span>
            <span>{wsConnected ? '● LIVE' : '○ OFFLINE'}</span>
          </div>
          {wsMessage && <p className="text-xs text-gray-500">{wsMessage}</p>}
          {wsError && <p className="text-xs text-red-400">Error: {wsError}</p>}
        </div>
      )}

      {/* Download Result */}
      {wsResultUrl && (
        <div className="border-t border-gray-800 pt-4">
          <audio controls src={wsResultUrl} className="w-full" preload="metadata" />
          <div className="flex gap-2 mt-2">
            <a
              href={wsResultUrl}
              download={`mv_${selectedTrack?.id || 'output'}.mp4`}
              className="flex-1 px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-600 transition-colors text-center"
            >
              {t('ui.downloadFull')}
            </a>
          </div>
        </div>
      )}
    </div>
  );
}