import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WaveformEditor } from '../components/Audio/WaveformEditor';
import { AILyricsCompletion } from '../components/Audio/AILyricsCompletion';
import { MixConsole } from '../components/TrackStudio/MixConsole';
import { StemExporter } from '../components/Audio/StemExporter';
import { useTranslation } from '../i18n/useTranslation';
import { useAudioGeneration, RateLimitBanner } from '../hooks/useAudioGeneration';

export function PathAPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState('');
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [lyrics, setLyrics] = useState('');

  const { loading, generate, rateLimited, setRateLimited } = useAudioGeneration({ onSuccess: setAudioUrl });

  const handleGenerate = () => {
    if (!prompt.trim()) return;
    generate('/ai/generate', { prompt: prompt.trim(), style: 'pop' });
  };

  const handleRandom = () => {
    const prompts = t('pathA.randomPrompts', { returnObjects: true }) as string[];
    setPrompt(prompts[Math.floor(Math.random() * prompts.length)]);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/')} className="text-sm text-[var(--text-secondary)] hover:text-white transition">&larr; {t('common.back') || '返回'}</button>
        <h1 className="text-2xl font-display font-bold gradient-text">{t('pathA.title')}</h1>
      </div>
      <p className="text-sm text-[var(--text-muted)]">{t('pathA.tagline')}</p>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
        <h2 className="font-display font-semibold">🎤 {t('ui.musicPrompt')}</h2>
        <textarea
          className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
          placeholder={t('ui.promptPlaceholder')}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
        />
        <div className="flex gap-3 items-center">
          <button
            onClick={handleGenerate}
            disabled={loading || !prompt.trim()}
            title={!prompt.trim() ? t('pathA.tooltipNeedPrompt') : loading ? t('pathA.tooltipGenerating') : t('pathA.tooltipGenerate')}
            className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? <><span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" /> {t('pathA.generating')}</> : t('ui.generateMusic')}
          </button>
          <button onClick={handleRandom} className="btn-secondary">{t('ui.randomPrompt')}</button>
          {!prompt.trim() && !loading && (
            <span className="text-xs text-[var(--text-muted)]">{t('ui.promptHint')}</span>
          )}
        </div>
      </section>

      {audioUrl && <WaveformEditor url={audioUrl} />}
      <AILyricsCompletion value={lyrics} onChange={setLyrics} />
      <MixConsole history={[]} />

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
        <h2 className="font-display font-semibold mb-3">{t('ui.versionHistory')}</h2>
        <p className="text-sm text-[var(--text-muted)]">{t('ui.historyEmpty')}</p>
      </section>

      {rateLimited && <RateLimitBanner onDismiss={() => setRateLimited(false)} />}
    </div>
  );
}
