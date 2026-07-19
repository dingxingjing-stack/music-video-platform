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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-