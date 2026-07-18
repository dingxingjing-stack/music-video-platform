/**
 * 声音克隆页面 v2 — 合规版
 * - 前置法律协议勾选
 * - 官方音色 / 我的克隆音色 分组
 * - 音频上传校验（时长/格式/本月额度）
 * - 排队提示 + 操作日志
 * - 隐藏导出/分享按钮
 */
import { useState, useEffect } from 'react';
import { RateLimitBanner } from '../hooks/useAudioGeneration';

interface VoiceSample { id: string; name: string; audio_url: string; duration: number; created_at: string; is_private?: boolean; }

interface CloneResult { success: boolean; audio_url: string | null; duration: number | null; voice_id: string | null; error: string | null; message: string | null; }

interface QuotaInfo { used: number; limit: number; can_clone: boolean; }

const API = 'https://ai-music-backend-8e85.onrender.com/api/v1';

const CONSENT_TEXT = [
  '本次上传的音频为本人自有嗓音，已完整取得该声音的使用授权，绝不盗用、克隆公众人物、亲友、陌生人等第三方声音；',
  '授权平台使用 Agnes AI 接口完成声音克隆，生成的音色仅可在本平台内本人账号下使用，不可导出、分发、商用授权给第三方；',
  '若因本人提交侵权音频产生民事、刑事责任，全部由本人承担，平台有权删除音色、封禁账号、留存证据移交监管部门；',
  '知悉平台可对音频内容、音色用途进行核查，违规音色会直接下架。',
];

export function PathCPage() {
  const [activeTab, setActiveTab] = useState<'library' | 'upload' | 'clone'>('library');
  const [publicVoices, setPublicVoices] = useState<VoiceSample[]>([]);
  const [privateVoices, setPrivateVoices] = useState<VoiceSample[]>([]);
  const [selectedVoice, setSelectedVoice] = useState('');
  const [cloneText, setCloneText] = useState('');
  const [speed, setSpeed] = useState(1.0);
  const [pitchShift, setPitchShift] = useState(0);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneResult, setCloneResult] = useState<CloneResult | null>(null);
  const [uploadUrl, setUploadUrl] = useState('');
  const [uploadName, setUploadName] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [quota, setQuota] = useState<QuotaInfo>({ used: 0, limit: 1, can_clone: true });
  const [queueStatus, setQueueStatus] = useState('');

  useEffect(() => { fetchVoices(); fetchQuota(); }, []);

  const fetchVoices = async () => {
    try {
      const res = await fetch(`${API}/voice/voices`);
      const data: VoiceSample[] = await res.json();
      setPublicVoices(data.filter(v => !v.is_private));
      setPrivateVoices(data.filter(v => v.is_private));
      if (!selectedVoice) {
        const first = data.find(v => !v.is_private);
        if (first) setSelectedVoice(first.id);
      }
    } catch { /* silent */ }
  };

  const fetchQuota = async () => {
    try {
      const res = await fetch(`${API}/voice/clone-quota`);
      const data: QuotaInfo = await res.json();
      setQuota(data);
    } catch { /* silent */ }
  };

  const handleUpload = async () => {
    if (!consentChecked) { alert('请先勾选声音克隆授权协议'); return; }
    if (!uploadUrl) { alert('请输入音频 URL'); return; }
    if (!quota.can_clone) { alert(`本月克隆次数已达上限（${quota.limit}次）`); return; }

    setIsUploading(true);
    setQueueStatus('');
    try {
      const params = new URLSearchParams({ audio_url: uploadUrl, ...(uploadName && { name: uploadName }) });
      const res = await fetch(`${API}/voice/upload?${params}`, { method: 'POST' });

      if (res.status === 400) {
        const err = await res.json();
        alert(`❌ ${err.detail}`);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setQueueStatus(`克隆任务已提交（ID: ${data.voice_id || data.id}），依托 Agnes AI 云端处理，预计数分钟完成，完成后将出现在「我的克隆音色」分组。`);
      fetchVoices();
      fetchQuota();
      setActiveTab('library');
    } catch (e: any) {
      alert(`❌ 上传失败：${e.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleClone = async () => {
    if (!cloneText.trim()) { alert('请输入要合成的文本'); return; }
    if (!selectedVoice) { alert('请选择声音'); return; }

    setIsCloning(true);
    setCloneResult(null);
    try {
      const res = await fetch(`${API}/voice/clone`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_id: selectedVoice, text: cloneText, speed, pitch_shift: pitchShift }),
      });
      if (res.status === 429) { setRateLimited(true); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CloneResult = await res.json();
      setCloneResult(data);
      if (data.success && data.audio_url) new Audio(data.audio_url).play();
    } catch (e: any) {
      alert(`❌ 合成失败：${e.message}`);
    } finally {
      setIsCloning(false);
    }
  };

  const allVoices = [
    ...publicVoices.map(v => ({ ...v, group: '官方音色库' as const })),
    ...privateVoices.map(v => ({ ...v, group: '我的克隆音色' as const })),
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6 bg-gradient-to-r from-orange-400 to-pink-500 bg-clip-text text-transparent">🎤 声音克隆</h1>

      <div className="flex gap-2 mb-6 border-b border-zinc-800">
        {(['library','upload','clone'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-t-lg transition ${activeTab === tab ? 'bg-zinc-800 text-orange-400 border-b-2 border-orange-400' : 'text-zinc-400 hover:text-white'}`}>
            {tab === 'library' ? '🎵 音色库' : tab === 'upload' ? '📤 上传声音' : '🎙️ 克隆合成'}
          </button>
        ))}
      </div>

      {/* === 音色库 === */}
      {activeTab === 'library' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">可用声音</h2>
            <span className="text-xs text-zinc-500">本月克隆 {quota.used}/{quota.limit}</span>
          </div>

          {allVoices.length === 0 ? (
            <div className="card-solid p-10 text-center">
              <div className="text-5xl mb-4">🎤</div>
              <p className="text-secondary mb-2">还没有声音样本</p>
              <p className="text-muted text-sm mb-6">去「上传声音」标签页添加你的第一个声音</p>
              <button onClick={() => setActiveTab('upload')} className="btn-base px-5 py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded-lg font-medium">📤 上传声音</button>
            </div>
          ) : (
            ['官方音色库', '我的克隆音色'].map(group => {
              const groupVoices = allVoices.filter(v => v.group === group);
              if (groupVoices.length === 0) return null;
              return (
                <div key={group}>
                  <h3 className="text-sm text-zinc-500 mb-2 uppercase tracking-wider">{group}</h3>
                  {groupVoices.map(v => (
                    <div key={v.id} onClick={() => setSelectedVoice(v.id)}
                      className={`p-4 rounded-lg border transition cursor-pointer mb-2 ${selectedVoice === v.id ? 'bg-zinc-800 border-orange-400' : 'bg-zinc-900 border-zinc-800 hover:border-zinc-600'}`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="font-medium text-white">{v.name}</h3>
                          <p className="text-sm text-zinc-400">{v.duration}s • {v.created_at?.split('T')[0]}</p>
                        </div>
                        <audio controls src={v.audio_url} className="h-8" />
                      </div>
                      {selectedVoice === v.id && <div className="mt-2 text-xs text-orange-400">✓ 已选择</div>}
                    </div>
                  ))}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* === 上传声音 === */}
      {activeTab === 'upload' && (
        <div className="space-y-4">
          <div className="card-solid p-6">
            <h2 className="text-xl font-semibold mb-1">上传声音样本</h2>
            <p className="text-xs text-zinc-500 mb-4">声音克隆须知：① 仅允许上传本人人声；克隆他人嗓音属于侵权行为，平台会下架音色并封禁账号；② 生成音色仅限您个人在本站使用，不可导出、商用；③ 每位用户每月可免费创建 {quota.limit} 个私有克隆音色（本月已用 {quota.used}/{quota.limit}）。</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-2">音频 URL（3-10 分钟，MP3，单人朗读，无背景杂音）</label>
                <input type="url" value={uploadUrl} onChange={e => setUploadUrl(e.target.value)} placeholder="https://example.com/voice.mp3"
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white" />
                <p className="text-xs text-zinc-500 mt-1">💡 建议使用安静环境录制，清晰朗读日常语句，克隆效果更佳</p>
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">声音名称（可选）</label>
                <input type="text" value={uploadName} onChange={e => setUploadName(e.target.value)} placeholder="我的声音"
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white" />
              </div>

              {/* 协议勾选 */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4 space-y-2">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox" checked={consentChecked} onChange={e => setConsentChecked(e.target.checked)} className="mt-1 accent-orange-400" />
                  <div className="text-xs text-zinc-400 leading-relaxed">
                    <p className="text-white font-medium mb-1">本人郑重声明：</p>
                    {CONSENT_TEXT.map((t, i) => <p key={i} className="mb-1">{i + 1}. {t}</p>)}
                  </div>
                </label>
              </div>

              <button onClick={handleUpload} disabled={isUploading || !uploadUrl || !consentChecked || !quota.can_clone}
                className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed">
                {isUploading ? '⏳ 上传中...' : quota.can_clone ? '📤 上传声音' : '🚫 本月额度已用完'}
              </button>

              {queueStatus && <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-3 text-sm text-green-300">{queueStatus}</div>}
            </div>
          </div>
        </div>
      )}

      {/* === 克隆合成 === */}
      {activeTab === 'clone' && (
        <div className="space-y-4">
          <div className="card-solid p-6">
            <h2 className="text-xl font-semibold mb-4">声音克隆合成</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-2">选择声音</label>
                <select value={selectedVoice} onChange={e => setSelectedVoice(e.target.value)}
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white">
                  <optgroup label="── 官方音色库 ──">
                    {publicVoices.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                  </optgroup>
                  {privateVoices.length > 0 && (
                    <optgroup label="── 我的克隆音色 ──">
                      {privateVoices.map(v => <option key={v.id} value={v.id}>{v.name} 🔒</option>)}
                    </optgroup>
                  )}
                </select>
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">合成文本</label>
                <textarea value={cloneText} onChange={e => setCloneText(e.target.value)} placeholder="输入要合成的文本（最多 1000 字符）" rows={4} maxLength={1000}
                  className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-orange-400 text-white resize-none" />
                <p className="text-xs text-zinc-500 mt-1">{cloneText.length}/1000</p>
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">播放速度：{speed}x</label>
                <input type="range" min="0.5" max="2.0" step="0.1" value={speed} onChange={e => setSpeed(parseFloat(e.target.value))} className="w-full accent-orange-400" />
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">音高偏移：{pitchShift > 0 ? '+' : ''}{pitchShift}</label>
                <input type="range" min="-12" max="12" step="1" value={pitchShift} onChange={e => setPitchShift(parseInt(e.target.value))} className="w-full accent-orange-400" />
              </div>

              <button onClick={handleClone} disabled={isCloning || !cloneText.trim() || !selectedVoice}
                className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed">
                {isCloning ? '⏳ 合成中...' : '🎙️ 开始合成'}
              </button>
            </div>
          </div>

          {cloneResult && (
            <div className={`p-6 rounded-lg ${cloneResult.success ? 'bg-green-900/20 border border-green-500' : 'bg-red-900/20 border border-red-500'}`}>
              <h3 className="text-lg font-semibold mb-2">{cloneResult.success ? '✅ 合成成功' : '❌ 合成失败'}</h3>
              {cloneResult.message && <p className="text-sm text-zinc-300 whitespace-pre-line mb-4">{cloneResult.message}</p>}
              {cloneResult.success && cloneResult.audio_url && (
                <div className="space-y-3">
                  <audio controls src={cloneResult.audio_url} className="w-full" />
                  <p className="text-xs text-zinc-400">时长：{cloneResult.duration}s</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {rateLimited && <RateLimitBanner onDismiss={() => setRateLimited(false)} />}
    </div>
  );
}
