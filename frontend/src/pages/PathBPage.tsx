import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WaveformEditor } from '../components/Audio/WaveformEditor';
import { AILyricsCompletion } from '../components/Audio/AILyricsCompletion';
import { MixConsole } from '../components/TrackStudio/MixConsole';
import { StemExporter } from '../components/Audio/StemExporter';
import { useTranslation } from '../i18n/useTranslation';
import { ComingSoonModal } from '../hooks/useAudioGeneration';

export function PathBPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [audioUrl, _setAudioUrl] = useState<string | null>(null);
  const [lyrics, setLyrics] = useState('');
  const [showComingSoon, setShowComingSoon] = useState(false);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/')} className="text-sm text-[var(--text-secondary)] hover:text-white transition">&larr; {t('common.back') || '返回'}</button>
        <h1 className="text-2xl font-display font-bold gradient-text">路径 B — 混合模式</h1>
      </div>
      <p className="text-sm text-[var(--text-muted)]">音频 + 歌词 + 风格参考 → 混合生成</p>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
        <h2 className="font-display font-semibold">🎛️ 混合输入</h2>
        <div className="grid md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-[var(--text-secondary)]">上传参考音频</label>
            <div className="border-2 border-dashed border-[var(--border)] rounded-lg p-6 text-center text-sm text-[var(--text-muted)] cursor-pointer hover:border-[var(--accent-gradient-start)] transition">
              🎵 点击上传音频文件（MP3/WAV）
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-xs text-[var(--text-secondary)]">风格提示词</label>
            <textarea className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]" placeholder="描述混合后的风格方向..." />
          </div>
        </div>
        <button onClick={() => setShowComingSoon(true)} className="btn-primary">🎛️ 开始混合生成</button>
      </section>

      {audioUrl && <WaveformEditor url={audioUrl} />}
      <AILyricsCompletion value={lyrics} onChange={setLyrics} />
      <MixConsole history={[]} />
      {audioUrl && <StemExporter audioUrl={audioUrl} />}

      {showComingSoon && <ComingSoonModal onClose={() => setShowComingSoon(false)} />}
    </div>
  );
}
