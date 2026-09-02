import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';

export function AudioToolsPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const tools = [
    { key:'separation', title: t('audioTools.separation'), desc: t('audioTools.separationDesc'), icon:'⬢', to:'/audio-tools/separation', available: true },
    { key:'mastering', title: t('audioTools.mastering'), desc: t('audioTools.masteringDesc'), icon:'◈', to:'/audio-tools/mastering', available: true },
    { key:'lyric', title: t('audioTools.lyricTool'), desc: t('audioTools.lyricDesc'), icon:'≡', to:'/audio-tools/lyrics', available: true },
    { key:'conversion', title: t('audioTools.conversion'), desc: t('audioTools.conversionDesc'), icon:'⇄', to:'#', available: false },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 py-8">
        <h1 className="text-2xl font-black tracking-tight">{t('audioTools.title')}</h1>
        <p className="mt-1 text-sm text-[#8a8a8a]">{t('audioTools.subtitle')}</p>

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {tools.map(tool=> (
            <div key={tool.key} className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 flex flex-col">
              <div className="w-10 h-10 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg">{tool.icon}</div>
              <h3 className="mt-4 text-base font-semibold text-white">{tool.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-[#8a8a8a] flex-1">{tool.desc}</p>
              <div className="mt-4">
                {tool.available ? (
                  <button onClick={()=> tool.to.startsWith('#') ? null : navigate(tool.to)} className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium hover:bg-[#ededed] transition">{t('audioTools.open')} →</button>
                ) : (
                  <span className="inline-flex px-3 py-1 rounded-full bg-[#1a1a1a] border border-[#262626] text-xs text-[#6a6a6a]">{t('audioTools.comingSoon')}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
          <h3 className="text-sm font-semibold text-white mb-2">{t('audioTools.howItWorks')}</h3>
          <ul className="text-sm text-[#8a8a8a] list-disc list-inside space-y-1">
            <li>{t('audioTools.how1')}</li>
            <li>{t('audioTools.how2')}</li>
            <li>{t('audioTools.how3')}</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default AudioToolsPage;
