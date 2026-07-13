/**
 * AILyricsCompletion — Smart AI-powered lyrics completion with streaming output.
 * Sends partial lyrics to backend LLM endpoint, displays typewriter-style completions.
 */
import { useState, useRef, useCallback } from 'react';

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export function AILyricsCompletion({ value, onChange }: Props) {
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
      setSuggestion('⚠️ 生成失败，请重试');
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
      <h2 className="font-display font-semibold">🤖 AI 歌词智能补全</h2>

      {/* Input */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="输入你已经写好的歌词片段，AI 会自动续写..."
        className="w-full h-28 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
      />

      {/* Controls */}
      <div className="flex flex-wrap gap-3">
        <select
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          className="rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] px-3 py-1.5 text-sm"
        >
          {['流行', '摇滚', 'R&B', '嘻哈', '电子', '民谣', '古典', '爵士'].map((s) => (
            <option key={s} value={s}>{s}</option>
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
          {loading ? '⏳ 生成中...' : '✨ AI 续写'}
        </button>
      </div>

      {/* Suggestion Output */}
      {suggestion && (
        <div className="rounded-lg border border-[var(--accent-gradient-start)]/30 bg-[var(--accent-gradient-start)]/5 p-3 space-y-2">
          <p className="text-sm whitespace-pre-wrap text-[var(--text-primary)]">{suggestion}</p>
          <div className="flex gap-2">
            <button className="btn-primary !px-3 !py-1 text-xs" onClick={applySuggestion}>
              ✅ 应用
            </button>
            <button className="btn-secondary !px-3 !py-1 text-xs" onClick={() => setSuggestion('')}>
              ❌ 忽略
            </button>
          </div>
        </div>
      )}
    </section>
  );
}