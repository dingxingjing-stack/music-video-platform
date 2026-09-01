import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { BetaConsentModal } from '../components/BetaConsentModal';
import { api } from '../config/api';
import { useTranslation } from '../i18n/useTranslation';

const fadeIn = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-50px' },
  transition: { duration: 0.5, delay },
});

export function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const tr = (k: string, fb: string) => (t(k) === k ? fb : t(k));
  const [feedbacks, setFeedbacks] = useState<{ name: string; text: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackName, setFeedbackName] = useState('');
  const [toast, setToast] = useState<{ id: string; message: string; type: 'success' | 'error' } | null>(null);

  const FEATURES = [
    { icon: '♪', title: tr('home.cards.createMusic.title', 'Create Music'), desc: tr('home.cards.createMusic.desc', 'Generate complete tracks from description, lyrics and style.'), path: '/create', color: 'from-[#ff6a10]/20 to-[#ee0979]/5' },
    { icon: '◐', title: tr('home.cards.voiceClone.title', 'Voice Clone'), desc: tr('home.cards.voiceClone.desc', 'Create and manage your own voice models for licensed generation.'), path: '/voice-clone', color: 'from-[#38bdf8]/20 to-[#6366f1]/5' },
    { icon: '⬢', title: tr('home.cards.audioTools.title', 'Audio Tools'), desc: tr('home.cards.audioTools.desc', 'Separation, mastering, conversion and more — all in one place.'), path: '/audio-tools', color: 'from-[#34d399]/20 to-[#06b6d4]/5' },
    { icon: '♡', title: tr('home.cards.myCreations.title', 'My Creations'), desc: tr('home.cards.myCreations.desc', 'Manage all your generated and edited works in one hub.'), path: '/my-works', color: 'from-[#a78bfa]/20 to-[#fb923c]/5' },
  ];

  const CASES = [
    { title: 'Night Neon', author: '@beta_01', genre: 'Synthwave', plays: 234, cover: '◈' },
    { title: 'Summer Breeze', author: '@beta_02', genre: 'Indie Pop', plays: 189, cover: '○' },
    { title: 'Code Poet', author: '@beta_03', genre: 'Lo-fi', plays: 312, cover: '⬡' },
    { title: 'Deep Echo', author: '@beta_04', genre: 'Ambient', plays: 156, cover: '⬢' },
  ];

  useEffect(() => {
    const fetchFeedback = async () => {
      try {
        const res = await fetch(api.url('/api/v1/feedback'));
        if (!res.ok) throw new Error('Failed');
        const data = await res.json();
        setFeedbacks(data.map((f: any) => ({ name: f.name, text: f.text })));
      } catch {
        setFeedbacks([
          { name: tr('landing.anonymousUser', 'Anonymous'), text: 'Great public beta — fast generation and clean studio feel.' },
          { name: tr('landing.anonymousUser', 'Anonymous'), text: 'Voice Clone UI is clear and the audio tools are well integrated.' },
        ]);
      } finally { setLoading(false); }
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
      const res = await fetch(api.url('/api/v1/feedback'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: feedbackName.trim() || tr('landing.anonymousUser','Anonymous'), text: feedbackText.trim() }),
      });
      if (!res.ok) throw new Error('Network error');
      setFeedbacks(prev => [{ name: feedbackName.trim() || tr('landing.anonymousUser','Anonymous'), text: feedbackText.trim() }, ...prev]);
      setFeedbackText('');
      setFeedbackName('');
      showToast(tr('landing.feedbackToastOk','Thank you for your feedback!'), 'success');
    } catch {
      showToast(tr('landing.feedbackToastFail','Submission failed'), 'error');
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] relative overflow-x-hidden">
      <BetaConsentModal />
      <div className="fixed inset-0 pointer-events-none opacity-[0.04]">
        <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, white 1px, transparent 0)', backgroundSize: '24px 24px' }} />
      </div>

      {/* Hero */}
      <section className="relative min-h-[86vh] flex items-center justify-center px-6 py-16">
        <motion.div className="text-center max-w-3xl z-10" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#141414] border border-[#262626] text-[11px] tracking-[0.14em] text-[#8a8a8a]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {tr('landing.heroBadge','Public beta · Completely free')}
          </div>
          <h1 className="text-4xl sm:text-6xl font-black tracking-tight mt-6 leading-none">
            <span className="bg-gradient-to-r from-white to-[#8a8a8a] bg-clip-text text-transparent">{tr('landing.heroTitle1','All-in-one AI')}</span>
            <br />
            <span className="bg-gradient-to-r from-white to-[#8a8a8a] bg-clip-text text-transparent">{tr('landing.heroTitle2','AI Music Studio')}</span>
          </h1>
          <p className="text-sm sm:text-base text-[#8a8a8a] mt-4 max-w-xl mx-auto leading-relaxed">
            {tr('landing.heroSub','From inspiration and composition to final production — your AI-powered studio.')}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center mt-8">
            <button onClick={() => navigate('/')} className="px-8 py-3.5 rounded-xl font-semibold bg-white text-[#0a0a0a] hover:bg-[#ededed] transition">
              {tr('landing.ctaStart','Start Creating')}
            </button>
            <button onClick={() => navigate('/community')} className="px-8 py-3.5 rounded-xl font-medium border border-[#1f1f1f] bg-[#141414] text-white hover:bg-[#1a1a1a] transition">
              {tr('landing.ctaExplore','Explore the Community')}
            </button>
          </div>
        </motion.div>
      </section>

      {/* Features */}
      <section className="relative z-10 px-6 py-14 max-w-[1120px] mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-10">
          <h2 className="text-xl sm:text-2xl font-black tracking-tight text-white">{tr('home.featuresTitle','Create Your Sound')}</h2>
          <p className="text-sm text-[#6a6a6a] mt-1">{tr('home.featuresSubtitle','Four core modules covering the full music journey')}</p>
        </motion.div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FEATURES.map((f, i) => (
            <motion.div key={f.title} {...fadeIn(i * 0.06)} onClick={() => navigate(f.path)} className={`rounded-[20px] p-6 bg-gradient-to-br ${f.color} border border-[#1f1f1f] cursor-pointer hover:border-white/10 hover:bg-[#141414] transition`}>
              <div className="w-10 h-10 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg">{f.icon}</div>
              <h3 className="text-base font-semibold text-white mt-4">{f.title}</h3>
              <p className="text-sm text-[#8a8a8a] mt-1 leading-relaxed">{f.desc}</p>
              <div className="mt-3 text-xs font-medium text-white/60">Open →</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Cases */}
      <section className="relative z-10 px-6 py-12 max-w-[1120px] mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-8">
          <h2 className="text-xl font-black text-white">{tr('landing.casesTitle','Community Works')}</h2>
          <p className="text-sm text-[#6a6a6a]">{tr('landing.casesSub','Real creations from public beta users.')}</p>
        </motion.div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {CASES.map((c, i) => (
            <motion.div key={c.title} {...fadeIn(i * 0.05)} className="rounded-2xl p-5 bg-[#141414] border border-[#1f1f1f]">
              <div className="w-10 h-10 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center">{c.cover}</div>
              <h3 className="text-sm font-semibold text-white mt-3">{c.title}</h3>
              <p className="text-xs text-[#6a6a6a] mt-1">{c.author} · {c.genre}</p>
              <p className="text-xs text-[#4a4a4a] mt-1">▶ {c.plays} plays</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Feedback */}
      <section className="relative z-10 px-6 py-12 max-w-[720px] mx-auto">
        <motion.div {...fadeIn()} className="text-center mb-8">
          <h2 className="text-xl font-black text-white">{tr('landing.feedbackTitle','User Feedback')}</h2>
          <p className="text-sm text-[#6a6a6a]">{tr('landing.feedbackSub','Real feedback from public beta users.')}</p>
        </motion.div>
        {loading ? <div className="text-center text-sm text-[#555555] py-8">Loading...</div> : (
          <div className="space-y-3">
            {feedbacks.map((f, i) => (
              <motion.div key={i} {...fadeIn(i * 0.04)} className="rounded-xl p-4 bg-[#141414] border border-[#1f1f1f]">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-7 h-7 rounded-full bg-white text-[#0a0a0a] text-xs font-bold flex items-center justify-center">{f.name.charAt(0).toUpperCase()}</div>
                  <span className="text-sm font-medium text-white">{f.name}</span>
                </div>
                <p className="text-sm text-[#8a8a8a]">{f.text}</p>
              </motion.div>
            ))}
          </div>
        )}
        <motion.div {...fadeIn(0.1)} className="mt-6 rounded-2xl p-5 bg-[#141414] border border-[#1f1f1f]">
          <h3 className="text-sm font-semibold text-white mb-3">Leave your feedback</h3>
          <input type="text" value={feedbackName} onChange={e=> setFeedbackName(e.target.value)} placeholder="Nickname (optional)" className="w-full mb-3 px-3.5 py-2.5 bg-[#0f0f0f] border border-[#1f1f1f] rounded-xl text-white text-sm placeholder:text-[#555555] focus:outline-none focus:border-white/20" />
          <textarea value={feedbackText} onChange={e=> setFeedbackText(e.target.value)} placeholder="Share your experience..." rows={3} className="w-full mb-3 px-3.5 py-2.5 bg-[#0f0f0f] border border-[#1f1f1f] rounded-xl text-white text-sm placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
          <button onClick={submitFeedback} disabled={!feedbackText.trim()} className="px-5 py-2.5 rounded-xl bg-white text-[#0a0a0a] text-sm font-semibold disabled:opacity-40 hover:bg-[#ededed] transition">Submit Feedback</button>
        </motion.div>
      </section>

      <footer className="relative z-10 border-t border-[#1f1f1f] py-8 px-6 text-center">
        <div className="max-w-[1120px] mx-auto">
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mb-4 text-xs text-[#6a6a6a]">
            <a href="/legal/terms" className="hover:text-white">Terms</a>
            <a href="/legal/privacy" className="hover:text-white">Privacy</a>
            <a href="/legal/aimusic-copyright" className="hover:text-white">AI Copyright</a>
            <a href="/legal/voice-cloning" className="hover:text-white">Voice Clone Policy</a>
          </div>
          <p className="text-xs text-[#4a4a4a]">© 2026 Zyvexo · AI Music Studio</p>
        </div>
      </footer>

      {toast && <div className={`fixed bottom-6 right-6 z-[200] px-4 py-2.5 rounded-xl text-sm font-medium ${toast.type==='success'?'bg-emerald-500 text-white':'bg-red-500 text-white'}`}>{toast.message}</div>}
    </div>
  );
}
