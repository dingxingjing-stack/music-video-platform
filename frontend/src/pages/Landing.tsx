import { useState } from 'react';
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
  const [feedbacks, setFeedbacks] = useState<{ name: string; text: string }[]>([
    { name: '音乐爱好者', text: '公测体验非常好，AI 生成速度很快！期待 MV 功能解锁。' },
    { name: '独立音乐人', text: 'DAW 编辑器功能丰富，比想象中专业。希望能增加更多效果器。' },
  ]);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackName, setFeedbackName] = useState('');

  const submitFeedback = () => {
    if (!feedbackText.trim()) return;
    setFeedbacks([...feedbacks, { name: feedbackName.trim() || '匿名用户', text: feedbackText.trim() }]);
    setFeedbackText('');
    setFeedbackName('');
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <motion.div key={i} {...fadeIn(i * 0.1)} onClick={() => navigate('/')} className={`cursor-pointer rounded-2xl border border-[#2a2a2a] bg-gradient-to-br ${f.color} p-6 hover:border-[#ff6a10]/30 transition-all group`}>
              <span className="text-4xl mb-4 block group-hover:scale-110 transition-transform">{f.icon}</span>
              <h3 className="text-lg font-bold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-[#888888]">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ========== 公测福利 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-4xl mx-auto">
        <motion.div {...fadeIn()} className="rounded-2xl border border-[#2a2a2a] bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] overflow-hidden">
          <div className="px-6 py-5 border-b border-[#2a2a2a] bg-gradient-to-r from-[#ff6a10]/10 to-[#ee0979]/5">
            <h2 className="text-xl font-bold gradient-text">🎁 公测福利</h2>
          </div>
          <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-5 rounded-xl bg-[#121212] border border-[#2a2a2a]">
              <h3 className="font-medium text-white mb-2 flex items-center gap-2"><span>👤</span> 普通用户</h3>
              <ul className="text-sm text-[#888888] space-y-1.5">
                <li>• 每日免费生成 10 次额度</li>
                <li>• 全部基础功能无限制</li>
                <li>• 作品自动带公测水印</li>
                <li>• 社区浏览、点赞、收藏</li>
              </ul>
            </div>
            <div className="p-5 rounded-xl bg-[#121212] border border-[#ff6a10]/20">
              <h3 className="font-medium text-white mb-2 flex items-center gap-2"><span>🏆</span> 资深测试用户</h3>
              <ul className="text-sm text-[#888888] space-y-1.5">
                <li>• 每日免费生成 30 次额度</li>
                <li>• 解锁 MV 生成、协作编辑</li>
                <li>• HF 高级模型、字幕识别</li>
                <li>• 一键多平台发布</li>
                <li className="text-[#ff6a10]">→ 活跃度≥100 且生成≥50 次可申请</li>
              </ul>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ========== 作品案例 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-5xl mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-10">
          <h2 className="text-2xl sm:text-3xl font-bold mb-2"><span className="gradient-text">公测作品展示</span></h2>
          <p className="text-sm text-[#888888]">来自社区的精选作品</p>
        </motion.div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {CASES.map((c, i) => (
            <motion.div key={i} {...fadeIn(i * 0.08)} onClick={() => navigate('/community')} className="cursor-pointer rounded-xl border border-[#2a2a2a] bg-[#1e1e1e] overflow-hidden hover:border-[#ff6a10]/30 transition-all">
              <div className="aspect-square flex items-center justify-center text-5xl bg-gradient-to-br from-[#1a1a1a] to-[#0e0e0e]">{c.cover}</div>
              <div className="p-3">
                <div className="text-sm font-medium text-white truncate">{c.title}</div>
                <div className="text-xs text-[#555555] mt-1">{c.author}</div>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#2a2a2a] text-[#888888]">{c.genre}</span>
                  <span className="text-[10px] text-[#555555]">▶ {c.plays}</span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ========== 用户反馈 ========== */}
      <section className="relative z-10 px-4 py-16 max-w-3xl mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-8">
          <h2 className="text-2xl sm:text-3xl font-bold mb-2"><span className="gradient-text">用户反馈</span></h2>
          <p className="text-sm text-[#888888]">告诉我们你的想法</p>
        </motion.div>
        <div className="space-y-3 mb-6">
          {feedbacks.map((f, i) => (
            <motion.div key={i} {...fadeIn(i * 0.05)} className="p-4 rounded-xl bg-[#1e1e1e] border border-[#2a2a2a]">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#ff6a10] to-[#ee0979] flex items-center justify-center text-xs font-bold text-white flex-shrink-0">{f.name[0]}</div>
                <div>
                  <div className="text-xs font-medium text-[#888888]">{f.name}</div>
                  <div className="text-sm text-white mt-1">{f.text}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input value={feedbackName} onChange={(e) => setFeedbackName(e.target.value)} placeholder="昵称（选填）" className="sm:w-40 rounded-lg bg-[#1e1e1e] border border-[#2a2a2a] px-3 py-2 text-sm text-white placeholder:text-[#555555] focus:border-[#ff6a10]/50 focus:outline-none" />
          <input value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submitFeedback()} placeholder="说点什么..." className="flex-1 rounded-lg bg-[#1e1e1e] border border-[#2a2a2a] px-3 py-2 text-sm text-white placeholder:text-[#555555] focus:border-[#ff6a10]/50 focus:outline-none" />
          <button onClick={submitFeedback} disabled={!feedbackText.trim()} className="px-5 py-2 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] disabled:opacity-40 whitespace-nowrap">发送</button>
        </div>
      </section>

      {/* ========== Bug 反馈按钮 + 弹窗 ========== */}
      <button onClick={() => setShowBugModal(true)} className="fixed bottom-4 right-4 z-50 px-4 py-2.5 rounded-full bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-medium shadow-lg shadow-[#ff6a10]/30 hover:scale-105 transition-transform">
        🐛 反馈 Bug
      </button>
      {showBugModal && (
        <BugReportModal onClose={() => setShowBugModal(false)} />
      )}

      {/* ========== 页脚 ========== */}
      <footer className="relative z-10 border-t border-[#2a2a2a] bg-[#0e0e0e] px-4 py-10 mt-10">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8 text-sm">
            <div><h4 className="font-medium text-white mb-3">产品</h4><ul className="space-y-2 text-[#888888]"><li className="hover:text-[#ff6a10] cursor-pointer" onClick={() => navigate('/')}>工作台</li><li className="hover:text-[#ff6a10] cursor-pointer" onClick={() => navigate('/path-a')}>AI 作曲</li><li className="hover:text-[#ff6a10] cursor-pointer" onClick={() => navigate('/community')}>社区</li></ul></div>
            <div><h4 className="font-medium text-white mb-3">公测</h4><ul className="space-y-2 text-[#888888]"><li className="cursor-pointer">公测须知</li><li className="cursor-pointer">灰度申请</li><li className="cursor-pointer">每日额度</li></ul></div>
            <div><h4 className="font-medium text-white mb-3">法律</h4><ul className="space-y-2 text-[#888888]"><li className="cursor-pointer">版权声明</li><li className="cursor-pointer">用户协议</li><li className="cursor-pointer">隐私政策</li></ul></div>
            <div><h4 className="font-medium text-white mb-3">联系</h4><ul className="space-y-2 text-[#888888]"><li className="cursor-pointer">反馈 Bug</li><li className="cursor-pointer">意见建议</li></ul></div>
          </div>
          <div className="pt-6 border-t border-[#2a2a2a] flex flex-col sm:flex-row items-center justify-between gap-2">
            <p className="text-xs text-[#555555]">© 2026 MV Studio · 公测测试版 v2.0 · All rights reserved</p>
            <p className="text-xs text-[#555555]">公测期间所有作品禁止商用 · Powered by Render & Cloudflare</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

function BugReportModal({ onClose }: { onClose: () => void }) {
  const [type, setType] = useState('bug');
  const [desc, setDesc] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const submit = async () => {
    try {
      await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/beta/apply-gray', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-User-ID': 'beta_user' },
        body: JSON.stringify({ feature_key: 'bug_report', reason: `[${type}] ${desc}`, contact: '' }),
      });
    } catch { /* 公测容错 */ }
    setSubmitted(true);
    setTimeout(onClose, 2000);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} onClick={(e) => e.target === e.currentTarget && onClose} className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <motion.div initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} className="w-full max-w-md bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl overflow-hidden">
        {submitted ? (
          <div className="p-10 text-center"><span className="text-4xl">✅</span><p className="mt-3 text-white font-medium">感谢反馈！</p><p className="mt-1 text-xs text-[#888888]">我们会尽快处理</p></div>
        ) : (
          <>
            <div className="px-5 pt-5 pb-3 border-b border-[#2a2a2a]"><h3 className="font-bold gradient-text text-lg">🐛 问题反馈</h3></div>
            <div className="p-5 space-y-3">
              <div className="flex gap-2">
                {[{ k: 'bug', l: '🐛 Bug' }, { k: 'suggestion', l: '💡 建议' }, { k: 'other', l: '📝 其他' }].map((o) => (
                  <button key={o.k} onClick={() => setType(o.k)} className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-colors ${type === o.k ? 'border-[#ff6a10]/50 bg-[#ff6a10]/10 text-[#ff6a10]' : 'border-[#2a2a2a] text-[#888888]'}`}>{o.l}</button>
                ))}
              </div>
              <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="详细描述问题..." rows={4} className="w-full rounded-lg bg-[#121212] border border-[#2a2a2a] px-3 py-2 text-sm text-white placeholder:text-[#555555] focus:border-[#ff6a10]/50 focus:outline-none resize-none" />
              <div className="flex gap-2">
                <button onClick={onClose} className="flex-1 py-2 rounded-lg text-sm border border-[#2a2a2a] text-[#888888]">取消</button>
                <button onClick={submit} disabled={!desc.trim()} className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] disabled:opacity-40">提交</button>
              </div>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}
