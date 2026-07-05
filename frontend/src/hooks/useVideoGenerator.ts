import { useState, useCallback, useEffect } from 'react';
import { useWebSocketProgress } from './useWebSocketProgress';
import type { BeatDetectionResult, MVConfig, VideoRenderJob } from '../types/trackStudio';

export function useVideoGenerator() {
  // Beat detection state
  const [beatData, setBeatData] = useState<BeatDetectionResult | null>(null);
  const [detectingBeats, setDetectingBeats] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);

  // Render state
  const [renderJob, setRenderJob] = useState<VideoRenderJob | null>(null);
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  // WebSocket progress hook for render
  const {
    progress: wsProgress,
    message: wsMessage,
    resultUrl: wsResultUrl,
    error: wsError,
    connected: wsConnected,
  } = useWebSocketProgress(renderJob?.jobId || null);

  // Detect beats
  const detectBeats = useCallback(async (trackId: string, audioUrl: string) => {
    setDetectingBeats(true);
    setDetectError(null);
    try {
      const resp = await fetch('/api/v1/mv/detect-beats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: trackId, url: audioUrl }),
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
  }, []);

  const clearBeatData = useCallback(() => {
    setBeatData(null);
    setDetectError(null);
  }, []);

  // Start video render
  const renderVideo = useCallback(async (trackId: string, audioUrl: string, beatResult: BeatDetectionResult, config: MVConfig) => {
    setRendering(true);
    setRenderError(null);
    try {
      const resp = await fetch('/api/v1/mv/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_track_id: trackId,
          audio_url: audioUrl,
          beat_data: beatResult,
          config,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setRenderJob({
        jobId: data.task_id,
        sourceTrackId: trackId,
        beatResult,
        config,
        status: 'queued',
        progress: 0,
      });
    } catch (err) {
      console.error('MV render failed:', err);
      setRenderError('MV render failed');
      setRendering(false);
    }
  }, []);

  // Sync render job state from WebSocket
  useEffect(() => {
    if (!renderJob) return;
    if (wsProgress !== undefined) {
      setRenderJob(prev => prev ? { ...prev, progress: wsProgress } : null);
    }
    if (wsResultUrl) {
      setRenderJob(prev => prev ? { ...prev, status: 'completed', progress: 100 } : null);
      setRendering(false);
    }
    if (wsError) {
      setRenderJob(prev => prev ? { ...prev, status: 'failed' } : null);
      setRenderError(wsError);
      setRendering(false);
    }
  }, [renderJob, wsProgress, wsMessage, wsResultUrl, wsError]);

  const clearRenderJob = useCallback(() => {
    setRenderJob(null);
    setRendering(false);
    setRenderError(null);
  }, []);

  return {
    // Beat detection
    beatData,
    detectingBeats,
    detectError,
    detectBeats,
    clearBeatData,
    // Render
    renderJob,
    rendering,
    renderError,
    renderVideo,
    clearRenderJob,
    // WebSocket
    wsProgress,
    wsMessage,
    wsResultUrl,
    wsError,
    wsConnected,
  };
}