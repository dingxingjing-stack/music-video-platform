import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { MidiTrack } from '../types/trackStudio';
import { MidiEditor } from '../components/MidiEditor/MidiEditor';
import { useTranslation } from '../i18n/useTranslation';

function generateTrackId(): string {
  return `track-${Date.now()}`;
}

export function PathDPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<'form' | 'midi'>('form');
  
  // MIDI Track 状态
  const [midiTrack, setMidiTrack] = useState<MidiTrack>({
    id: generateTrackId(),
    name: 'MIDI Track 1',
    instrument: 0, // Acoustic Grand Piano
    channel: 0,
    notes: [],
    color: '#3b82f6',
    solo: false,
    mute: false,
    volume: 1,
    pan: 0,
  });

  const handleStartMidiEditor = useCallback(() => {
    setViewMode('midi');
  }, []);

  const handleBackToForm = useCallback(() => {
    setViewMode('form');
  }, []);

  const handleTrackChange = useCallback((track: MidiTrack) => {
    setMidiTrack(track);
  }, []);

  if (viewMode === 'midi') {
    return (
      <div className="flex-1 flex flex-col h-[calc(100vh-64px)] overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-2 bg-[#1e1e1e] border-b border-[#2a2a2a]">
          <button
            onClick={handleBackToForm}
            className="text-sm text-[#777777] hover:text-white transition"
          >
            ← 返回
          </button>
          <h1 className="text-xl font-bold text-[#e0e0e0]">🎹 MIDI 编辑器</h1>
          <span className="text-xs text-[#777777] ml-2">
            {midiTrack.notes.length} 个音符
          </span>
        </div>
        <MidiEditor track={midiTrack} onTrackChange={handleTrackChange} />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/')} className="text-sm text-[#777777] hover:text-white transition">← {t('common.back') || '返回'}</button>
        <h1 className="text-2xl font-bold gradient-text">路径 D — 原创创作</h1>
      </div>
      <p className="text-sm text-[#777777]">从零开始：MIDI 编辑 + 音频生成 → 完整作品</p>

      {/* Original Creation Form */}
      <section className="rounded-xl border border-[#2a2a2a] bg-[#1e1e1e] p-5 space-y-4">
        <h2 className="font-semibold text-[#e0e0e0]">🎹 MIDI 编辑器</h2>
        <p className="text-xs text-[#777777]">
          使用钢琴卷帘创作 MIDI 旋律，支持 GM 标准 128 种乐器
        </p>
        
        <div className="grid md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-[#777777]">轨道名称</label>
            <input
              type="text"
              value={midiTrack.name}
              onChange={(e) => setMidiTrack({ ...midiTrack, name: e.target.value })}
              className="w-full rounded-lg bg-[#2a2a2a] border border-[#3a3a3a] px-3 py-2 text-sm text-[#e0e0e0]"
              placeholder="Track 1"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs text-[#777777]">当前乐器</label>
            <div className="text-sm text-[#e0e0e0] py-2">
              {midiTrack.instrument === 0 ? 'Acoustic Grand Piano' : `Program ${midiTrack.instrument}`}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm text-[#777777]">
          <span>📝 音符数：<strong className="text-[#e0e0e0]">{midiTrack.notes.length}</strong></span>
          <span>🎵 通道：<strong className="text-[#e0e0e0]">{midiTrack.channel + 1}</strong></span>
        </div>

        <button
          onClick={handleStartMidiEditor}
          className="w-full py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg font-medium transition"
        >
          🎹 打开 MIDI 编辑器
        </button>
      </section>

      {/* Audio Generation Section (placeholder) */}
      <section className="rounded-xl border border-[#2a2a2a] bg-[#1e1e1e] p-5 space-y-4 opacity-50">
        <h2 className="font-semibold text-[#e0e0e0]">🎵 音频生成（待实现）</h2>
        <p className="text-xs text-[#777777]">
          将 MIDI 导出为音频（WAV/MP3），使用 SoundFont 或 AI 模型渲染
        </p>
        <button className="w-full py-2.5 bg-[#2a2a2a] text-[#777777] rounded-lg text-sm cursor-not-allowed" disabled>
          音频生成未实现
        </button>
      </section>
    </div>
  );
}