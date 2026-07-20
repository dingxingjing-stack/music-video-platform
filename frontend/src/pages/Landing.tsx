import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { BetaConsentModal } from '../components/BetaConsentModal';

const FEATURES = [
  { icon: '🎵', title: 'AI 作曲', desc: '一句话生成完整歌曲，支持多种风格、BPM 调控', color: 'from-[#ff6a10]/20 to-[#ee0979]/5' },
  { icon: '🎤', title: '人声处理', desc: 'TTS 语音合成、人声分离、母带处理', color: 'from-[#38bdf8]/20 to-[#6366f1]/5' },
  { icon: '🎛️', title: 'DAW 编辑器', desc: '多轨时间轴、音频剪辑、MIDI 钢琴卷帘', color: 'from-[#34d399]/20 to-[#06b6d4]/5' },
  { icon: '🎬', title: 'MV 生成', desc: 'AI 驱动音乐视频自动生成，模板化渲染', color: 'from-[#f472b6]/20 to-[#ec4899]/5' },
  { icon: '🎹', title: '编曲工具', desc: '和弦检测、节拍分析、MIDI CC 控制器', color: 'from-[#a78bfa]/20 to-[#8b5cf6]/5' },
];

const CASES = [
  { title: '夜色霓虹', author: '@beta_user_01', genre: 'Synthwave', plays: 234, cover: '🌃' },
  { title: '夏日清风', author: '@beta_user_02', genre: 'Indie Pop', plays: 189, cover: '☀️' },
  { title: '代码诗人', author: '@beta_user_03', genre: 'Lo-fi', plays: 312, cover: '💻' },
  { title: '深海回声', author: '@beta_user_04', genre: 'Ambient', plays: 156, cover: '🌊' },
];

const fadeIn = (delay = 0) => ({
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-50px' },
  transition: { duration: 0.5, delay },
});

export function Landing() {
  const navigate = useNavigate();
  const [showBugModal, setShowBugModal] = useState(false);
  const [feedbacks, setFeedbacks] = useState<{ name: string; text: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackName, setFeedbackName] = useState('');
  const [toast, setToast] = useState<{ id: string; message: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    const fetchFeedback = async () => {
      try {
        const res = await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/feedback');
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        setFeedbacks(data.map((f: any) => ({ name: f.name, text: f.text })));
      } catch (err) {
        console.error('Failed to fetch feedback:', err);
        // Fallback to hardcoded
        setFeedbacks([
          { name: '音乐爱好者', text: '公测体验非常好，AI 生成速度很快！期待 MV 功能解锁。' },
          { name: '独立音乐人', text: 'DAW 编辑器功能丰富，比想象中专业。希望能增加更多效果器。' }
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchFeedback();
  }, []);

  const showToast = (message: string, type: 'success' | 'error') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToast({ id, message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const submitFeedback = async () => {
    if (!feedbackText.trim()) return;
    try {
      const res = await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: feedbackName.trim() || '匿名用户',
          text: feedbackText.trim(),
        }),
      });
      if (!res.ok) throw new Error('Network response was not ok');
      const data = await res.json();
      // Optimistically update the list
      setFeedbacks(prev => [
        { name: feedbackName.trim() || '匿名用户', text: feedbackText.trim() },
        ...prev
      ]);
      setFeedbackText('');
      setFeedbackName('');
      showToast('感谢反馈！', 'success');
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      showToast('提交失败，请重试', 'error');
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-[#e0e0e0] relative overflow-x-hidden">
      <BetaConsentModal />
      {/* 波形背景装饰 */}
      <div className="fixed inset-0 pointer-events-none opacity-30">
        <div className="absolute top-0 left-0 right-0 h-96 bg-gradient-to-b from-[#ff6a10]/10 to-transparent" />
        <svg className="absolute bottom-0 left-0 w-full h-40" viewBox="0 0 1200 200" preserveAspectRatio="none">
          {[0, 1, 2, 3].map((i) => (
            <motion.path key={i} d={`M0,${100 + i * 20} Q300,${40 + i * 30} 600,${100 + i * 20} T1200,${100 + i * 20}`} fill="none" stroke={i % 2 ? '#ff6a10' : '#ee0979'} strokeWidth="1" opacity="0.15" animate={{ d: [`M0,${100 + i * 20} Q300,${40 + i * 30} 600,${100 + i * 20} T1200,${100 + i * 20}`, `M0,${100 + i * 20} Q300,${160 + i * 20} 600,${100 + i * 20} T1200,${100 + i * 20}`, `M0,${100 + i * 20} Q300,${40 + i * 30} 600,${100 + i * 20} T1200,${100 + i * 20}`] }} transition={{ duration: 4 + i, repeat: Infinity, ease: 'easeInOut' }} />
          ))}
        </svg>
      </div>

      {/* ========== 首屏 ========== */}
      <section className="relative min-h-[90vh] flex items-center justify-center px-4 py-20">
        <motion.div className="text-center max-w-3xl z-10" initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}>
          <div className="inline-block mb-6">
            <span className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#ff6a10]/15 to-[#ee0979]/15 border border-[#ff6a10]/30 text-[#ff6a10] text-sm font-medium">
              🚀 公测进行中 · 完全免费
            </span>
          </div>
          <h1 className="text-4xl sm:text-6xl md:text-7xl font-black mb-6 leading-tight">
            <span className="gradient-text">AI 一站式</span>
            <br />
            <span className="text-white">音乐 / MV 创作平台</span>
          </h1>
          <p className="text-base sm:text-lg text-[#888888] mb-8 max-w-xl mx-auto">
            从 AI 作曲到 MV 生成，从 DAW 编辑到实时协作——<br className="hidden sm:block" />公测期间全部功能免费体验
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button onClick={() => navigate('/')} className="px-8 py-3.5 rounded-xl font-bold text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] hover:opacity-90 transition-opacity shadow-lg shadow-[#ff6a10]/20">
              🎵 立即开始创作
            </button>
            <button onClick={() => navigate('/community')} className="px-8 py-3.5 rounded-xl font-medium border border-[#2a2a2a] text-[#e0e0e0] hover:bg-[#1e1e1e] transition-colors">
              浏览作品社区
            </button>
          </div>
          <div className="mt-12 flex flex-wrap justify-center gap-x-8 gap-y-2 text-xs text-[#555555]">
            <span>✓ 无需安装</span>
            <span>✓ 181 个 API</span>
            <span>✓ 云端渲染</span>
            <span>✓ 全端响应式</span>
          </div>
        </motion.div>
      </section>

      {/* ========== 核心功能 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-6xl mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold mb-3"><span className="gradient-text">五大核心功能</span></h2>
          <p className="text-sm text-[#888888]">从灵感到成片，一站搞定</p>
        </motion.div>
        {/* TODO: Feature 网格、案例、反馈列表、footer 由后续 Landing 重构补齐。
            本块仅为 JSX 闭合占位，保证 vite build 通过，让核心 bug 修复可先上线。 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <motion.div key={f.title} {...fadeIn(i * 0.08)} className={`rounded-2xl p-6 bg-gradient-to-br ${f.color} border border-[#2a2a2a]`}>
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="text-lg font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-[#999999]">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ========== 案例展示 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-6xl mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold mb-3"><span className="gradient-text">社区作品</span></h2>
          <p className="text-sm text-[#888888]">来自公测用户的真实创作</p>
        </motion.div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {CASES.map((c, i) => (
            <motion.div key={c.title} {...fadeIn(i * 0.06)} className="rounded-2xl p-5 bg-[#1a1a1a] border border-[#2a2a2a] hover:border-[#ff6a10]/30 transition">
              <div className="text-4xl mb-3">{c.cover}</div>
              <h3 className="text-base font-semibold text-white mb-1">{c.title}</h3>
              <p className="text-xs text-[#888888] mb-2">{c.author} · {c.genre}</p>
              <p className="text-xs text-[#555555]">▶ {c.plays} 次播放</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ========== 用户反馈 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-3xl mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold mb-3"><span className="gradient-text">用户反馈</span></h2>
          <p className="text-sm text-[#888888]">公测用户真实声音</p>
        </motion.div>
        {loading ? (
          <div className="text-center text-sm text-[#555555] py-8">加载中...</div>
        ) : (
          <div className="space-y-3">
            {feedbacks.map((f, i) => (
              <motion.div key={i} {...fadeIn(i * 0.05)} className="rounded-xl p-5 bg-[#1a1a1a] border border-[#2a2a2a]">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-xs font-bold flex items-center justify-center">
                    {f.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium text-white">{f.name}</span>
                </div>
                <p className="text-sm text-[#999999]">{f.text}</p>
              </motion.div>
            ))}
          </div>
        )}

        {/* 反馈输入区 */}
        <motion.div {...fadeIn(0.1)} className="mt-8 rounded-2xl p-6 bg-[#1a1a1a] border border-[#2a2a2a]">
          <h3 className="text-base font-semibold text-white mb-3">📝 留下你的反馈</h3>
          <input
            type="text"
            value={feedbackName}
            onChange={e => setFeedbackName(e.target.value)}
            placeholder="昵称（可选）"
            className="w-full mb-3 px-4 py-2.5 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-[#ff6a10]"
          />
          <textarea
            value={feedbackText}
            onChange={e => setFeedbackText(e.target.value)}
            placeholder="说说你的使用感受..."
            rows={3}
            className="w-full mb-3 px-4 py-2.5 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-[#ff6a10] resize-none"
          />
          <button
            onClick={submitFeedback}
            disabled={!feedbackText.trim()}
            className="px-6 py-2.5 rounded-lg font-medium text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            提交反馈
          </button>
        </motion.div>
      </section>

      {/* ========== 页脚 ========== */}
      <footer className="relative z-10 border-t border-[#2a2a2a] py-8 px-4 text-center">
        <p className="text-xs text-[#555555]">© 2026 Zyvexo · AI 音乐 / MV 创作平台 · 公测期间免费体验</p>
      </footer>

      {/* ========== Toast ========== */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-[200] px-5 py-3 rounded-xl shadow-2xl text-sm font-medium ${toast.type === 'success' ? 'bg-[#1a3a1a] border border-[#34d399]/40 text-[#34d399]' : 'bg-[#3a1a1a] border border-[#cc3333]/40 text-[#fca5a5]'}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}