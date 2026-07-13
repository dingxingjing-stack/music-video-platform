/**
 * AIGeneratePanel v2 — AI 音频生成面板（Suno 风格增强版）
 * 
 * 新增功能：
 * - 人声/性别选择 (auto/male/female/instrumental)
 * - 风格滑块控制 (Weirdness + Style Strength)
 * - 歌词编辑器 (自定义歌词 + AI 生成歌词)
 * - 歌曲结构编辑 (Intro/Verse/Chorus/Bridge/Outro 拖拽排列)
 */

import { useState, useCallback } from 'react';

interface Props {
  onGenerated: (audioUrl: string, title: string) => void;
  onClose: () => void;
}

// ─── API 调用 ───────────────────────────────────────
interface GenerateParams {
  prompt: string;
  style: string;
  vocal_type: string;
  weirdness: number;
  style_strength: number;
  duration: number;  // P0-2 长歌曲支持
  structure: string | null;
  lyrics: string | null;
}

interface GenerateResult {
  audio_url: string;
  optimized_prompt?: string;
  generated_lyrics?: string;
  style_suggestions?: string[];
}

async function callGenerateAPI(params: GenerateParams): Promise<GenerateResult> {
  const response = await fetch('http://localhost:8000/api/v1/ai/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`);
  const data = await response.json();
  if (!data.success || !data.audio_url) throw new Error(data.error || '生成失败');
  return {
    audio_url: data.audio_url,
    optimized_prompt: data.optimized_prompt,
    generated_lyrics: data.generated_lyrics,
    style_suggestions: data.style_suggestions,
  };
}

// ─── 歌曲结构类型 ───────────────────────────────────
interface SongSection {
  id: string;
  type: 'intro' | 'verse' | 'chorus' | 'bridge' | 'outro';
  label: string;
}

const DEFAULT_SECTIONS: SongSection[] = [
  { id: 's1', type: 'intro', label: '前奏' },
  { id: 's2', type: 'verse', label: '主歌 1' },
  { id: 's3', type: 'chorus', label: '副歌' },
  { id: 's4', type: 'verse', label: '主歌 2' },
  { id: 's5', type: 'chorus', label: '副歌' },
  { id: 's6', type: 'bridge', label: '桥段' },
  { id: 's7', type: 'outro', label: '尾奏' },
];

const SECTION_COLORS: Record<string, string> = {
  intro: 'from-blue-500/20 to-blue-600/20 border-blue-500/40',
  verse: 'from-green-500/20 to-green-600/20 border-green-500/40',
  chorus: 'from-orange-500/20 to-orange-600/20 border-orange-500/40',
  bridge: 'from-purple-500/20 to-purple-600/20 border-purple-500/40',
  outro: 'from-gray-500/20 to-gray-600/20 border-gray-500/40',
};

const SECTION_TYPES: { value: string; label: string }[] = [
  { value: 'intro', label: '前奏' },
  { value: 'verse', label: '主歌' },
  { value: 'chorus', label: '副歌' },
  { value: 'bridge', label: '桥段' },
  { value: 'outro', label: '尾奏' },
];

const VOCAL_OPTIONS = [
  { value: 'auto', label: '.AUTO', icon: '🎵' },
  { value: 'male', label: '男声', icon: '👨' },
  { value: 'female', label: '女声', icon: '👩' },
  { value: 'instrumental', label: '纯音乐', icon: '🎹' },
];

// ─── 组件 ───────────────────────────────────────────
export function AIGeneratePanel({ onGenerated, onClose }: Props) {
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState('pop');
  const [vocalType, setVocalType] = useState('auto');
  const [weirdness, setWeirdness] = useState(0.5);
  const [styleStrength, setStyleStrength] = useState(0.7);
  const [duration, setDuration] = useState(180); // 默认 3 分钟
  const [lyrics, setLyrics] = useState('');
  const [showLyricsEditor, setShowLyricsEditor] = useState(false);
  const [generatedLyrics, setGeneratedLyrics] = useState('');
  const [sections, setSections] = useState<SongSection[]>(DEFAULT_SECTIONS);
  const [showStructure, setShowStructure] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  const styles = [
    { value: 'pop', label: '流行' }, { value: 'rock', label: '摇滚' },
    { value: 'electronic', label: '电子' }, { value: 'hip-hop', label: '嘻哈' },
    { value: 'r&b', label: 'R&B' }, { value: 'jazz', label: '爵士' },
    { value: 'classical', label: '古典' }, { value: 'ambient', label: '氛围' },
    { value: 'cinematic', label: '电影配乐' }, { value: 'lo-fi', label: 'Lo-Fi' },
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

  // ─── 生成 ─────────────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) { setError('请输入音乐提示词'); return; }
    setIsGenerating(true);
    setProgress(0);
    setError(null);
    setGeneratedLyrics('');

    const interval = setInterval(() => setProgress(p => Math.min(p + 8, 90)), 400);

    try {
      const result = await callGenerateAPI({
        prompt,
        style,
        vocal_type: vocalType,
        weirdness,
        style_strength: styleStrength,
        duration,  // P0-2 长歌曲支持
        structure: showStructure ? JSON.stringify({ sections: sections.map(s => s.type) }) : null,
        lyrics: showLyricsEditor && lyrics.trim() ? lyrics : null,
      });
      clearInterval(interval);
      setProgress(100);
      const title = prompt.length > 20 ? prompt.slice(0, 20) + '...' : prompt;
      if (result.generated_lyrics) setGeneratedLyrics(result.generated_lyrics);
      onGenerated(result.audio_url, title);
      setIsGenerating(false);
    } catch (e) {
      clearInterval(interval);
      setError(e instanceof Error ? e.message : '生成失败');
      setIsGenerating(false);
      setProgress(0);
    }
  }, [prompt, style, vocalType, weirdness, styleStrength, duration, sections, lyrics, showStructure, showLyricsEditor, onGenerated]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[700px] max-h-[85vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">✨ AI 生成音频</h2>
            <p className="text-xs text-[#777777]">输入提示词，AI 自动创作音乐 · Suno 增强版</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* Tab 切换 */}
        <div className="flex border-b border-[#2a2a2a]">
          <button
            onClick={() => setActiveTab('basic')}
            className={`flex-1 px-4 py-2 text-sm font-medium transition ${activeTab === 'basic' ? 'text-orange-400 border-b-2 border-orange-500 bg-[#1a1a1a]' : 'text-[#777777] hover:text-[#e0e0e0]'}`}
          >基础设置</button>
          <button
            onClick={() => setActiveTab('advanced')}
            className={`flex-1 px-4 py-2 text-sm font-medium transition ${activeTab === 'advanced' ? 'text-orange-400 border-b-2 border-orange-500 bg-[#1a1a1a]' : 'text-[#777777] hover:text-[#e0e0e0]'}`}
          >高级控制</button>
        </div>

        {/* 内容区 */}
        <div className="p-4 space-y-4 overflow-auto">
          {/* ── 基础设置 Tab ── */}
          {activeTab === 'basic' && (
            <>
              {/* 提示词 */}
              <div>
                <label className="text-xs text-[#777777] mb-1 block">音乐提示词</label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={'描述你想要的音乐风格、情绪、节奏... 例如：夏日午后，轻松愉悦的流行音乐，轻快的吉他旋律'}
                  className="w-full h-24 bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] resize-none focus:border-orange-500/50"
                  disabled={isGenerating}
                />
              </div>

              {/* 风格选择 */}
              <div>
                <label className="text-xs text-[#777777] mb-1 block">音乐风格</label>
                <div className="grid grid-cols-5 gap-2">
                  {styles.map(s => (
                    <button
                      key={s.value}
                      onClick={() => setStyle(s.value)}
                      className={`px-2 py-1.5 rounded text-xs transition ${style === s.value ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333]'}`}
                      disabled={isGenerating}
                    >{s.label}</button>
                  ))}
                </div>
              </div>

              {/* 人声选择 */}
              <div>
                <label className="text-xs text-[#777777] mb-1 block">人声 / 性别</label>
                <div className="grid grid-cols-4 gap-2">
                  {VOCAL_OPTIONS.map(v => (
                    <button
                      key={v.value}
                      onClick={() => setVocalType(v.value)}
                      className={`px-3 py-2 rounded-lg text-sm transition flex items-center gap-1.5 ${vocalType === v.value ? 'bg-gradient-to-r from-orange-500/30 to-pink-500/30 border border-orange-500/50 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333] border border-transparent'}`}
                      disabled={isGenerating}
                    >
                      <span>{v.icon}</span>
                      <span>{v.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 时长选择 (P0-2 长歌曲支持) */}
              <div>
                <label className="text-xs text-[#777777] mb-1 block">歌曲时长</label>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { value: 120, label: '2 分钟', desc: '短视频' },
                    { value: 180, label: '3 分钟', desc: '标准' },
                    { value: 240, label: '4 分钟', desc: '完整版' },
                    { value: 300, label: '5 分钟', desc: '加长版' },
                  ].map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setDuration(opt.value)}
                      className={`px-2 py-2 rounded-lg text-xs transition flex flex-col items-center gap-0.5 ${duration === opt.value ? 'bg-gradient-to-r from-orange-500/30 to-pink-500/30 border border-orange-500/50 text-white' : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333] border border-transparent'}`}
                      disabled={isGenerating}
                    >
                      <span className="font-medium">{opt.label}</span>
                      <span className="text-[10px] text-[#777777]">{opt.desc}</span>
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <input
                    type="range" min={120} max={480} step={30}
                    value={duration}
                    onChange={e => setDuration(parseInt(e.target.value))}
                    className="flex-1 mr-3 accent-orange-500"
                    disabled={isGenerating}
                  />
                  <span className="text-xs text-orange-400 font-mono w-16 text-right">
                    {Math.floor(duration / 60)}:{(duration % 60).toString().padStart(2, '0')}
                  </span>
                </div>
                <div className="flex justify-between text-[10px] text-[#555555] mt-0.5">
                  <span>2 分钟</span><span>8 分钟</span>
                </div>
              </div>
            </>
          )}

          {/* ── 高级控制 Tab ── */}
          {activeTab === 'advanced' && (
            <>
              {/* 风格滑块 */}
              <div className="space-y-3">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-[#777777]">🎨 风格强度 (Style Strength)</label>
                    <span className="text-xs text-orange-400 font-mono">{Math.round(styleStrength * 100)}%</span>
                  </div>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={styleStrength}
                    onChange={e => setStyleStrength(parseFloat(e.target.value))}
                    className="w-full accent-orange-500"
                    disabled={isGenerating}
                  />
                  <div className="flex justify-between text-[10px] text-[#555555] mt-0.5">
                    <span>通用</span><span>强烈</span>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-[#777777]">🌀 风格偏离度 (Weirdness)</label>
                    <span className="text-xs text-orange-400 font-mono">{Math.round(weirdness * 100)}%</span>
                  </div>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={weirdness}
                    onChange={e => setWeirdness(parseFloat(e.target.value))}
                    className="w-full accent-purple-500"
                    disabled={isGenerating}
                  />
                  <div className="flex justify-between text-[10px] text-[#555555] mt-0.5">
                    <span>标准</span><span>实验性</span>
                  </div>
                </div>
              </div>

              {/* 歌词编辑器 */}
              <div className="border border-[#3a3a3a] rounded-lg">
                <button
                  onClick={() => setShowLyricsEditor(!showLyricsEditor)}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#e0e0e0] hover:bg-[#2a2a2a] transition"
                >
                  <span>📝 歌词编辑器</span>
                  <span className="text-[#777777]">{showLyricsEditor ? '▼' : '▶'}</span>
                </button>
                {showLyricsEditor && (
                  <div className="border-t border-[#3a3a3a] p-3">
                    <textarea
                      value={lyrics}
                      onChange={e => setLyrics(e.target.value)}
                      placeholder="[Verse 1]&#10;在这里输入你的歌词...&#10;用 [Verse] [Chorus] [Bridge] 标记段落"
                      className="w-full h-32 bg-[#2a2a2a] border border-[#3a3a3a] rounded px-2 py-1.5 text-sm text-[#e0e0e0] resize-none focus:border-orange-500/50"
                      disabled={isGenerating}
                    />
                    <p className="text-[10px] text-[#555555] mt-1">留空则使用 AI 自动生成歌词</p>
                    {generatedLyrics && (
                      <div className="mt-2 p-2 bg-[#22c55e]/10 border border-[#22c55e]/20 rounded text-xs text-[#e0e0e0] max-h-32 overflow-auto whitespace-pre-wrap">
                        <span className="text-[#22c55e]">AI 生成歌词：</span><br />
                        {generatedLyrics}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 歌曲结构编辑 */}
              <div className="border border-[#3a3a3a] rounded-lg">
                <button
                  onClick={() => setShowStructure(!showStructure)}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#e0e0e0] hover:bg-[#2a2a2a] transition"
                >
                  <span>🏗️ 歌曲结构编辑</span>
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
                        <span className="text-xs text-[#e0e0e0] flex-1">{s.label}</span>
                        <button
                          onClick={() => moveSection(s.id, 'up')} disabled={idx === 0 || isGenerating}
                          className="text-xs text-[#777777] hover:text-white disabled:opacity-30 px-1 w-6 h-6"
                        >↑</button>
                        <button
                          onClick={() => moveSection(s.id, 'down')} disabled={idx === sections.length - 1 || isGenerating}
                          className="text-xs text-[#777777] hover:text-white disabled:opacity-30 px-1 w-6 h-6"
                        >↓</button>
                        <button
                          onClick={() => removeSection(s.id)} disabled={isGenerating || sections.length <= 1}
                          className="text-xs text-red-400 hover:text-red-300 disabled:opacity-30 px-1 w-6 h-6"
                        >✕</button>
                      </div>
                    ))}
                    {/* 添加段段 */}
                    <div className="flex gap-1 pt-1 flex-wrap">
                      {SECTION_TYPES.map(t => (
                        <button
                          key={t.value}
                          onClick={() => addSection(t.value)}
                          disabled={isGenerating}
                          className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs transition disabled:opacity-30"
                        >+ {t.label}</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* 进度条 */}
          {isGenerating && (
            <div>
              <div className="flex items-center justify-between text-xs text-[#777777] mb-1">
                <span>正在生成...</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-xs text-[#777777] mt-2 text-center">AI 正在创作你的音乐，请稍候...</p>
            </div>
          )}

          {/* 错误 */}
          {error && (
            <div className="p-3 bg-[#ef4444]/20 border border-[#ef4444]/30 rounded text-sm text-[#ef4444]">{error}</div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="p-4 border-t border-[#2a2a2a] flex items-center justify-between">
          <button onClick={onClose} disabled={isGenerating} className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50">取消</button>
          <div className="text-xs text-[#555555]">
            {/* ✅ Enhanced AI Features */}
            {vocalType !== 'auto' || weirdness !== 0.5 || showLyricsEditor || showStructure ? '⚡ 高级模式' : '基础模式'}
          </div>
          <button
            onClick={handleGenerate}
            disabled={isGenerating || !prompt.trim()}
            className="px-6 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            {isGenerating ? '生成中...' : '✨ 生成音频'}
          </button>
        </div>
      </div>
    </div>
  );
}