import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';
import { useAudioGeneration } from '../hooks/useAudioGeneration';
import { WaveformEditor } from '../components/Audio/WaveformEditor';
import { SONG_LANGUAGES } from '../config/songLanguages';
import { authFetch } from '../api/http';
import { api } from '../config/api';
import { useAuth } from '../context/AuthContext';
import { useCreditsBalance } from '../hooks/useCreditsBalance';

// 产品规则 v1：用户不选择时长，系统按 240–270s 自动生成（后端硬上限 270s）
const GENERATION_SECONDS = 270;
// 一次成功创作的官方定价（Credits），用于前端余额提示
const CREATION_COST_CREDITS = 30;

export function CreateMusicPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { isLoggedIn } = useAuth();
  const credits = useCreditsBalance(isLoggedIn);
  const [description, setDescription] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [genre, setGenre] = useState('');
  const [mood, setMood] = useState('');
  const [vocal, setVocal] = useState('');
  const [songLanguage, setSongLanguage] = useState('');
  const [saving, setSaving] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [history, setHistory] = useState<{id:string, url:string, prompt:string, time:string}[]>(()=> {
    try{ const r=localStorage.getItem('zyvexo_create_history'); return r?JSON.parse(r):[] }catch{return []}
  });
  const { loading, generate, rateLimited, setRateLimited } = useAudioGeneration({
    onSuccess: (url: string) => {
      setAudioUrl(url);
      const item = { id: Math.random().toString(36).slice(2,8), url, prompt: description, time: new Date().toLocaleString() };
      const next = [item, ...history].slice(0,20);
      setHistory(next);
      localStorage.setItem('zyvexo_create_history', JSON.stringify(next));
    }
  });

  const handleGenerate = () => {
    if (!description.trim()) return;
    const payload: any = {
      prompt: description.trim(),
      lyrics: lyrics.trim() || undefined,
      style: genre || 'pop',
      mood: mood || undefined,
      vocal: vocal || undefined,
      instrumental: vocal === 'instrumental' || undefined,
      duration: GENERATION_SECONDS,
      song_language: songLanguage || undefined,
    };
    generate('/ai/generate', payload);
  };

  const handleDelete = (id:string) => {
    const next = history.filter(h=>h.id!==id);
    setHistory(next);
    localStorage.setItem('zyvexo_create_history', JSON.stringify(next));
    if (history.find(h=>h.id===id)?.url===audioUrl) setAudioUrl(null);
  };

  // 保存作品到作品库：调真实后端 POST /api/v1/songs（含 song_language），
  // 取代旧的 localStorage mock（zyvexo_last_save）。
  const handleSave = async () => {
    if (!audioUrl) return;
    setSaving(true);
    try {
      await authFetch<{ id?: string }>(api.url('/api/v1/songs'), {
        method: 'POST',
        body: {
          title: description.trim().slice(0, 80) || 'Untitled',
          lyrics: lyrics.trim() || null,
          style: genre || 'pop',
          duration_seconds: GENERATION_SECONDS,
          song_language: songLanguage || null,
        },
      });
      alert(t('createMusic.saved'));
    } catch (e) {
      alert(t('createMusic.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-black tracking-tight">{t('createMusic.title')}</h1>
          <p className="mt-1 text-sm text-[#8a8a8a]">{t('createMusic.subtitle')}</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_0.85fr] gap-6">
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 space-y-4">
            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.songDescription')}</label>
              <textarea value={description} onChange={e=> setDescription(e.target.value)} placeholder={t('createMusic.songDescriptionPlaceholder')} rows={3} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-3 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
            </div>
            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.lyrics')}</label>
              <textarea value={lyrics} onChange={e=> setLyrics(e.target.value)} placeholder={t('createMusic.lyricsPlaceholder')} rows={4} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-3 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.genre')}</label>
                <select value={genre} onChange={e=> setGenre(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{t('createMusic.genrePlaceholder')}</option>
                  <option value="pop">{t('createMusic.genres.pop')}</option>
                  <option value="rock">{t('createMusic.genres.rock')}</option>
                  <option value="electronic">{t('createMusic.genres.electronic')}</option>
                  <option value="hiphop">{t('createMusic.genres.hiphop')}</option>
                  <option value="jazz">{t('createMusic.genres.jazz')}</option>
                  <option value="ambient">{t('createMusic.genres.ambient')}</option>
                  <option value="cinematic">{t('createMusic.genres.cinematic')}</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.mood')}</label>
                <select value={mood} onChange={e=> setMood(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{t('createMusic.moodPlaceholder')}</option>
                  <option value="uplifting">{t('createMusic.moods.uplifting')}</option>
                  <option value="melancholic">{t('createMusic.moods.melancholic')}</option>
                  <option value="energetic">{t('createMusic.moods.energetic')}</option>
                  <option value="calm">{t('createMusic.moods.calm')}</option>
                  <option value="dreamy">{t('createMusic.moods.dreamy')}</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.vocal')}</label>
                <select value={vocal} onChange={e=> setVocal(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{t('createMusic.vocalPlaceholder')}</option>
                  <option value="female">{t('createMusic.vocals.female')}</option>
                  <option value="male">{t('createMusic.vocals.male')}</option>
                  <option value="choir">{t('createMusic.vocals.choir')}</option>
                  <option value="instrumental">{t('createMusic.vocals.instrumental')}</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{t('createMusic.songLanguage')}</label>
                <select value={songLanguage} onChange={e=> setSongLanguage(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{t('createMusic.songLanguageAuto')}</option>
                  {SONG_LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>{l.nativeName}</option>
                  ))}
                </select>
              </div>
            </div>
            {(() => {
              const balanceKnown = credits.balance !== null;
              const insufficient = balanceKnown && (credits.balance as number) < CREATION_COST_CREDITS;
              return (
                <>
                  <p className="text-xs text-[#8a8a8a] -mt-1">
                    {t('createMusic.creditsRule')}
                    {balanceKnown && <span className="ml-2 text-[#b0b0b0]">{t('nav.credits', { n: credits.balance as number })}</span>}
                  </p>
                  {insufficient && (
                    <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300 flex items-center justify-between">
                      <span>{t('createMusic.creditsLow')}</span>
                      <button onClick={() => navigate('/pricing')} className="text-white underline">{t('createMusic.goPricing')}</button>
                    </div>
                  )}
                  <button onClick={handleGenerate} disabled={loading || !description.trim() || insufficient} className="w-full py-3 rounded-xl bg-white text-[#0a0a0a] font-semibold text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#ededed] transition flex items-center justify-center gap-2">
                    {loading ? <><span className="w-4 h-4 border-2 border-[#0a0a0a]/30 border-t-[#0a0a0a] rounded-full animate-spin" /> {t('createMusic.generating')}</> : `${t('createMusic.generate')} · ${CREATION_COST_CREDITS} ${t('pricing.credits')}`}
                  </button>
                </>
              );
            })()}
            <p className="text-xs text-[#555555]">{t('createMusic.tips')}</p>
            {rateLimited && (
              <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300 flex items-center justify-between">
                <span>{t('createMusic.rateLimited')}</span>
                <button onClick={()=> setRateLimited(false)} className="text-white underline">{t('createMusic.dismiss')}</button>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 min-h-[280px]">
              {!audioUrl ? (
                <div className="h-[240px] flex flex-col items-center justify-center text-center">
                  <div className="w-12 h-12 rounded-full bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg">♪</div>
                  <p className="mt-3 text-sm text-[#6a6a6a]">{t('createMusic.resultPlaceholderTitle')}</p>
                  <p className="text-xs text-[#4a4a4a] mt-1">{t('createMusic.resultPlaceholderDesc')}</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <WaveformEditor url={audioUrl} />
                  <audio controls src={audioUrl} className="w-full" />
                  <div className="flex flex-wrap gap-2">
                    <button onClick={()=> { const a=document.createElement('a'); a.href=audioUrl; a.download='zyvexo-track.wav'; a.click(); }} className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium hover:bg-[#ededed]">{t('createMusic.download')}</button>
                    <button onClick={handleSave} disabled={saving} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-white text-sm hover:bg-[#222222] disabled:opacity-50">{t('createMusic.save')}</button>
                    <button onClick={()=> setAudioUrl(null)} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-[#ff6b6b] text-sm hover:bg-[#1f1a1a]">{t('createMusic.delete')}</button>
                    <button onClick={()=> { setDescription(''); setLyrics(''); }} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-white text-sm hover:bg-[#222222]">{t('createMusic.createAgain')}</button>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
              <h3 className="text-sm font-semibold text-white">{t('createMusic.history')}</h3>
              {history.length===0 ? (
                <p className="mt-3 text-xs text-[#6a6a6a]">{t('createMusic.emptyHistory')}</p>
              ) : (
                <div className="mt-3 space-y-2 max-h-[320px] overflow-auto pr-1">
                  {history.map(h=> (
                    <div key={h.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f]">
                      <button onClick={()=> setAudioUrl(h.url)} className="w-8 h-8 rounded-lg bg-white text-[#0a0a0a] flex items-center justify-center text-xs shrink-0">▶</button>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-white truncate">{h.prompt || 'Untitled'}</div>
                        <div className="text-[11px] text-[#6a6a6a]">{h.time}</div>
                      </div>
                      <button onClick={()=> handleDelete(h.id)} className="text-xs text-[#ff6b6b] hover:text-red-400 px-2">{t('createMusic.delete')}</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CreateMusicPage;
