/**
 * StemExporter — Export individual audio stems (vocals, drums, bass, etc.) as ZIP.
 * Uses backend API to split audio and package stems.
 */
import { useState } from 'react';

interface Props {
  audioUrl: string;
  trackName?: string;
}

export function StemExporter({ audioUrl, trackName }: Props) {
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    setProgress(0);
    setDone(false);

    try {
      const resp = await fetch('/api/v1/audio/stems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_url: audioUrl, track_name: trackName || 'track' }),
      });

      if (!resp.ok) throw new Error('Export failed');

      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${trackName || 'track'}_stems.zip`;
      a.click();
      URL.revokeObjectURL(url);

      setProgress(100);
      setDone(true);
    } catch (err) {
      console.error('Stem export error:', err);
      alert('⚠️ 分轨导出失败，请重试');
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-3">
      <h2 className="font-display font-semibold">📦 分轨导出 (Stems)</h2>
      <p className="text-xs text-[var(--text-muted)]">
        将音频拆分为人声、鼓、贝斯、旋律等独立音轨，打包为 ZIP 下载。
        <span className="text-[var(--accent-pink)] ml-1">Suno 不支持此功能。</span>
      </p>

      {/* Progress Bar */}
      {exporting && (
        <div className="w-full h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{
              width: `${exporting ? (progress > 0 ? progress : 30) : done ? 100 : 0}%`,
              background: 'linear-gradient(90deg, var(--accent-gradient-start), var(--accent-gradient-end))',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
      )}

      <button
        className="btn-primary !px-4 !py-2 text-sm"
        onClick={handleExport}
        disabled={exporting}
      >
        {exporting ? '⏳ 正在拆分导出...' : done ? '✅ 已下载' : '⬇ 导出 Stem ZIP'}
      </button>

      {done && (
        <p className="text-xs text-[var(--accent-green)]">✅ 导出成功！ZIP 包含：人声、鼓组、贝斯、旋律、和声等音轨。</p>
      )}
    </section>
  );
}