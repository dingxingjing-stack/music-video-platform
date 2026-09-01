import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';

export function AudioToolsPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const tr = (k:string, fb:string)=> t(k)===k?fb:t(k);

  const tools = [
    { key:'separation', title: tr('audioTools.separation','Audio Separation'), desc: tr('audioTools.separationDesc','Demucs-based 4-stem separation: vocals/drums/bass/other'), icon:'⬢', to:'/audio-tools/separation', available: true },
    { key:'mastering', title: tr('audioTools.mastering','Audio Mastering'), desc: tr('audioTools.masteringDesc','Intelligent mastering and loudness optimization'), icon:'◈', to:'/audio-tools/mastering', available: true },
    { key:'lyric', title: tr('audioTools.lyricTool','Lyric Tools'), desc: tr('audioTools.lyricDesc','AI lyric generation and writing assistance'), icon:'≡', to:'/audio-tools/lyrics', available: true },
    { key:'conversion', title: tr('audioTools.conversion','Format Conversion'), desc: tr('audioTools.conversionDesc','Convert between WAV / MP3 / FLAC and more'), icon:'⇄', to:'#', available: false },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 py-8">
        <h1 className="text-2xl font-black tracking-tight">{tr('audioTools.title','Audio Tools')}</h1>
        <p className="mt-1 text-sm text-[#8a8a8a]">{tr('audioTools.subtitle','All-in-one audio processing — separation, mastering, conversion')}</p>

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {tools.map(tool=> (
            <div key={tool.key} className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 flex flex-col">
              <div className="w-10 h-10 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg">{tool.icon}</div>
              <h3 className="mt-4 text-base font-semibold text-white">{tool.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-[#8a8a8a] flex-1">{tool.desc}</p>
              <div className="mt-4">
                {tool.available ? (
                  <button onClick={()=> tool.to.startsWith('#') ? null : navigate(tool.to)} className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium hover:bg-[#ededed] transition">{tr('audioTools.open','Open')} →</button>
                ) : (
                  <span className="inline-flex px-3 py-1 rounded-full bg-[#1a1a1a] border border-[#262626] text-xs text-[#6a6a6a]">{tr('audioTools.comingSoon','Coming Soon')}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
          <h3 className="text-sm font-semibold text-white mb-2">How it works</h3>
          <ul className="text-sm text-[#8a8a8a] list-disc list-inside space-y-1">
            <li>Tools run on existing backend capabilities — no mocked results.</li>
            <li>Separation uses Demucs; mastering uses loudness/target presets.</li>
            <li>All outputs can be saved to My Creations.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default AudioToolsPage;
