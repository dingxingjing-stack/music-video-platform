import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';

export function HomePage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const cards = [
    {
      key: 'createMusic',
      title: t('home.cards.createMusic.title'),
      desc: t('home.cards.createMusic.desc'),
      icon: '♪',
      to: '/create',
      accent: 'from-[#ff6a10] to-[#ee0979]',
    },
    {
      key: 'voiceClone',
      title: t('home.cards.voiceClone.title'),
      desc: t('home.cards.voiceClone.desc'),
      icon: '◐',
      to: '/voice-clone',
      accent: 'from-[#38bdf8] to-[#6366f1]',
    },
    {
      key: 'audioTools',
      title: t('home.cards.audioTools.title'),
      desc: t('home.cards.audioTools.desc'),
      icon: '⬢',
      to: '/audio-tools',
      accent: 'from-[#34d399] to-[#06b6d4]',
    },
    {
      key: 'myCreations',
      title: t('home.cards.myCreations.title'),
      desc: t('home.cards.myCreations.desc'),
      icon: '♡',
      to: '/my-works',
      accent: 'from-[#a78bfa] to-[#fb923c]',
    },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 pt-10 pb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#141414] border border-[#262626] text-[11px] tracking-[0.14em] text-[#8a8a8a]">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {t('home.badge')}
        </div>
        <h1 className="mt-6 text-4xl sm:text-5xl font-black tracking-tight leading-none">
          <span className="bg-gradient-to-r from-white to-[#b0b0b0] bg-clip-text text-transparent">{t('home.title1')}</span>
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[#8a8a8a] max-w-2xl">
          {t('home.subtitle')}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button onClick={() => navigate('/create')} className="px-6 py-3 rounded-xl bg-white text-[#0a0a0a] font-semibold text-sm hover:bg-[#ededed] transition">
            {t('home.ctaPrimary')} →
          </button>
          <button onClick={() => navigate('/community')} className="px-6 py-3 rounded-xl bg-[#141414] border border-[#262626] text-white text-sm hover:bg-[#1a1a1a] transition">
            {t('home.ctaSecondary')}
          </button>
        </div>
      </div>

      <div className="max-w-[1120px] mx-auto px-6 pb-10">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-sm font-semibold tracking-[0.14em] text-[#4a4a4a] uppercase">{t('home.featuresTitle')}</h2>
          <span className="text-xs text-[#555555] hidden sm:block">{t('home.featuresSubtitle')}</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {cards.map((c) => (
            <button key={c.key} onClick={() => navigate(c.to)} className="text-left rounded-[20px] p-6 bg-[#141414] border border-[#1f1f1f] hover:border-[#2a2a2a] hover:bg-[#171717] transition group relative overflow-hidden">
              <div className={`absolute -right-10 -top-10 w-28 h-28 rounded-full bg-gradient-to-br ${c.accent} opacity-[0.08] blur-2xl group-hover:opacity-[0.14] transition`} />
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.accent} flex items-center justify-center text-white text-lg shadow-lg`}>{c.icon}</div>
              <h3 className="mt-4 text-[18px] font-semibold text-white">{c.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-[#8a8a8a]">{c.desc}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-[#b0b0b0] group-hover:text-white transition">{t('home.info.open')} <span className="transition group-hover:translate-x-0.5">→</span></span>
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-[1120px] mx-auto px-6 pb-12">
        <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
          <div>
            <div className="text-white font-medium mb-1">{t('home.info.workflowTitle')}</div>
            <div className="text-[#8a8a8a] leading-relaxed">{t('home.info.workflowDesc')}</div>
          </div>
          <div>
            <div className="text-white font-medium mb-1">{t('home.info.voiceTitle')}</div>
            <div className="text-[#8a8a8a] leading-relaxed">{t('home.info.voiceDesc')}</div>
          </div>
          <div>
            <div className="text-white font-medium mb-1">{t('home.info.worksTitle')}</div>
            <div className="text-[#8a8a8a] leading-relaxed">{t('home.info.worksDesc')}</div>
          </div>
        </div>
        <p className="mt-6 text-center text-xs text-[#4a4a4a]">© 2026 Zyvexo · AI Music Studio · {t('nav.betaTag')}</p>
      </div>
    </div>
  );
}

export default HomePage;
