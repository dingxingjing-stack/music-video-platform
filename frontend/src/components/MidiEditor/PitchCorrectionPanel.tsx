/**
 * PitchCorrectionPanel — 音高修正面板
 * 
 * 功能:
 * - 显示检测到的音符
 * - 选择根音和音阶
 * - 自动/手动修正
 * - 音高曲线可视化 (简化版)
 */

import { useState, useCallback } from 'react';
import { SCALES, type ScaleType } from '../../utils/scaleAssistant';

const ROOT_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

interface PitchNote {
  time: number;
  frequency: number;
  midi_note: number;
  note_name: string;
  confidence: number;
  is_in_scale: boolean;
}

interface Props {
  onClose: () => void;
}

export function PitchCorrectionPanel({ onClose }: Props) {
  const [rootNote, setRootNote] = useState('C');
  const [scaleType, setScaleType] = useState<ScaleType>('major');
  const [autoCorrect, setAutoCorrect] = useState(true);
  const [strength, setStrength] = useState(0.8);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [detectedNotes, setDetectedNotes] = useState<PitchNote[]>([]);
  const [correctedNotes, setCorrectedNotes] = useState<PitchNote[]>([]);

  // 分析音频 (Mock)
  const handleAnalyze = useCallback(async () => {
    setIsAnalyzing(true);
    
    // Mock 分析结果
    setTimeout(() => {
      const mockNotes: PitchNote[] = [
        { time: 0, frequency: 261.63, midi_note: 60, note_name: 'C4', confidence: 0.95, is_in_scale: true },
        { time: 1, frequency: 293.66, midi_note: 62, note_name: 'D4', confidence: 0.92, is_in_scale: true },
        { time: 2, frequency: 329.63, midi_note: 64, note_name: 'E4', confidence: 0.88, is_in_scale: true },
        { time: 3, frequency: 349.23, midi_note: 65, note_name: 'F4', confidence: 0.91, is_in_scale: true },
        { time: 4, frequency: 392.00, midi_note: 67, note_name: 'G4', confidence: 0.94, is_in_scale: true },
      ];
      setDetectedNotes(mockNotes);
      setCorrectedNotes(mockNotes);
      setIsAnalyzing(false);
    }, 1000);
  }, []);

  // 执行修正
  const handleCorrect = useCallback(async () => {
    if (!detectedNotes.length) return;

    setIsAnalyzing(true);
    
    // Mock 修正结果
    setTimeout(() => {
      const corrected = detectedNotes.map(note => ({
        ...note,
        is_in_scale: true,
      }));
      setCorrectedNotes(corrected);
      setIsAnalyzing(false);
    }, 800);
  }, [detectedNotes]);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-3xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎤 音高修正</h2>
            <p className="text-sm text-zinc-400 mt-1">类似 VariAudio 的简易音高调整</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            关闭
          </button>
        </div>

        {/* 设置区域 */}
        <div className="grid grid-cols-4 gap-4 mb-6 p-4 bg-zinc-800/50 rounded-xl">
          {/* 根音选择 */}
          <div>
            <label className="text-xs text-zinc-400 mb-1 block">根音</label>
            <select
              value={rootNote}
              onChange={(e) => setRootNote(e.target.value)}
              className="w-full bg-zinc-700 border border-zinc-600 rounded px-3 py-2 text-sm text-white"
            >
              {ROOT_NOTES.map(note => (
                <option key={note} value={note}>{note}</option>
              ))}
            </select>
          </div>

          {/* 音阶类型 */}
          <div>
            <label className="text-xs text-zinc-400 mb-1 block">音阶</label>
            <select
              value={scaleType}
              onChange={(e) => setScaleType(e.target.value as ScaleType)}
              className="w-full bg-zinc-700 border border-zinc-600 rounded px-3 py-2 text-sm text-white"
            >
              {(Object.keys(SCALES) as ScaleType[]).map(key => (
                <option key={key} value={key}>{SCALES[key].name}</option>
              ))}
            </select>
          </div>

          {/* 修正强度 */}
          <div>
            <label className="text-xs text-zinc-400 mb-1 block">修正强度</label>
            <input
              type="range"
              min="0"
              max="100"
              value={strength * 100}
              onChange={(e) => setStrength(Number(e.target.value) / 100)}
              className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
            />
            <div className="text-xs text-zinc-500 text-center mt-1">{Math.round(strength * 100)}%</div>
          </div>

          {/* 自动修正开关 */}
          <div className="flex items-end">
            <button
              onClick={() => setAutoCorrect(!autoCorrect)}
              className={`w-full px-4 py-2 rounded-lg text-sm font-medium transition ${
                autoCorrect
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                  : 'bg-zinc-700 text-zinc-400'
              }`}
            >
              {autoCorrect ? '自动修正 ✓' : '手动模式'}
            </button>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3 mb-6">
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="flex-1 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg font-medium transition disabled:opacity-50"
          >
            {isAnalyzing ? '分析中...' : detectedNotes.length ? '重新分析' : '分析音高'}
          </button>
          <button
            onClick={handleCorrect}
            disabled={isAnalyzing || detectedNotes.length === 0}
            className="flex-1 px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition disabled:opacity-50"
          >
            {isAnalyzing ? '修正中...' : '执行修正'}
          </button>
        </div>

        {/* 音符列表 */}
        {detectedNotes.length > 0 && (
          <div>
            <h3 className="text-lg font-bold text-white mb-3">检测到的音符 ({detectedNotes.length}个)</h3>
            <div className="grid grid-cols-2 gap-4">
              {/* 原始音符 */}
              <div className="bg-zinc-800/50 rounded-xl p-4">
                <h4 className="text-sm font-medium text-zinc-400 mb-2">原始</h4>
                <div className="space-y-2">
                  {detectedNotes.map((note, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-white font-medium">{note.note_name}</span>
                      <span className="text-zinc-500">{note.frequency.toFixed(1)} Hz</span>
                      <span className="text-zinc-600 text-xs">{note.time.toFixed(1)}s</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 修正后音符 */}
              <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-4">
                <h4 className="text-sm font-medium text-purple-400 mb-2">修正后</h4>
                <div className="space-y-2">
                  {correctedNotes.map((note, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-white font-medium">{note.note_name}</span>
                      <span className="text-zinc-500">{note.frequency.toFixed(1)} Hz</span>
                      <span className="text-purple-400 text-xs">✓ 已修正</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 空状态 */}
        {detectedNotes.length === 0 && (
          <div className="text-center py-12 text-zinc-500">
            <div className="text-4xl mb-4">🎤</div>
            <p>点击"分析音高"开始检测</p>
            <p className="text-xs mt-2">支持 WAV/MP3 格式，自动检测人声/乐器音高</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default PitchCorrectionPanel;