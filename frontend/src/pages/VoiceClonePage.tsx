import { useState, useRef } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { api } from '../config/api';

interface VoiceModel {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  sampleUrl?: string;
}

export function VoiceClonePage() {
  const { t } = useTranslation();
  const tr = (k: string, fb: string) => (t(k) === k ? fb : t(k));
  const [voices, setVoices] = useState<VoiceModel[]>(() => {
    try {
      const raw = localStorage.getItem('zyvexo_voices');
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  });
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [consent, setConsent] = useState(false);

  const persist = (next: VoiceModel[]) => {
    setVoices(next);
    localStorage.setItem('zyvexo_voices', JSON.stringify(next));
  };

  const handleCreate = async () => {
    if (!file || !name.trim() || !consent) return;
    setCreating(true);
    try {
      // Try backend if available, otherwise fallback to local mock
      // Existing API: we attempt to reuse current audio upload endpoint; if fails, store locally
      let sampleUrl: string | undefined;
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(api.url('/api/v1/audio/upload'), { method: 'POST', body: form });
        if (res.ok) {
          const data = await res.json();
          sampleUrl = data.url || data.audio_url;
        }
      } catch {}
      if (!sampleUrl) {
        sampleUrl = URL.createObjectURL(file);
      }
      const next: VoiceModel = {
        id: Math.random().toString(36).slice(2, 9),
        name: name.trim(),
        description: description.trim(),
        createdAt: new Date().toISOString(),
        sampleUrl,
      };
      persist([next, ...voices]);
      setName('');
      setDescription('');
      setFile(null);
      setConsent(false);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (id: string) => {
    persist(voices.filter(v => v.id !== id));
  };

  const handlePreview = (v: VoiceModel) => {
    if (previewId === v.id) { setPreviewId(null); audioRef.current?.pause(); return; }
    setPreviewId(v.id);
    if (v.sampleUrl && audioRef.current) {
      audioRef.current.src = v.sampleUrl;
      audioRef.current.play().catch(()=>{});
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-black tracking-tight">{tr('voiceClone.title','Voice Clone')}</h1>
          <p className="mt-1 text-sm text-[#8a8a8a]">{tr('voiceClone.subtitle','Create and manage your own voice models — only for voices you own or have permission to use')}</p>
          <div className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
            <span>⚠</span> {tr('voiceClone.consent','Only clone voices you own or have permission to use.')}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-6">
          {/* Create form */}
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 space-y-4">
            <h2 className="text-sm font-semibold tracking-wide text-white">{tr('voiceClone.createVoice','Create Voice')}</h2>

            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{tr('voiceClone.uploadSample','Upload Voice Sample')}</label>
              <div className="mt-1.5 rounded-xl border border-dashed border-[#2a2a2a] bg-[#0f0f0f] p-4">
                <input type="file" accept="audio/*" onChange={e=> setFile(e.target.files?.[0]||null)} className="text-sm text-[#8a8a8a] file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-white file:text-[#0a0a0a] file:text-sm file:font-medium hover:file:bg-[#ededed]" />
                <p className="mt-2 text-xs text-[#555555]">{tr('voiceClone.uploadHint','WAV/MP3, 10s–2min, clean vocal')}</p>
                {file && <p className="mt-1 text-xs text-emerald-400">Selected: {file.name} ({(file.size/1024).toFixed(0)} KB)</p>}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{tr('voiceClone.voiceName','Voice Name')}</label>
              <input value={name} onChange={e=> setName(e.target.value)} placeholder={tr('voiceClone.voiceNamePlaceholder','e.g. My Voice v1')} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-2.5 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20" />
            </div>

            <div>
              <label className="text-xs font-medium text-[#b0b0b0]">{tr('voiceClone.voiceDescription','Voice Description')}</label>
              <textarea value={description} onChange={e=> setDescription(e.target.value)} placeholder={tr('voiceClone.voiceDescriptionPlaceholder','Describe the character and use of this voice...')} rows={3} className="mt-1.5 w-full rounded-xl bg-[#0f0f0f] border border-[#262626] px-3.5 py-2.5 text-sm text-white placeholder:text-[#555555] focus:outline-none focus:border-white/20 resize-none" />
            </div>

            <label className="flex items-start gap-2.5 py-1 cursor-pointer">
              <input type="checkbox" checked={consent} onChange={e=> setConsent(e.target.checked)} className="mt-0.5 accent-white" />
              <span className="text-xs leading-relaxed text-[#8a8a8a]">{tr('voiceClone.consent','Only clone voices you own or have permission to use.')}</span>
            </label>

            <button onClick={handleCreate} disabled={!file || !name.trim() || !consent || creating} className="w-full py-2.5 rounded-xl bg-white text-[#0a0a0a] text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#ededed] transition">
              {creating ? tr('createMusic.generating','Generating...') : tr('voiceClone.createVoice','Create Voice')}
            </button>

            <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3">
              <div className="text-xs font-medium text-amber-300">{tr('voiceClone.pending','Pending Integration')}</div>
              <div className="mt-1 text-xs leading-relaxed text-[#b0b0b0]">{tr('voiceClone.pendingDesc','Voice clone backend is not yet fully available — UI is ready; storage and playback use existing capabilities.')}</div>
            </div>
          </div>

          {/* My Voices */}
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wide text-white">{tr('voiceClone.myVoices','My Voices')} <span className="ml-1 text-xs text-[#6a6a6a]">({voices.length})</span></h2>
              <span className="text-xs text-[#555555]">Local</span>
            </div>

            {voices.length === 0 ? (
              <div className="mt-6 rounded-xl border border-dashed border-[#262626] bg-[#0f0f0f] p-8 text-center">
                <div className="text-lg">◐</div>
                <p className="mt-2 text-sm text-[#6a6a6a]">{tr('voiceClone.empty','No voice models yet — upload a sample to create')}</p>
              </div>
            ) : (
              <div className="mt-4 space-y-3 max-h-[520px] overflow-auto pr-1">
                {voices.map(v=> (
                  <div key={v.id} className="rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-white">{v.name}</div>
                        <div className="text-xs text-[#6a6a6a] line-clamp-2">{v.description || '—'}</div>
                        <div className="text-[11px] text-[#444444] mt-1">{new Date(v.createdAt).toLocaleString()}</div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button onClick={()=> handlePreview(v)} className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border ${previewId===v.id ? 'bg-white text-[#0a0a0a] border-white' : 'bg-[#1a1a1a] text-white border-[#262626] hover:bg-[#222222]'}`}>{tr('voiceClone.preview','Preview')}</button>
                        <button onClick={()=> handleDelete(v.id)} className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-[#1a1a1a] border border-[#262626] text-[#ff6b6b] hover:bg-[#1f1f1f]">{tr('voiceClone.delete','Delete')}</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <audio ref={audioRef} onEnded={()=> setPreviewId(null)} className="hidden" />
            <p className="mt-4 text-[11px] leading-relaxed text-[#4a4a4a]">Backend voice-clone API is not yet fully deployed. Current storage uses browser local persistence and existing upload capability; server-side training and licensed synthesis will be connected when available.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default VoiceClonePage;
