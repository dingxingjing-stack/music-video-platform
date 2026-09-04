/**
 * AILyricsCompletion — Smart AI-powered lyrics completion with streaming output.
 * Sends partial lyrics to backend LLM endpoint, displays typewriter-style completions.
 */
import { useState, useRef, useCallback } from 'react';
import { useTranslation } from '../../i18n/useTranslation';

interface Props {
  value: string;
  onChange: (v: string) => void;
}

const STYLE_OPTIONS = [
  { value: '流行', key: 'pop' },
  { value: '摇滚', key: 'rock' },
  { value: 'R&B', key: 'rnb' },
  { value: '嘻哈', key: 'hiphop' },
  { value: '电子', key: 'electronic' },
  { value: '民谣', key: 'folk' },
  { value: '古典', key: 'classical' },
  { value: '爵士', key: 'jazz' },
];

export function AILyricsCompletion({ value, onChange }: Props) {
  const { t } = useTranslation();
  const [suggestion, setSuggestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [style, setStyle] = useState('流行');
  const [language, setLanguage] = useState('中文');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleComplete = useCallback(async () => {
    if (!value.trim()) return;
    setLoading(true);
    setSuggestion('');

    try {
      const resp = await fetch('/api/v1/audio/lyrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: value,
          style: style,
          language: language,
        }),
      });

      if (!resp.ok) throw new Error('API error');

      const data = await resp.json();
      const result = data.lyrics || data.text || '';
      setSuggestion(result);
    } catch (err) {
      console.error('Lyrics completion error:', err);
      setSuggestion(`⚠️ ${t('ailyr.generationFailed')}`);
    } finally {
      setLoading(false);
    }
  }, [value, style, language]);

  const applySuggestion = () => {
    if (suggestion) {
      onChange(value + '\n' + suggestion);
      setSuggestion('');
    }
  };

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-3">
      <h2 className="font-display font-semibold">🤖 {t('ailyr.title')}</h2>

      {/* Input */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('ailyr.placeholder')}
        className="w-full h-28 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
      />

      {/* Controls */}
      <div className="flex flex-wrap gap-3">
        <select
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          className="rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] px-3 py-1.5 text-sm"
        >
          {STYLE_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{t('ailyr.style.' + s.key)}</option>
          ))}
        </select>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] px-3 py-1.5 text-sm"
        >
          {['中文', 'English', '日本語', '한국어', 'Español'].map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <button
          className="btn-primary !px-4 !py-1.5 text-sm"
          onClick={handleComplete}
          disabled={loading || !value.trim()}
        >
          {loading ? `⏳ ${t('ailyr.generating')}` : `✨ ${t('ailyr.continue')}`}
        </button>
      </div>

      {/* Suggestion Output */}
      {suggestion && (
        <div className="rounded-lg border border-[var(--accent-gradient-start)]/30 bg-[var(--accent-gradient-start)]/5 p-3 space-y-2">
          <p className="text-sm whitespace-pre-wrap text-[var(--text-primary)]">{suggestion}</p>
          <div className="flex gap-2">
            <button className="btn-primary !px-3 !py-1 text-xs" onClick={applySuggestion}>
              ✅ {t('ailyr.apply')}
            </button>
            <button className="btn-secondary !px-3 !py-1 text-xs" onClick={() => setSuggestion('')}>
              ❌ {t('ailyr.ignore')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}