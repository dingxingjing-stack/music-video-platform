/**
 * ChordTrackPanel — 和弦轨道面板
 * 
 * 功能:
 * - 和弦库浏览
 * - 和弦进行生成
 * - 和声编排
 * - 可视化钢琴显示和弦组成音
 */

import { useState, useCallback, useEffect } from 'react';

interface ChordDefinition {
  name: string;
  root: string;
  quality: string;
  intervals: number[];
  notes: string[];
}

interface DetectedChord {
  time: number;
  chord_name: string;
  confidence: number;
  duration: number;
  bass_note?: string;
}

interface ChordProgression {
  chords: DetectedChord[];
  key: string;
  tempo: number;
  total_duration: number;
}

const PROGRESSIONS = {
  pop_basic: '流行基础 (I-V-vi-IV)',
  pop_variant: '流行变体 (I-vi-IV-V)',
  jazz_ii_v_i: '爵士 II-V-I',
  blues_12: '12 小节蓝调',
  emotional: '情感/抒情 (vi-IV-I-V)',
  epic: '史诗/电影',
};

const QUALITY_LABELS: Record<string, string> = {
  major: '大三和弦',
  minor: '小三和弦',
  '7th': '七和弦',
  dim: '减和弦',
  aug: '增和弦',
};

interface Props {
  onClose: () => void;
}

export function ChordTrackPanel({ onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'library' | 'progression' | 'harmony'>('library');
  const [chords, setChords] = useState<ChordDefinition[]>([]);
  const [selectedQuality, setSelectedQuality] = useState<string>('all');
  const [progression, setProgression] = useState<ChordProgression | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // 加载和弦库
  useEffect(() => {
    const loadChords = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/v1/chords/library?quality=${selectedQuality === 'all' ? '' : selectedQuality}`);
        const data = await response.json();
        setChords(data);
      } catch (error) {
        console.error('Failed to load chords:', error);
      }
    };
    
    if (activeTab === 'library') {
      loadChords();
    }
  }, [activeTab, selectedQuality]);

  // 生成和弦进行
  const handleGenerateProgression = useCallback(async () => {
    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append('progression_type', 'pop_basic');
      formData.append('key', 'C');
      formData.append('tempo', '120');
      formData.append('bars', '4');

      const response = await fetch('http://localhost:8000/api/v1/chords/generate', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setProgression(data);
    } catch (error) {
      console.error('Failed to generate progression:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-4xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎸 和弦轨道</h2>
            <p className="text-sm text-zinc-400 mt-1">自动和声编排 + 和弦进行生成</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            关闭
          </button>
        </div>

        {/* Tab 导航 */}
        <div className="flex gap-2 mb-6 border-b border-zinc-800">
          {[
            { id: 'library', label: '🎹 和弦库' },
            { id: 'progression', label: '🎼 和弦进行' },
            { id: 'harmony', label: '🎵 和声编排' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as typeof activeTab)}
              className={`px-4 py-2 rounded-t-lg font-medium transition ${
                activeTab === tab.id
                  ? 'bg-zinc-800 text-white border-b-2 border-purple-500'
                  : 'bg-transparent text-zinc-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 和弦库 Tab */}
        {activeTab === 'library' && (
          <div>
            {/* 筛选器 */}
            <div className="mb-4">
              <label className="text-xs text-zinc-400 mb-1 block">和弦品质</label>
              <div className="flex gap-2 flex-wrap">
                {['all', 'major', 'minor', '7th', 'dim', 'aug'].map(q => (
                  <button
                    key={q}
                    onClick={() => setSelectedQuality(q)}
                    className={`px-3 py-1.5 rounded text-xs font-medium transition ${
                      selectedQuality === q
                        ? 'bg-purple-500 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white'
                    }`}
                  >
                    {q === 'all' ? '全部' : QUALITY_LABELS[q] || q}
                  </button>
                ))}
              </div>
            </div>

            {/* 和弦网格 */}
            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {chords.map((chord) => (
                <div
                  key={chord.name}
                  className="bg-zinc-800/50 rounded-xl p-4 border border-zinc-700 hover:border-purple-500/50 transition cursor-pointer group"
                >
                  <div className="text-center">
                    <div className="text-2xl font-bold text-white mb-1 group-hover:text-purple-400 transition">
                      {chord.name}
                    </div>
                    <div className="text-xs text-zinc-500 mb-2">
                      {QUALITY_LABELS[chord.quality] || chord.quality}
                    </div>
                    <div className="flex justify-center gap-1">
                      {chord.notes.map((note, i) => (
                        <div
                          key={i}
                          className="w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center text-xs text-zinc-300"
                        >
                          {note}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 和弦进行 Tab */}
        {activeTab === 'progression' && (
          <div>
            {/* 进行类型选择 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <h3 className="text-sm font-medium text-white mb-3">选择和弦进行</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(PROGRESSIONS).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => {}}
                    className="p-3 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-left transition"
                  >
                    <div className="text-sm font-medium text-white">{label.split(' ')[0]}</div>
                    <div className="text-xs text-zinc-400 mt-1">{label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* 生成按钮 */}
            <button
              onClick={handleGenerateProgression}
              disabled={isLoading}
              className="w-full px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition disabled:opacity-50"
            >
              {isLoading ? '生成中...' : '🎼 生成和弦进行'}
            </button>

            {/* 结果显示 */}
            {progression && (
              <div className="mt-6">
                <h3 className="text-lg font-bold text-white mb-3">
                  生成的和弦进行 ({progression.key}调，{progression.tempo} BPM)
                </h3>
                <div className="grid grid-cols-4 gap-3">
                  {progression.chords.map((chord, i) => (
                    <div
                      key={i}
                      className="bg-gradient-to-b from-purple-500/20 to-pink-500/20 border border-purple-500/30 rounded-xl p-4 text-center"
                    >
                      <div className="text-3xl font-bold text-white mb-1">{chord.chord_name}</div>
                      <div className="text-xs text-zinc-400">
                        {chord.time.toFixed(1)}s - {(chord.time + chord.duration).toFixed(1)}s
                      </div>
                      <div className="text-xs text-purple-400 mt-2">✓ {chord.confidence * 100 | 0}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 和声编排 Tab */}
        {activeTab === 'harmony' && (
          <div className="text-center py-12 text-zinc-500">
            <div className="text-4xl mb-4">🎵</div>
            <p>和声编排功能开发中...</p>
            <p className="text-xs mt-2">支持柱式/分解/长音三种和声风格</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChordTrackPanel;