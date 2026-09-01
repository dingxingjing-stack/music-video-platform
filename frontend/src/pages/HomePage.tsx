import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';

export function HomePage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const tr = (k: string, fb: string) => {
    const v = t(k);
    return v === k ? fb : v;
  };

  const cards = [
    {
      key: 'createMusic',
      title: tr('home.cards.createMusic.title', 'Create Music'),
      desc: tr('home.cards.createMusic.desc', 'Generate complete tracks from description, lyrics and style.'),
      icon: '♪',
      to: '/create',
      accent: 'from-[#ff6a10] to-[#ee0979]',
    },
    {
      key: 'voiceClone',
      title: tr('home.cards.voiceClone.title', 'Voice Clone'),
      desc: tr('home.cards.voiceClone.desc', 'Create and manage your own voice models for licensed generation.'),
      icon: '◐',
      to: '/voice-clone',
      accent: 'from-[#38bdf8] to-[#6366f1]',
    },
    {
      key: 'audioTools',
      title: tr('home.cards.audioTools.title', 'Audio Tools'),
      desc: tr('home.cards.audioTools.desc', 'Separation, mastering, conversion and more — all in one place.'),
      icon: '⬢',
      to: '/audio-tools',
      accent: 'from-[#34d399] to-[#06b6d4]',
    },
    {
      key: 'myCreations',
      title: tr('home.cards.myCreations.title', 'My Creations'),
      desc: tr('home.cards.myCreations.desc', 'Manage all your generated and edited works in one hub.'),
      icon: '♡',
      to: '/my-works',
      accent: 'from-[#a78bfa] to-[#fb923c]',
    },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {/* Header */}
      <div className="max-w-[1120px] mx-auto px-6 pt-10 pb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#141414] border border-[#262626] text-[11px] tracking-[0.14em] text-[#8a8a8a]">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {tr('home.badge', 'AI Music Studio · Modern Creation Platform')}
        </div>
        <h1 className="mt-6 text-4xl sm:text-5xl font-black tracking-tight leading-none">
          <span className="bg-gradient-to-r from-white to-[#b0b0b0] bg-clip-text text-transparent">{tr('home.title1', 'AI Music Studio')}</span>
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[#8a8a8a] max-w-2xl">
          {tr('home.subtitle', 'From idea to final mix — a professional AI-powered studio for music, voice and audio.')}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button onClick={() => navigate('/create')} className="px-6 py-3 rounded-xl bg-white text-[#0a0a0a] font-semibold text-sm hover:bg-[#ededed] transition">
            {tr('home.ctaPrimary', 'Start Creating')} →
          </button>
          <button onClick={() => navigate('/community')} className="px-6 py-3 rounded-xl bg-[#141414] border border-[#262626] text-white text-sm hover:bg-[#1a1a1a] transition">
            {tr('home.ctaSecondary', 'Explore Community')}
          </button>
        </div>
      </div>

      {/* Cards */}
      <div className="max-w-[1120px] mx-auto px-6 pb-10">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-sm font-semibold tracking-[0.14em] text-[#4a4a4a] uppercase">{tr('home.featuresTitle', 'Create Your Sound')}</h2>
          <span className="text-xs text-[#555555] hidden sm:block">{tr('home.featuresSubtitle', 'Four core modules covering the full music journey')}</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {cards.map((c) => (
            <button key={c.key} onClick={() => navigate(c.to)} className="text-left rounded-[20px] p-6 bg-[#141414] border border-[#1f1f1f] hover:border-[#2a2a2a] hover:bg-[#171717] transition group relative overflow-hidden">
              <div className={`absolute -right-10 -top-10 w-28 h-28 rounded-full bg-gradient-to-br ${c.accent} opacity-[0.08] blur-2xl group-hover:opacity-[0.14] transition`} />
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.accent} flex items-center justify-center text-white text-lg shadow-lg`}>{c.icon}</div>
              <h3 className="mt-4 text-[18px] font-semibold text-white">{c.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-[#8a8a8a]">{c.desc}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-[#b0b0b0] group-hover:text-white transition">Open <span className="transition group-hover:translate-x-0.5">→</span></span>
            </button>
          ))}
        </div>
      </div>

      {/* Info strip */}
      <div className="max-w-[1120px] mx-auto px-6 pb-12">
        <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
          <div>
            <div className="text-white font-medium mb-1">Professional workflow</div>
            <div className="text-[#8a8a8a] leading-relaxed">Prompt → generation → edit → mix → export. No extra installs.</div>
          </div>
          <div>
            <div className="text-white font-medium mb-1">Responsible voice use</div>
            <div className="text-[#8a8a8a] leading-relaxed">Voice Clone is permission-based and traceable by design.</div>
          </div>
          <div>
            <div className="text-white font-medium mb-1">Your works, your control</div>
            <div className="text-[#8a8a8a] leading-relaxed">All generations saved to My Creations with playback and export.</div>
          </div>
        </div>
        <p className="mt-6 text-center text-xs text-[#4a4a4a]">© 2026 Zyvexo · AI Music Studio · {tr('nav.betaTag','Public Beta v2.0')}</p>
      </div>
    </div>
  );
}

export default HomePage;
