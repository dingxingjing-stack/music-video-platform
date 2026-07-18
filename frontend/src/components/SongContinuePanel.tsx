/**
 * SongContinuePanel — 歌曲续写 + 结构扩展面板
 *
 * P0-1 歌曲续写:
 * - 选择续写起点 (时间滑块)
 * - 风格选项
 * - 时长选择
 * - POST /api/v1/music/continue
 *
 * P0-2 结构扩展:
 * - 段落拖拽排序 (Intro/Verse/Chorus/Bridge/Outro)
 * - 一键添加段落
 * - POST /api/v1/music/extend-structure
 *
 * 深色主题: bg-gray-900, text-white, orange-600 按钮
 */

import { useState, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

interface Section {
  id: string;
  type: SectionType;
  label: string;
  energy: 'low' | 'medium' | 'high';
}

type SectionType = 'Intro' | 'Verse' | 'Chorus' | 'Bridge' | 'Outro';

interface ContinueResult {
  song_id: string;
  continued_song_id: string;
  title: string;
  duration: number;
  status: string;
  audio_url: string | null;
  lyrics: string | null;
}

interface SectionResult {
  name: string;
  start_time: number;
  duration: number;
  energy: string;
}

interface ExtendResult {
  song_id: string;
  new_song_id: string;
  sections: SectionResult[];
  duration: number;
}

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const SECTION_TYPES: { type: SectionType; label: string; energy: 'low' | 'medium' | 'high'; color: string }[] = [
  { type: 'Intro',  label: 'Intro',  energy: 'low',    color: 'bg-blue-500' },
  { type: 'Verse',  label: 'Verse',  energy: 'medium',  color: 'bg-green-500' },
  { type: 'Chorus', label: 'Chorus', energy: 'high',   color: 'bg-orange-500' },
  { type: 'Bridge', label: 'Bridge', energy: 'medium',  color: 'bg-purple-500' },
  { type: 'Outro',  label: 'Outro',  energy: 'low',    color: 'bg-gray-500' },
];

const CONTINUE_STYLES = [
  { id: 'auto',     name: '自动匹配', desc: '保持原曲风格' },
  { id: 'pop',      name: 'Pop',      desc: '流行' },
  { id: 'rock',     name: 'Rock',     desc: '摇滚' },
  { id: 'electronic', name: 'Electronic', desc: '电子' },
  { id: 'jazz',     name: 'Jazz',     desc: '爵士' },
  { id: 'classical', name: 'Classical', desc: '古典' },
  { id: 'hiphop',   name: 'Hip-Hop', desc: '嘻哈' },
  { id: 'ballad',   name: 'Ballad',  desc: '抒情' },
];

const DURATION_OPTIONS = [15, 30, 60, 90, 120, 180, 240];

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

interface Props {
  songId: string;
  songDuration: number; // 原曲总时长 (秒)
  onClose: () => void;
}

export function SongContinuePanel({ songId, songDuration, onClose }: Props) {
  // ----- P0-1: 歌曲续写状态 -----
  const [continueFrom, setContinueFrom] = useState(0);
  const [selectedStyle, setSelectedStyle] = useState('auto');
  const [duration, setDuration] = useState(60);
  const [isContinuing, setIsContinuing] = useState(false);
  const [continueResult, setContinueResult] = useState<ContinueResult | null>(null);
  const [continueError, setContinueError] = useState<string | null>(null);

  // ----- P0-2: 结构扩展状态 -----
  const [sections, setSections] = useState<Section[]>([
    { id: 's1', type: 'Intro',  label: 'Intro',  energy: 'low' },
    { id: 's2', type: 'Verse',  label: 'Verse',  energy: 'medium' },
    { id: 's3', type: 'Chorus', label: 'Chorus', energy: 'high' },
    { id: 's4', type: 'Chorus', label: 'Chorus', energy: 'high' },
    { id: 's5', type: 'Outro',  label: 'Outro',  energy: 'low' },
  ]);
  const [isExtending, setIsExtending] = useState(false);
  const [extendResult, setExtendResult] = useState<ExtendResult | null>(null);
  const [extendError, setExtendError] = useState<string | null>(null);

  // ----- 拖拽状态 -----
  const dragIndexRef = useRef<number | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const API_BASE = 'https://ai-music-backend-8e85.onrender.com';

  // ===========================================================================
  // P0-1 歌曲续写: POST /api/v1/music/continue
  // ===========================================================================
  const handleContinue = useCallback(async () => {
    setIsContinuing(true);
    setContinueError(null);
    setContinueResult(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/music/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          continue_from: continueFrom,
          style: selectedStyle === 'auto' ? null : selectedStyle,
          duration: duration,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
      }

      const data: ContinueResult = await response.json();
      setContinueResult(data);
    } catch (err) {
      setContinueError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setIsContinuing(false);
    }
  }, [songId, continueFrom, selectedStyle, duration, API_BASE]);

  // ===========================================================================
  // P0-2 结构扩展: POST /api/v1/music/extend-structure
  // ===========================================================================
  const handleExtendStructure = useCallback(async () => {
    setIsExtending(true);
    setExtendError(null);
    setExtendResult(null);

    const structureStr = sections.map(s => s.type).join('-');

    try {
      const response = await fetch(`${API_BASE}/api/v1/music/extend-structure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          structure: structureStr,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
      }

      const data: ExtendResult = await response.json();
      setExtendResult(data);
    } catch (err) {
      setExtendError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setIsExtending(false);
    }
  }, [songId, sections, API_BASE]);

  // ===========================================================================
  // 拖拽排序逻辑
  // ===========================================================================

  const handleDragStart = (index: number, e: React.DragEvent) => {
    dragIndexRef.current = { dragIndex }.dragIndex;
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (index: number, e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  };

  const handleDrop = (index: number, e: React.DragEvent) => {
    e.preventDefault();
    const dragIdx = dragIndexRef.current;
    dragIndexRef.current = null;
    setDraggedIndex(null);
    setDragOverIndex(null);

    if (dragIdx === null || dragIdx === index) return;

    setSections(prev => {
      const next = [...prev];
      const [moved] = next.splice(dragIdx, 1);
      next.splice(index, 0, moved);
      return next;
    });
  };

  const handleDragEnd = () => {
    dragIndexRef.current = null;
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // ===========================================================================
  // 段落操作
  // ===========================================================================

  const addSection = (type: SectionType) => {
    const meta = SECTION_TYPES.find(s => s.type === type)!;
    setSections(prev => [
      ...prev,
      {
        id: `s${Date.now()}`,
        type,
        label: meta.label,
        energy: meta.energy,
      },
    ]);
  };

  const removeSection = (id: string) => {
    setSections(prev => prev.filter(s => s.id !== id));
  };

  const moveSection = (index: number, dir: -1 | 1) => {
    setSections(prev => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  // ===========================================================================
  // 格式化时间
  // ===========================================================================
  const formatTime = (seconds: number): string => {
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  const getSectionColor = (type: SectionType): string => {
    return SECTION_TYPES.find(s => s.type === type)?.color ?? 'bg-gray-500';
  };

  // ===========================================================================
  // 渲染
  // ===========================================================================
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gray-900 rounded-2xl p-6 max-w-5xl w-full max-h-[85vh] overflow-auto shadow-2xl border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎵 歌曲续写 & 结构扩展</h2>
            <p className="text-sm text-gray-400 mt-1">
              P0-1 续写创作 · P0-2 段落编排
            </p>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition"
          >
            关闭
          </button>
        </div>

        {/* ================================================================== */}
        {/* P0-1 歌曲续写                                                     */}
        {/* ================================================================== */}
        <div className="mb-8 p-5 bg-gray-800/50 rounded-xl border border-gray-700">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-5 bg-orange-600 rounded-full inline-block"></span>
            歌曲续写
          </h3>

          {/* 续写起点 - 时间滑块 */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-300">
                续写起点
              </label>
              <span className="text-sm font-bold text-orange-500 bg-orange-500/10 px-3 py-1 rounded-lg">
                {formatTime(continueFrom)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(songDuration, 1)}
              step={1}
              value={continueFrom}
              onChange={(e) => setContinueFrom(Number(e.target.value))}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-orange-600"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0:00 (开头)</span>
              <span>原曲时长: {formatTime(songDuration)}</span>
            </div>
          </div>

          {/* 风格选项 */}
          <div className="mb-5">
            <label className="text-sm font-medium text-gray-300 block mb-2">
              风格
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {CONTINUE_STYLES.map(style => (
                <button
                  key={style.id}
                  onClick={() => setSelectedStyle(style.id)}
                  className={`p-3 rounded-lg border-2 transition text-left ${
                    selectedStyle === style.id
                      ? 'border-orange-600 bg-orange-600/10'
                      : 'border-gray-700 bg-gray-800/50 hover:border-gray-500'
                  }`}
                >
                  <div className={`text-sm font-bold ${selectedStyle === style.id ? 'text-orange-400' : 'text-white'}`}>
                    {style.name}
                  </div>
                  <div className="text-xs text-gray-400">{style.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 时长选择 */}
          <div className="mb-5">
            <label className="text-sm font-medium text-gray-300 block mb-2">
              续写时长
            </label>
            <div className="grid grid-cols-4 md:grid-cols-7 gap-2">
              {DURATION_OPTIONS.map(d => (
                <button
                  key={d}
                  onClick={() => setDuration(d)}
                  className={`py-2.5 rounded-lg border-2 transition font-medium text-sm ${
                    duration === d
                      ? 'border-orange-600 bg-orange-600/10 text-orange-400'
                      : 'border-gray-700 bg-gray-800/50 text-white hover:border-gray-500'
                  }`}
                >
                  {d < 60 ? `${d}s` : `${d / 60}min`}
                </button>
              ))}
            </div>
          </div>

          {/* 错误提示 */}
          {continueError && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              ❌ {continueError}
            </div>
          )}

          {/* 续写结果 */}
          {continueResult && (
            <div className="mb-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
              <div className="flex items-center gap-3 mb-3">
                <div className="text-2xl">✅</div>
                <div>
                  <div className="text-green-400 font-bold">续写完成!</div>
                  <div className="text-xs text-gray-400">
                    新歌曲ID: {continueResult.continued_song_id}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-400">标题:</span>
                  <span className="text-white ml-2">{continueResult.title}</span>
                </div>
                <div>
                  <span className="text-gray-400">时长:</span>
                  <span className="text-white ml-2">{formatTime(continueResult.duration)}</span>
                </div>
              </div>
              {continueResult.lyrics && (
                <div className="mt-3 p-3 bg-gray-800/50 rounded-lg text-sm text-gray-300 whitespace-pre-wrap">
                  <div className="text-xs text-gray-500 mb-1">生成歌词:</div>
                  {continueResult.lyrics}
                </div>
              )}
              {continueResult.audio_url && (
                <div className="mt-3">
                  <audio
                    src={`${API_BASE}${continueResult.audio_url}`}
                    controls
                    className="w-full"
                  />
                </div>
              )}
            </div>
          )}

          {/* 执行按钮 */}
          <button
            onClick={handleContinue}
            disabled={isContinuing}
            className="w-full py-4 bg-orange-600 hover:bg-orange-700 text-white rounded-xl font-bold text-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isContinuing ? '🎵 续写中...' : '✨ 开始续写'}
          </button>
        </div>

        {/* ================================================================== */}
        {/* P0-2 结构扩展                                                     */}
        {/* ================================================================== */}
        <div className="p-5 bg-gray-800/50 rounded-xl border border-gray-700">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-5 bg-orange-600 rounded-full inline-block"></span>
            结构扩展
          </h3>

          <p className="text-sm text-gray-400 mb-3">
            拖拽段落进行排序，或使用下方按钮一键添加新段落。
          </p>

          {/* 段落列表 (拖拽排序) */}
          <div className="space-y-2 mb-4">
            {sections.length === 0 && (
              <div className="text-center text-gray-500 py-8 text-sm border-2 border-dashed border-gray-700 rounded-lg">
                暂无段落，请添加新段落
              </div>
            )}
            {sections.map((section, index) => {
              const sectionColor = getSectionColor(section.type);
              const isDragging = draggedIndex === index;
              const isDragOver = dragOverIndex === index && draggedIndex !== index;

              return (
                <div
                  key={section.id}
                  draggable
                  onDragStart={(e) => handleDragStart(index, e)}
                  onDragOver={(e) => handleDragOver(index, e)}
                  onDrop={(e) => handleDrop(index, e)}
                  onDragEnd={handleDragEnd}
                  className={`flex items-center gap-3 p-3 rounded-lg border-2 transition cursor-move ${
                    isDragging
                      ? 'opacity-40 border-orange-600'
                      : isDragOver
                      ? 'border-orange-500 bg-orange-500/5'
                      : 'border-gray-700 bg-gray-800'
                  }`}
                >
                  {/* 拖拽手柄 */}
                  <div className="text-gray-500 text-xl select-none">⠿</div>

                  {/* 段落指示色 */}
                  <div className={`w-2 h-10 ${sectionColor} rounded-full`}></div>

                  {/* 段落信息 */}
                  <div className="flex-1">
                    <div className="text-white font-bold text-sm">{section.label}</div>
                    <div className="text-xs text-gray-400">
                      第 {index + 1} 段 · 能量: {section.energy}
                    </div>
                  </div>

                  {/* 上下移动按钮 */}
                  <div className="flex flex-col gap-1">
                    <button
                      onClick={() => moveSection(index, -1)}
                      disabled={index === 0}
                      className="px-2 py-0.5 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded disabled:opacity-30 disabled:cursor-not-allowed transition"
                    >
                      ▲
                    </button>
                    <button
                      onClick={() => moveSection(index, 1)}
                      disabled={index === sections.length - 1}
                      className="px-2 py-0.5 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded disabled:opacity-30 disabled:cursor-not-allowed transition"
                    >
                      ▼
                    </button>
                  </div>

                  {/* 删除按钮 */}
                  <button
                    onClick={() => removeSection(section.id)}
                    className="px-3 py-1.5 text-xs bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition"
                  >
                    删除
                  </button>
                </div>
              );
            })}
          </div>

          {/* 一键添加段落 */}
          <div className="mb-4">
            <div className="text-xs text-gray-400 mb-2 font-medium">一键添加段落:</div>
            <div className="flex flex-wrap gap-2">
              {SECTION_TYPES.map(s => (
                <button
                  key={s.type}
                  onClick={() => addSection(s.type)}
                  className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg text-sm font-medium border border-gray-700 hover:border-gray-500 transition flex items-center gap-2"
                >
                  <span className={`w-2 h-2 ${s.color} rounded-full`}></span>
                  + {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* 当前结构预览 */}
          <div className="mb-5 p-3 bg-gray-900/50 rounded-lg border border-gray-700">
            <div className="text-xs text-gray-500 mb-1">当前结构:</div>
            <div className="text-sm text-orange-400 font-mono font-bold">
              {sections.map(s => s.type).join(' → ') || '(空)'}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              共 {sections.length} 个段落
            </div>
          </div>

          {/* 错误提示 */}
          {extendError && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              ❌ {extendError}
            </div>
          )}

          {/* 扩展结果 */}
          {extendResult && (
            <div className="mb-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
              <div className="flex items-center gap-3 mb-3">
                <div className="text-2xl">✅</div>
                <div>
                  <div className="text-green-400 font-bold">结构扩展完成!</div>
                  <div className="text-xs text-gray-400">
                    新歌曲ID: {extendResult.new_song_id} · 总时长: {formatTime(extendResult.duration)}
                  </div>
                </div>
              </div>
              <div className="space-y-1">
                {extendResult.sections.map((sec, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm p-2 bg-gray-800/50 rounded">
                    <span className="text-gray-500 w-6 text-right">{i + 1}.</span>
                    <span className="text-white font-medium w-16">{sec.name}</span>
                    <span className="text-gray-400">
                      {formatTime(sec.start_time)} - {formatTime(sec.start_time + sec.duration)}
                    </span>
                    <span className="text-gray-500 ml-auto">
                      {sec.duration}s · {sec.energy}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 执行按钮 */}
          <button
            onClick={handleExtendStructure}
            disabled={isExtending || sections.length === 0}
            className="w-full py-4 bg-orange-600 hover:bg-orange-700 text-white rounded-xl font-bold text-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isExtending ? '🏗️ 扩展中...' : '🏗️ 执行结构扩展'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SongContinuePanel;
