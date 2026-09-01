import { useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { useAudioGeneration } from '../hooks/useAudioGeneration';
import { WaveformEditor } from '../components/Audio/WaveformEditor';

export function CreateMusicPage() {
  const { t } = useTranslation();
  const tr = (k:string, fb:string)=> t(k)===k?fb:t(k);
  const [description, setDescription] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [genre, setGenre] = useState('');
  const [mood, setMood] = useState('');
  const [vocal, setVocal] = useState('');
  const [duration, setDuration] = useState('30');
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
      duration: parseInt(duration)||30,
    };
    generate('/ai/generate', payload);
  };

  const handleDelete = (id:string) => {
    const next = history.filter(h=>h.id!==id);
    setHistory(next);
    localStorage.setItem('zyvexo_create_history', JSON.stringify(next));
    if (history.find(h=>h.id===id)?.url===audioUrl) setAudioUrl(null);
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-black tracking-tight">{tr('createMusic.title','Create Music')}</h1>
          <p className="mt-1 text-sm text-[#8a8a8a]">{tr('createMusic.subtitle','Generate complete tracks — powered by description, lyrics and style')}</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_0.85fr] gap-6">
          {/* Form */}
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 space-y-4">
            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.songDescription','Song Description')}</label>
              <textarea value={description} onChange={e=> setDescription(e.target.value)} placeholder={tr('createMusic.songDescriptionPlaceholder','Describe the music you want...')} rows={3} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-3 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
            </div>
            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.lyrics','Lyrics')}</label>
              <textarea value={lyrics} onChange={e=> setLyrics(e.target.value)} placeholder={tr('createMusic.lyricsPlaceholder','Enter lyrics or leave empty for AI generation...')} rows={4} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-3 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.genre','Genre')}</label>
                <select value={genre} onChange={e=> setGenre(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{tr('createMusic.genrePlaceholder','Select or enter genre')}</option>
                  <option value="pop">Pop</option><option value="rock">Rock</option><option value="electronic">Electronic</option><option value="hiphop">Hip Hop</option><option value="jazz">Jazz</option><option value="ambient">Ambient</option><option value="cinematic">Cinematic</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.mood','Mood')}</label>
                <select value={mood} onChange={e=> setMood(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{tr('createMusic.moodPlaceholder','Select mood')}</option>
                  <option value="uplifting">Uplifting</option><option value="melancholic">Melancholic</option><option value="energetic">Energetic</option><option value="calm">Calm</option><option value="dreamy">Dreamy</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.vocal','Vocal')}</label>
                <select value={vocal} onChange={e=> setVocal(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="">{tr('createMusic.vocalPlaceholder','Select vocal')}</option>
                  <option value="female">Female</option><option value="male">Male</option><option value="choir">Choir</option><option value="instrumental">Instrumental</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-[#b0b0b0]">{tr('createMusic.duration','Duration')}</label>
                <select value={duration} onChange={e=> setDuration(e.target.value)} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-white/20">
                  <option value="15">15s</option><option value="30">30s</option><option value="60">60s</option><option value="90">90s</option><option value="120">120s</option>
                </select>
              </div>
            </div>
            <button onClick={handleGenerate} disabled={loading || !description.trim()} className="w-full py-3 rounded-xl bg-white text-[#0a0a0a] font-semibold text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#ededed] transition flex items-center justify-center gap-2">
              {loading ? <><span className="w-4 h-4 border-2 border-[#0a0a0a]/30 border-t-[#0a0a0a] rounded-full animate-spin" /> {tr('createMusic.generating','Generating...')}</> : tr('createMusic.generate','Generate Music')}
            </button>
            <p className="text-xs text-[#555555]">{tr('createMusic.tips','Tip: the more specific your description, the closer the result.')}</p>
            {rateLimited && (
              <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300 flex items-center justify-between">
                <span>Rate limited — free tier limit reached.</span>
                <button onClick={()=> setRateLimited(false)} className="text-white underline">Dismiss</button>
              </div>
            )}
          </div>

          {/* Result */}
          <div className="space-y-4">
            <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 min-h-[280px]">
              {!audioUrl ? (
                <div className="h-[240px] flex flex-col items-center justify-center text-center">
                  <div className="w-12 h-12 rounded-full bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg">♪</div>
                  <p className="mt-3 text-sm text-[#6a6a6a]">Your generation will appear here</p>
                  <p className="text-xs text-[#4a4a4a] mt-1">Enter a description and click Generate</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <WaveformEditor url={audioUrl} />
                  <audio controls src={audioUrl} className="w-full" />
                  <div className="flex flex-wrap gap-2">
                    <button onClick={()=> { const a=document.createElement('a'); a.href=audioUrl; a.download='zyvexo-track.wav'; a.click(); }} className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium hover:bg-[#ededed]">{tr('createMusic.download','Download')}</button>
                    <button onClick={()=> { localStorage.setItem('zyvexo_last_save', audioUrl); alert('Saved to My Creations (local)'); }} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-white text-sm hover:bg-[#222222]">{tr('createMusic.save','Save')}</button>
                    <button onClick={()=> setAudioUrl(null)} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-[#ff6b6b] text-sm hover:bg-[#1f1a1a]">{tr('createMusic.delete','Delete')}</button>
                    <button onClick={()=> { setDescription(''); setLyrics(''); }} className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-white text-sm hover:bg-[#222222]">{tr('createMusic.createAgain','Create Again')}</button>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
              <h3 className="text-sm font-semibold text-white">{tr('createMusic.history','History')}</h3>
              {history.length===0 ? (
                <p className="mt-3 text-xs text-[#6a6a6a]">{tr('createMusic.emptyHistory','No history yet — your generations will appear here')}</p>
              ) : (
                <div className="mt-3 space-y-2 max-h-[320px] overflow-auto pr-1">
                  {history.map(h=> (
                    <div key={h.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f]">
                      <button onClick={()=> setAudioUrl(h.url)} className="w-8 h-8 rounded-lg bg-white text-[#0a0a0a] flex items-center justify-center text-xs shrink-0">▶</button>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-white truncate">{h.prompt || 'Untitled'}</div>
                        <div className="text-[11px] text-[#6a6a6a]">{h.time}</div>
                      </div>
                      <button onClick={()=> handleDelete(h.id)} className="text-xs text-[#ff6b6b] hover:text-red-400 px-2">{tr('createMusic.delete','Delete')}</button>
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
