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
        <h1 className="text-2xl font-display font-bold gradient-text">{t('paths.pathB')}</h1>
      </div>
      <p className="text-sm text-[var(--text-muted)]">{t('pathB.subtitle')}</p>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
        <h2 className="font-display font-semibold">{t('pathB.hybridInput')}</h2>
        <div className="grid md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-[var(--text-secondary)]">{t('pathB.uploadReference')}</label>
            <div className="border-2 border-dashed border-[var(--border)] rounded-lg p-6 text-center text-sm text-[var(--text-muted)] cursor-pointer hover:border-[var(--accent-gradient-start)] transition">
              {t('pathB.clickUploadAudio')}
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-xs text-[var(--text-secondary)]">{t('pathB.stylePrompt')}</label>
            <textarea className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]" placeholder={t('pathB.placeholder')} />
          </div>
        </div>
        <button onClick={() => setShowComingSoon(true)} className="btn-primary">{t('pathB.startMix')}</button>
      </section>

      {audioUrl && <WaveformEditor url={audioUrl} />}
      <AILyricsCompletion value={lyrics} onChange={setLyrics} />
      <MixConsole history={[]} />

      {showComingSoon && <ComingSoonModal onClose={() => setShowComingSoon(false)} />}
    </div>
  );
}
