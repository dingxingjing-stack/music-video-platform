/**
 * MiniWaveform — Synthetic waveform preview drawn on a <canvas>.
 *
 * Draws a placeholder waveform pattern (no actual audio analysis).
 * Re-draws whenever `url` changes.
 */

import { useRef, useEffect } from 'react';

export function MiniWaveform({ url, className = '' }: { url: string; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, w, h);

    // Generate synthetic waveform bars
    const barCount = 40;
    const barWidth = 2;
    const gap = (w - barCount * barWidth) / (barCount - 1);
    ctx.fillStyle = '#6366f1';

    for (let i = 0; i < barCount; i++) {
      const x = i * (barWidth + gap);
      const amp = Math.sin(i * 0.3) * 0.3 + Math.sin(i * 0.7) * 0.2 + Math.random() * 0.5;
      const barH = Math.max(4, Math.abs(amp) * h * 0.8);
      const y = (h - barH) / 2;
      ctx.globalAlpha = 0.4 + Math.abs(amp) * 0.6;
      ctx.fillRect(x, y, barWidth, barH);
    }
    ctx.globalAlpha = 1;
  }, [url]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={40}
      className={`rounded ${className}`}
      style={{ imageRendering: 'pixelated' }}
    />
  );
}
