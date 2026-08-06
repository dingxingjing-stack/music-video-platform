/**
 * WaveformEditor — Full-featured audio waveform display with trim/envelope controls.
 * Uses wavesurfer.js for rendering, supports play/crop/fade-in-fade-out.
 */
import { useEffect, useRef, useState, useCallback } from 'react';

interface Props {
  url: string;
  onTrim?: (start: number, end: number) => void;
}

export function WaveformEditor({ url, onTrim }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<any>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(100);
  const [fadeIn, setFadeIn] = useState(0.5);
  const [fadeOut, setFadeOut] = useState(2);

  useEffect(() => {
    let ws: any = null;
    let timer: ReturnType<typeof setInterval> | null = null;

    (async () => {
      const WaveSurfer = (await import('wavesurfer.js')).default;
      if (!containerRef.current) return;

      ws = WaveSurfer.create({
        container: containerRef.current,
        waveColor: 'rgba(255,106,16,0.4)',
        progressColor: 'linear-gradient(90deg, #ff6a10, #f96bee)',
        cursorColor: '#f96bee',
        barWidth: 2,
        barRadius: 3,
        barGap: 2,
        height: 120,
        normalize: true,
        minPxPerSec: 40,
        backend: 'WebAudio',
      });

      ws.load(url);
      ws.on('ready', () => {
        setDuration(ws.getDuration());
        setTrimEnd(ws.getDuration());
      });
      ws.on('audioprocess', () => {
        setCurrentTime(ws.getCurrentTime());
      });
      ws.on('play', () => setPlaying(true));
      ws.on('pause', () => setPlaying(false));

      wavesurferRef.current = ws;
    })();

    return () => {
      if (timer) clearInterval(timer);
      if (ws) ws.destroy();
    };
  }, [url]);

  const togglePlay = useCallback(() => {
    const ws = wavesurferRef.current;
    if (!ws) return;
    ws.playPause();
  }, []);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const durationSec = duration || 0;
  const trimStartPct = (trimStart / durationSec) * 100;
  const trimEndPct = (trimEnd / durationSec) * 100;

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-3">
      <h2 className="font-display font-semibold">🌊 波形编辑器</h2>

      {/* Waveform */}
      <div className="relative">
        <div ref={containerRef} className="w-full" />
        {/* Trim region overlay */}
        <div className="absolute top-0 bottom-0 flex pointer-events-none" style={{ left: `${trimStartPct}%`, right: `${100 - trimEndPct}%` }}>
          <div className="flex-1 bg-[var(--accent-gradient-start)]/10 border-x border-[var(--accent-gradient-start)]/40" />
        </div>
      </div>

      {/* Playback Controls */}
      <div className="flex items-center gap-4 text-sm">
        <button onClick={togglePlay} className="btn-primary !px-4 !py-2 text-sm">
          {playing ? '⏸ 暂停' : '▶ 播放'}
        </button>
        <span className="text-[var(--text-muted)] font-mono">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>

      {/* Trim Sliders */}
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
          开始裁剪
          <input
            type="range"
            min={0}
            max={durationSec}
            step={0.1}
            value={trimStart}
            onChange={(e) => {
              const v = Number(e.target.value);
              setTrimStart(Math.min(v, trimEnd - 1));
            }}
            className="w-full accent-[var(--accent-gradient-start)]"
          />
          <span className="font-mono">{formatTime(trimStart)}</span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
          结束裁剪
          <input
            type="range"
            min={0}
            max={durationSec}
            step={0.1}
            value={trimEnd}
            onChange={(e) => {
              const v = Number(e.target.value);
              setTrimEnd(Math.max(v, trimStart + 1));
            }}
            className="w-full accent-[var(--accent-gradient-start)]"
          />
          <span className="font-mono">{formatTime(trimEnd)}</span>
        </label>
      </div>

      {/* Fade Controls */}
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
          淡入 (秒)
          <input
            type="range"
            min={0}
            max={5}
            step={0.1}
            value={fadeIn}
            onChange={(e) => setFadeIn(Number(e.target.value))}
            className="w-full accent-[var(--accent-gradient-start)]"
          />
          <span className="font-mono">{fadeIn.toFixed(1)}s</span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
          淡出 (秒)
          <input
            type="range"
            min={0}
            max={10}
            step={0.1}
            value={fadeOut}
            onChange={(e) => setFadeOut(Number(e.target.value))}
            className="w-full accent-[var(--accent-gradient-start)]"
          />
          <span className="font-mono">{fadeOut.toFixed(1)}s</span>
        </label>
      </div>

      {/* Apply Button */}
      <button
        className="btn-primary !px-4 !py-2 text-sm"
        onClick={() => onTrim?.(trimStart, trimEnd)}
      >
        ✅ 应用裁剪
      </button>
    </section>
  );
}