import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WaveformEditor } from '../components/Audio/WaveformEditor';
import { AILyricsCompletion } from '../components/Audio/AILyricsCompletion';
import { MixConsole } from '../components/TrackStudio/MixConsole';
import { StemExporter } from '../components/Audio/StemExporter';
import { useTranslation } from '../i18n/useTranslation';

export function PathAPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [audioUrl, _setAudioUrl] = useState<string | null>(null);
  const [lyrics, setLyrics] = useState('');

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/')} className="text-sm text-[var(--text-secondary)] hover:text-white transition">&larr; {t('common.back') || '返回'}</button>
        <h1 className="text-2xl font-display font-bold gradient-text">路径 A — Suno 风格</h1>
      </div>
      <p className="text-sm text-[var(--text-muted)]">提示词 → MusicGen → 全曲生成</p>

      {/* Input Area */}
      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
        <h2 className="font-display font-semibold">🎤 音乐提示词</h2>
        <textarea
          className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
          placeholder="输入提示词描述想要的音乐风格、情感、乐器..."
        />
        <div className="flex gap-3">
          <button className="btn-primary">✨ 🎵 生成音乐</button>
          <button className="btn-secondary">🔀 随机提示</button>
        </div>
      </section>

      {/* Waveform Editor */}
      {audioUrl && (
        <WaveformEditor url={audioUrl} />
      )}

      {/* AI Lyrics Completion */}
      <AILyricsCompletion value={lyrics} onChange={setLyrics} />

      {/* Mix Console */}
      <MixConsole history={[]} />

      {/* Stem Export */}
      {audioUrl && <StemExporter audioUrl={audioUrl} />}

      {/* Version History */}
      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
        <h2 className="font-display font-semibold mb-3">📋 版本历史</h2>
        <p className="text-sm text-[var(--text-muted)]">暂无历史记录。生成的音乐会自动保存到这里。</p>
      </section>
    </div>
  );
}