/**
 * 乐谱编辑器页面
 * 
 * 功能:
 * - 五线谱视图
 * - 钢琴卷帘视图
 * - 工具栏 (音符时值选择、调号、节拍)
 * - 播放控制
 * - 导入/导出
 */

import { useState } from 'react';
import { ScoreStaff } from '../components/ScoreStaff';
import { PianoRoll } from '../components/PianoRoll';
import { Note, StaffConfig, TimeSignature, KeySignature, NoteDuration } from '../types/score';

// 工具栏按钮
const TOOLS = [
  { id: 'select', icon: '🖱️', label: '选择' },
  { id: 'pencil', icon: '✏️', label: '绘制' },
  { id: 'eraser', icon: '🧹', label: '擦除' },
  { id: 'tie', icon: '🔗', label: '连音线' },
] as const;

const DURATIONS: NoteDuration[] = ['whole', 'half', 'quarter', 'eighth', 'sixteenth', 'thirty-second'];

export function ScoreEditorPage() {
  // 编辑器状态
  const [activeTool, setActiveTool] = useState<'select' | 'pencil' | 'eraser' | 'tie'>('select');
  const [selectedDuration, setSelectedDuration] = useState<NoteDuration>('quarter');
  const [activeView, setActiveView] = useState<'staff' | 'piano' | 'both'>('both');
  
  // 乐谱配置
  const [config, setConfig] = useState<StaffConfig>({
    type: 'treble',
    keySignature: 'C',
    timeSignature: '4/4',
    tempo: 120,
    measures: Array(8).fill(null).map((_, i) => ({
      number: i,
      notes: [] as Note[]
    }))
  });

  // 播放状态
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(0);

  // 处理音符点击
  const handleNoteClick = (note: Note) => {
    if (activeTool === 'eraser') {
      // 删除音符
      const updatedMeasures = config.measures.map(m => ({
        ...m,
        notes: m.notes.filter(n => n.id !== note.id)
      }));
      setConfig({ ...config, measures: updatedMeasures });
    }
  };

  // 播放控制
  const handlePlay = () => {
    setIsPlaying(true);
    // 简化实现：模拟播放
    const interval = setInterval(() => {
      setPlaybackTime(prev => prev + 100);
    }, 100);
    
    setTimeout(() => {
      clearInterval(interval);
      setIsPlaying(false);
      setPlaybackTime(0);
    }, 5000); // 播放 5 秒
  };

  // 导出乐谱
  const handleExport = async (format: string) => {
    console.log('Exporting score as', format);
    // 实际实现需要调用后端 API 或使用库
  };

  return (
    <div className="min-h-screen bg-[#121212] text-[#e0e0e0] p-4">
      {/* ===== 顶部工具栏 ===== */}
      <div className="bg-[#1e1e1e] rounded-lg p-3 mb-4 flex items-center gap-4">
        {/* 工具选择 */}
        <div className="flex items-center gap-2 border-r border-[#2a2a2a] pr-4">
          {TOOLS.map(tool => (
            <button
              key={tool.id}
              onClick={() => setActiveTool(tool.id as any)}
              className={`px-3 py-2 rounded-lg text-sm flex items-center gap-2 ${
                activeTool === tool.id
                  ? 'bg-gradient-to-r from-[#ff6a10]/20 to-[#ee0979]/10 text-white'
                  : 'text-[#888888] hover:text-white hover:bg-white/5'
              }`}
              title={tool.label}
            >
              <span>{tool.icon}</span>
            </button>
          ))}
        </div>

        {/* 音符时值 */}
        <div className="flex items-center gap-2 border-r border-[#2a2a2a] pr-4">
          <span className="text-xs text-[#888888]">时值:</span>
          {DURATIONS.map(dur => (
            <button
              key={dur}
              onClick={() => setSelectedDuration(dur)}
              className={`px-2 py-1 rounded text-xs ${
                selectedDuration === dur
                  ? 'bg-[#ff6a10] text-white'
                  : 'text-[#888888] hover:bg-white/5'
              }`}
            >
              {dur.slice(0, 4)}
            </button>
          ))}
        </div>

        {/* 调号/节拍 */}
        <div className="flex items-center gap-3">
          <select
            value={config.keySignature}
            onChange={(e) => setConfig({ ...config, keySignature: e.target.value as KeySignature })}
            className="bg-[#121212] border border-[#2a2a2a] rounded px-2 py-1 text-sm"
          >
            {['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb'].map(key => (
              <option key={key} value={key}>{key}调</option>
            ))}
          </select>

          <select
            value={config.timeSignature}
            onChange={(e) => setConfig({ ...config, timeSignature: e.target.value as TimeSignature })}
            className="bg-[#121212] border border-[#2a2a2a] rounded px-2 py-1 text-sm"
          >
            {['4/4', '3/4', '2/4', '6/8', '9/8'].map(sig => (
              <option key={sig} value={sig}>{sig}</option>
            ))}
          </select>

          <div className="flex items-center gap-2">
            <span className="text-xs text-[#888888]">BPM:</span>
            <input
              type="number"
              value={config.tempo}
              onChange={(e) => setConfig({ ...config, tempo: parseInt(e.target.value) || 120 })}
              className="w-16 bg-[#121212] border border-[#2a2a2a] rounded px-2 py-1 text-sm"
            />
          </div>
        </div>

        {/* 视图切换 */}
        <div className="flex items-center gap-2 border-l border-[#2a2a2a] pl-4 ml-auto">
          <button
            onClick={() => setActiveView('staff')}
            className={`px-3 py-2 rounded text-sm ${
              activeView === 'staff' ? 'bg-[#ff6a10] text-white' : 'text-[#888888] hover:bg-white/5'
            }`}
          >
            五线谱
          </button>
          <button
            onClick={() => setActiveView('piano')}
            className={`px-3 py-2 rounded text-sm ${
              activeView === 'piano' ? 'bg-[#ff6a10] text-white' : 'text-[#888888] hover:bg-white/5'
            }`}
          >
            钢琴卷帘
          </button>
          <button
            onClick={() => setActiveView('both')}
            className={`px-3 py-2 rounded text-sm ${
              activeView === 'both' ? 'bg-[#ff6a10] text-white' : 'text-[#888888] hover:bg-white/5'
            }`}
          >
            双视图
          </button>
        </div>

        {/* 导出按钮 */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport('musicxml')}
            className="px-3 py-2 bg-[#38bdf8] text-white rounded text-sm hover:opacity-80"
          >
            导出 MusicXML
          </button>
          <button
            onClick={() => handleExport('midi')}
            className="px-3 py-2 bg-[#34d399] text-white rounded text-sm hover:opacity-80"
          >
            导出 MIDI
          </button>
        </div>
      </div>

      {/* ===== 主编辑区 ===== */}
      <div className={`grid gap-4 ${activeView === 'both' ? 'grid-cols-2' : ''}`}>
        {/* 五线谱视图 */}
        {(activeView === 'staff' || activeView === 'both') && (
          <div className="bg-[#1e1e1e] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[#888888] mb-3">五线谱视图</h3>
            <ScoreStaff
              config={config}
              width={activeView === 'both' ? 650 : 1000}
              height={250}
              onNoteClick={handleNoteClick}
            />
          </div>
        )}

        {/* 钢琴卷帘视图 */}
        {(activeView === 'piano' || activeView === 'both') && (
          <div className="bg-[#1e1e1e] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[#888888] mb-3">钢琴卷帘</h3>
            <PianoRoll
              notes={config.measures.flatMap(m => m.notes)}
              width={activeView === 'both' ? 650 : 1000}
              height={300}
              playbackTime={isPlaying ? playbackTime : undefined}
            />
          </div>
        )}
      </div>

      {/* ===== 播放控制 ===== */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-[#1e1e1e] rounded-full px-6 py-3 flex items-center gap-4 shadow-xl border border-[#2a2a2a]">
        <button className="text-[#888888] hover:text-white text-xl">⏮</button>
        <button
          onClick={handlePlay}
          className="w-12 h-12 bg-gradient-to-r from-[#ff6a10] to-[#ee0979] rounded-full flex items-center justify-center text-white hover:opacity-90"
        >
          {isPlaying ? '⏸' : '▶'}
        </button>
        <button className="text-[#888888] hover:text-white text-xl">⏭</button>
        <div className="text-xs text-[#888888] ml-2 font-mono">
          {(playbackTime / 1000).toFixed(2)}s
        </div>
      </div>
    </div>
  );
}