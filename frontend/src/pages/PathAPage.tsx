import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WaveformEditor } from '../components/Audio/WaveformEditor';
import { AILyricsCompletion } from '../components/Audio/AILyricsCompletion';
import { MixConsole } from '../components/TrackStudio/MixConsole';
import { StemExporter } from '../components/Audio/StemExporter';
import { useTranslation } from '../i18n/useTranslation';
import { useAudioGeneration, RateLimitBanner } from '../hooks/useAudioGeneration';

const RANDOM_PROMPTS = [
  '一首轻快的流行歌曲，钢琴伴奏，温暖治愈',
  '史诗管弦乐，电影配乐风格，宏大震撼',
  'Lo-fi 嘻哈节奏，放松舒缓，适合学习',
  '电子舞曲，强劲节拍，夜店氛围',
  '古典吉他独奏，西班牙风格，浪漫优雅',
];

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
    setPrompt(RANDOM_PROMPTS[Math.floor(Math.random() * RANDOM_PROMPTS.length)]);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/')} className="text-sm text-[var(--text-secondary)] hover:text-white transition">&larr; {t('common.back') || '返回'}</button>
        <h1 className="text-2xl font-display font-bold gradient-text">路径 A — Suno 风格</h1>
      </div>
      <p className="text-sm text-[var(--text-muted)]">提示词 → Agnes AI → 全曲生成（免费）</p>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
        <h2 className="font-display font-semibold">🎤 音乐提示词</h2>
        <textarea
          className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
          placeholder="输入提示词描述想要的音乐风格、情感、乐器..."
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
        />
        <div className="flex gap-3">
          <button
            onClick={handleGenerate}
            disabled={loading || !prompt.trim()}
            className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? <><span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" /> 生成中...</> : '✨ 🎵 生成音乐'}
          </button>
          <button onClick={handleRandom} className="btn-secondary">🔀 随机提示</button>
        </div>
      </section>

      {audioUrl && <WaveformEditor url={audioUrl} />}
      <AILyricsCompletion value={lyrics} onChange={setLyrics} />
      <MixConsole history={[]} />
      {audioUrl && <StemExporter audioUrl={audioUrl} />}

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
        <h2 className="font-display font-semibold mb-3">📋 版本历史</h2>
        <p className="text-sm text-[var(--text-muted)]">暂无历史记录。生成的音乐会自动保存到这里。</p>
      </section>

      {rateLimited && <RateLimitBanner onDismiss={() => setRateLimited(false)} />}
    </div>
  );
}
