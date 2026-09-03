/**
 * AIGeneratePanel v3 — AI 生成音频面板（异步任务版）
 *
 * 对接后端异步协议（POST /ai/generate -> task_id -> 轮询 /ai/task/{id}），
 * 展示完整阶段：排队中/准备中/生成中(ACE-Step)/分轨中(Demucs)/上传中/完成/失败。
 * 完成后展示 {t('aiGen.fullSong')} + vocals/drums/bass/other 四轨，均可播放与下载；
 * 分轨失败时{t('aiGen.fullSong')}仍可播放/下载，并提供「重试分轨」（不重复扣额度）。
 * 下载统一走后端授权接口返回的短期预签名 URL（X-User-ID 归属校验）。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  useAiMusicTask,
  STAGE_LABEL,
  STEM_NAMES,
  AiStems,
} from '../../hooks/useAiMusicTask';
import { useTranslation } from '../../i18n/useTranslation';

interface Props {
  onGenerated: (audioUrl: string, title: string) => void;
  onClose: () => void;
}

// ─── 歌曲结构类型 ───────────────────────────────────
interface SongSection {
  id: string;
  type: 'intro' | 'verse' | 'chorus' | 'bridge' | 'outro';
  label: string;
}

const DEFAULT_SECTIONS: SongSection[] = [
  { id: 's1', type: 'intro', label: 'section.intro' },
  { id: 's2', type: 'verse', label: 'section.verse1' },
  { id: 's3', type: 'chorus', label: 'section.chorus' },
  { id: 's4', type: 'verse', label: 'section.verse2' },
  { id: 's5', type: 'chorus', label: 'section.chorus' },
  { id: 's6', type: 'bridge', label: 'section.bridge' },
  { id: 's7', type: 'outro', label: 'section.outro' },
];

const SECTION_COLORS: Record<string, string> = {
  intro: 'from-blue-500/20 to-blue-600/20 border-blue-500/40',
  verse: 'from-green-500/20 to-green-600/20 border-green-500/40',
  chorus: 'from-orange-500/20 to-orange-600/20 border-orange-500/40',
  bridge: 'from-purple-500/20 to-purple-600/20 border-purple-500/40',
  outro: 'from-gray-500/20 to-gray-600/20 border-gray-500/40',
};

const SECTION_TYPES: { value: string; label: string }[] = [
  { value: 'intro', label: 'section.intro' },
  { value: 'verse', label: 'section.verse' },
  { value: 'chorus', label: 'section.chorus' },
  { value: 'bridge', label: 'section.bridge' },
  { value: 'outro', label: 'section.outro' },
];

const VOCAL_OPTIONS = [
  { value: 'auto', label: 'vocal.auto', icon: '🎵' },
  { value: 'male', label: 'vocal.male', icon: '👨' },
  { value: 'female', label: 'vocal.female', icon: '👩' },
  { value: 'instrumental', label: 'vocal.instrumental', icon: '🎹' },
];

const DURATION_OPTIONS = [
  { value: 60, label: 'dur.1m', desc: 'dur.short' },
  { value: 120, label: 'dur.2m', desc: 'dur.video' },
  { value: 180, label: 'dur.3m', desc: 'dur.max' },
];

const PROGRESS_STAGES = ['pending', 'processing', 'generating', 'separating', 'uploading'];

export function AIGeneratePanel({ onGenerated, onClose }: Props) {
  const { t } = useTranslation();
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState('pop');
  const [vocalType, setVocalType] = useState('auto');
  const [weirdness, setWeirdness] = useState(0.5);
  const [styleStrength, setStyleStrength] = useState(0.7);
  const [duration, setDuration] = useState(180);
  const [lyrics, setLyrics] = useState('');
  const [showLyricsEditor, setShowLyricsEditor] = useState(false);
  const [generatedLyrics, setGeneratedLyrics] = useState('');
  const [sections, setSections] = useState<SongSection[]>(DEFAULT_SECTIONS);
  const [showStructure, setShowStructure] = useState(false);
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [error, setError] = useState<string | null>(null);

  const { task, loading, submit, retryStems, download } = useAiMusicTask();
  const onGeneratedRef = useRef(onGenerated);
  onGeneratedRef.current = onGenerated;

  const styles = [
    { value: 'pop', label: 'style.pop' }, { value: 'rock', label: 'style.rock' },
    { value: 'electronic', label: 'style.electronic' }, { value: 'hip-hop', label: 'style.hiphop' },
    { value: 'r&b', label: 'style.rnb' }, { value: 'jazz', label: 'style.jazz' },
    { value: 'classical', label: 'style.classical' }, { value: 'ambient', label: 'style.ambient' },
    { value: 'cinematic', label: 'style.cinematic' }, { value: 'lo-fi', label: 'style.lofi' },
  ];

  // ─── 结构操作 ─────────────────────────────────
  const moveSection = useCallback((id: string, dir: 'up' | 'down') => {
    setSections(prev => {
      const idx = prev.findIndex(s => s.id === id);
      if (idx < 0) return prev;
      const newIdx = dir === 'up' ? idx - 1 : idx + 1;
      if (newIdx < 0 || newIdx >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
      return next;
    });
  }, []);

  const removeSection = useCallback((id: string) => {
    setSections(prev => prev.filter(s => s.id !== id));
  }, []);

  const addSection = useCallback((type: string) => {
    const typeInfo = SECTION_TYPES.find(t => t.value === type);
    if (!typeInfo) return;
    const count = sections.filter(s => s.type === type).length;
    setSections(prev => [...prev, {
      id: `s${Date.now()}`,
      type: type as SongSection['type'],
      label: `${typeInfo.label}${count > 0 ? ' ' + (count + 1) : ''}`,
    }]);
  }, [sections]);

  // ─── 生成（异步任务）────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) { setError(t('aiGen.promptRequired')); return; }
    setError(null);
    setGeneratedLyrics('');
    const structure = showStructure ? JSON.stringify({ sections: sections.map(s => s.type) }) : null;
    const lyricsVal = showLyricsEditor && lyrics.trim() ? lyrics : null;
    const taskId = await submit({
      prompt,
      style,
      duration,
      lyrics: lyricsVal,
      type: 'song',
    });
    if (!taskId) {
      // submit 失败时 hook 已写入 task.error
      setError(task.error || t('aiGen.submitFailed'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, style, duration, lyrics, showLyricsEditor, showStructure, sections, submit]);

  // 完成 → 通知父组件（MultiTrackView 添加到音轨），仅触发一次
  useEffect(() => {
    if (task.stage === 'completed' && task.audioUrl) {
      const title = prompt.length > 20 ? prompt.slice(0, 20) + '...' : prompt;
      onGeneratedRef.current(task.audioUrl, title);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.stage, task.audioUrl]);

  // 失败/超限 → 展示错误
  useEffect(() => {
    if (task.stage === 'failed' && task.error) setError(task.error);
  }, [task.stage, task.error]);

  const handleDownload = useCallback(async (file: 'full' | 'vocals' | 'drums' | 'bass' | 'other', fmt = 'mp3') => {
    try {
      const url = await download(file, fmt);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${file === 'full' ? 'song_full' : file}.${fmt}`;
      a.target = '_blank';
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('aiGen.downloadFailed'));
    }
  }, [download]);

  const handleRetryStems = useCallback(async () => {
    setError(null);
    await retryStems();
  }, [retryStems]);

  const inProgress = PROGRESS_STAGES.includes(task.stage);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[720px] max-h-[90vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">✨ {t('aiGen.title')}</h2>
            <p className="text-xs text-[#777777]">{t('aiGen.subtitle')}</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition" disabled={loading}>✕</button>
        </div>

        {/* 结果区（完成后显示） */}
        {task.stage === 'completed' && (
          <div className="p-4 border-b border-[#2a2a2a] bg-[#141414]">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-emerald-400">✅ {t('aiGen.completed')}</h3>
              {task.stemsState === 'failed' && (
                <button
                  onClick={handleRetryStems}
                  disabled={loading || (task.stemRetries ?? 0) >= 1}
                  className="px-3 py-1 text-xs rounded bg-[#2a2a2a] text-orange-400 hover:bg-[#333] disabled:opacity-40"
                >
                  {t('aiGen.retryStems')}{task.stemRetries ? ` (${task.stemRetries}/1)` : ''}
                </button>
              )}
            </div>

            {task.stemsState === 'failed' && (
              <p className="text-xs text-orange-400/90 mb-2">
                ⚠️ {t('aiGen.stemsFailedHint')}
              </p>
            )}
            {task.stemsState === 'skipped' && (
              <p className="text-xs text-[#777777] mb-2">ℹ️ {t('aiGen.stemsSkipped')}</p>
            )}

            {/* {t('aiGen.fullSong')} */}
            <div className="rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] p-3 mb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-[#e0e0e0]">{t('aiGen.fullSong')}</span>
                <div className="flex gap-1.5">
                  <button onClick={() => handleDownload('full', 'mp3')} className="px-2 py-0.5 text-[11px] rounded bg-orange-500/20 text-orange-400 hover:bg-orange-500/30">⬇ MP3</button>
                  <button onClick={() => handleDownload('full', 'wav')} className="px-2 py-0.5 text-[11px] rounded bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333]">⬇ WAV</button>
                </div>
              </div>
              {task.audioUrl && <audio controls src={task.audioUrl} className="w-full h-9" />}
            </div>

            {/* 四轨分轨 */}
            <div className="grid grid-cols-1 gap-2">
              {STEM_NAMES.map(({ key, label, color }) => {
                const url = (task.stems as AiStems | null)?.[key];
                if (!url) return null;
                return (
                  <div key={key} className="rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] p-2.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium" style={{ color }}>{t(label)} ({key})</span>
                      <button onClick={() => handleDownload(key)} className="px-2 py-0.5 text-[11px] rounded bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333]">⬇ {t('aiGen.download')}</button>
                    </div>
                    <audio controls src={url} className="w-full h-9" />
                  </div>
                );
              })}
              {(!task.stems || Object.keys(task.stems).length === 0) && task.stemsState !== 'failed' && (
                <p className="text-xs text-[#777777]">{t('aiGen.noStems')}</p>
              )}
            </div>
          </div>
        )}

        {/* 内容区 */}
        <div className="p-4 space-y-4 overflow-auto">
          {/* 进度 / 状态 */}
          {(inProgress || loading) && (
            <div>
              <div className="flex items-center justify-between text-xs text-[#777777] mb-1">
                <span>{task.stage ? t(STAGE_LABEL[task.stage]) : t('aiGen.submitting')}</span>
                <span>{task.progress}%</span>
              </div>
              <div className="h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all" style={{ width: `${Math.max(4, task.progress || 5)}%` }} />
              </div>
              <p className="text-xs text-[#777777] mt-2 text-center">
                {task.stage === 'generating' && t('aiGen.statusGenerating')}
                {task.stage === 'separating' && t('aiGen.statusSeparating')}
                {task.stage === 'uploading' && t('aiGen.statusUploading')}
                {task.stage === 'pending' && t('aiGen.statusPending')}
                {!task.stage && t('aiGen.statusSubmitting')}
              </p>
            </div>
          )}

          {/* Tab 切换 */}
          <div className="flex border-b border-[#2a2a2a]">
            <button
              onClick={() => setActiveTab('basic')}
              className={`flex-1 px-4 py-2 text-sm font-medium transition ${activeTab === 'basic' ? 'text-orange-400 border-b-2 border-orange-500 bg-[#1a1a1a]' : 'text-[#777777] hover:text-[#e0e0e0]'}`}
            >{t('aiGen.tabBasic')}</button>
            <button
              onClick={() => setActiveTab('advanced')}
              className={`flex-1 px-4 py-2 text-sm font-medium transition ${activeTab === 'advanced' ? 'text-orange-400 border-b-2 border-orange-500 bg-[#1a1a1a]' : 'text-[#777777] hover:text-[#e0e0e0]'}`}
            >{t('aiGen.tabAdvanced')}</button>
          </div>

          {/* ── 基础设置 Tab ── */}
          {activeTab === 'basic' && (
            <>
              <div>
                <label className="text-xs text-[#777777] mb-1 block">{t('aiGen.musicPrompt')}</label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={t('aiGen.promptPlaceholder')}
                  className="w-full h-24 bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] resize-none focus:border-orange-500/50"
                  disabled={inProgress || loading}
                />
              </div>

              <div>
                <label className="text-xs text-[#777777] mb-1 block">{t('aiGen.musicStyle')}</label>
                <div className="grid grid-cols-5 gap-2">
                  {styles.map(s => (
                    <button
                      key={s.value}
                      onClick={() => setStyle(s.value)}
                      className={`px-2 py-1.5 rounded text-xs transition ${style === s.value ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333]'}`}
                      disabled={inProgress || loading}
                    >{t(`aiGen.${s.label}`)}</button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-[#777777] mb-1 block">{t('aiGen.vocalGender')}</label>
                <div className="grid grid-cols-4 gap-2">
                  {VOCAL_OPTIONS.map(v => (
                    <button
                      key={v.value}
                      onClick={() => setVocalType(v.value)}
                      className={`px-3 py-2 rounded-lg text-sm transition flex items-center gap-1.5 ${vocalType === v.value ? 'bg-gradient-to-r from-orange-500/30 to-pink-500/30 border border-orange-500/50 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333] border border-transparent'}`}
                      disabled={inProgress || loading}
                    >
                      <span>{v.icon}</span>
                      <span>{t(`aiGen.${v.label}`)}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-[#777777] mb-1 block">{t('aiGen.songDuration')}</label>
                <div className="grid grid-cols-3 gap-2">
                  {DURATION_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setDuration(opt.value)}
                      className={`px-2 py-2 rounded-lg text-xs transition flex flex-col items-center gap-0.5 ${duration === opt.value ? 'bg-gradient-to-r from-orange-500/30 to-pink-500/30 border border-orange-500/50 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333] border border-transparent'}`}
                      disabled={inProgress || loading}
                    >
                      <span className="font-medium">{t(`aiGen.${opt.label}`)}</span>
                      <span className="text-[10px] text-[#777777]">{t(`aiGen.${opt.desc}`)}</span>
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <input
                    type="range" min={30} max={180} step={15}
                    value={duration}
                    onChange={e => setDuration(parseInt(e.target.value))}
                    className="flex-1 mr-3 accent-orange-500"
                    disabled={inProgress || loading}
                  />
                  <span className="text-xs text-orange-400 font-mono w-16 text-right">
                    {Math.floor(duration / 60)}:{(duration % 60).toString().padStart(2, '0')}
                  </span>
                </div>
              </div>
            </>
          )}

          {/* ── 高级控制 Tab ── */}
          {activeTab === 'advanced' && (
            <>
              <div className="space-y-3">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-[#777777]">{t('aiGen.styleStrength')}</label>
                    <span className="text-xs text-orange-400 font-mono">{Math.round(styleStrength * 100)}%</span>
                  </div>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={styleStrength}
                    onChange={e => setStyleStrength(parseFloat(e.target.value))}
                    className="w-full accent-orange-500"
                    disabled={inProgress || loading}
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-[#777777]">{t('aiGen.weirdness')}</label>
                    <span className="text-xs text-orange-400 font-mono">{Math.round(weirdness * 100)}%</span>
                  </div>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={weirdness}
                    onChange={e => setWeirdness(parseFloat(e.target.value))}
                    className="w-full accent-purple-500"
                    disabled={inProgress || loading}
                  />
                </div>
              </div>

              {/* 歌词编辑器 */}
              <div className="border border-[#3a3a3a] rounded-lg">
                <button
                  onClick={() => setShowLyricsEditor(!showLyricsEditor)}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#e0e0e0] hover:bg-[#2a2a2a] transition"
                  disabled={inProgress || loading}
                >
                  <span>{t('aiGen.lyricsEditor')}</span>
                  <span className="text-[#777777]">{showLyricsEditor ? '▼' : '▶'}</span>
                </button>
                {showLyricsEditor && (
                  <div className="border-t border-[#3a3a3a] p-3">
                    <textarea
                      value={lyrics}
                      onChange={e => setLyrics(e.target.value)}
                      placeholder={t('aiGen.lyricsPlaceholder')}
                      className="w-full h-32 bg-[#2a2a2a] border border-[#3a3a3a] rounded px-2 py-1.5 text-sm text-[#e0e0e0] resize-none focus:border-orange-500/50"
                      disabled={inProgress || loading}
                    />
                    <p className="text-[10px] text-[#555555] mt-1">{t('aiGen.lyricsHint')}</p>
                  </div>
                )}
              </div>

              {/* 歌曲结构编辑 */}
              <div className="border border-[#3a3a3a] rounded-lg">
                <button
                  onClick={() => setShowStructure(!showStructure)}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#e0e0e0] hover:bg-[#2a2a2a] transition"
                  disabled={inProgress || loading}
                >
                  <span>{t('aiGen.structureEditor')}</span>
                  <span className="text-[#777777]">{showStructure ? '▼' : '▶'}</span>
                </button>
                {showStructure && (
                  <div className="border-t border-[#3a3a3a] p-3 space-y-2">
                    {sections.map((s, idx) => (
                      <div
                        key={s.id}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-lg border bg-gradient-to-r ${SECTION_COLORS[s.type]} flex-wrap`}
                      >
                        <span className="text-xs text-[#e0e0e0] w-5 text-center font-mono text-[#555555]">{idx + 1}</span>
                        <span className="text-xs text-[#e0e0e0] flex-1">{t(`aiGen.${s.label}`)}</span>
                        <button
                          onClick={() => moveSection(s.id, 'up')} disabled={idx === 0 || inProgress || loading}
                          className="text-xs text-[#777777] hover:text-white disabled:opacity-30 px-1 w-6 h-6"
                        >↑</button>
                        <button
                          onClick={() => moveSection(s.id, 'down')} disabled={idx === sections.length - 1 || inProgress || loading}
                          className="text-xs text-[#777777] hover:text-white disabled:opacity-30 px-1 w-6 h-6"
                        >↓</button>
                        <button
                          onClick={() => removeSection(s.id)} disabled={inProgress || loading || sections.length <= 1}
                          className="text-xs text-red-400 hover:text-red-300 disabled:opacity-30 px-1 w-6 h-6"
                        >✕</button>
                      </div>
                    ))}
                    <div className="flex gap-1 pt-1 flex-wrap">
                      {SECTION_TYPES.map(t => (
                        <button
                          key={t.value}
                          onClick={() => addSection(t.value)}
                          disabled={inProgress || loading}
                          className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs transition disabled:opacity-30"
                        >+ {t(`aiGen.${t.label}`)}</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* 错误 */}
          {error && (
            <div className="p-3 bg-[#ef4444]/20 border border-[#ef4444]/30 rounded text-sm text-[#ef4444]">{error}</div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="p-4 border-t border-[#2a2a2a] flex items-center justify-between">
          <button onClick={onClose} disabled={inProgress || loading} className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50">
            {task.stage === 'completed' ? t('aiGen.close') : t('aiGen.cancel')}
          </button>
          <div className="text-xs text-[#555555]">
            {task.stage === 'completed'
              ? t('aiGen.generated')
              : (vocalType !== 'auto' || weirdness !== 0.5 || showLyricsEditor || showStructure) ? t('aiGen.advancedMode') : t('aiGen.basicMode')}
          </div>
          <button
            onClick={handleGenerate}
            disabled={inProgress || loading || !prompt.trim()}
            className="px-6 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            {inProgress ? t(STAGE_LABEL[task.stage]) + '...' : task.stage === 'completed' ? t('aiGen.generateAnother') : t('aiGen.generate')}
          </button>
        </div>
      </div>
    </div>
  );
}