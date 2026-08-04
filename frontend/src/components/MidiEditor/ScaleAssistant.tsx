/**
 * ScaleAssistant — 音阶辅助组件
 * 
 * 功能:
 * - 选择根音和音阶类型
 * - 高亮显示音阶内音符
 * - 自动修正错音选项
 * - MIDI 键盘可视化
 */

import { useState, useCallback } from 'react';
import {
  SCALES,
  getScaleVisualNotes,
  type ScaleType,
} from '../../utils/scaleAssistant';

const ROOT_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

interface Props {
  enabled: boolean;
  rootNote: string;
  scaleType: ScaleType;
  autoQuantize: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onRootNoteChange: (note: string) => void;
  onScaleTypeChange: (type: ScaleType) => void;
  onAutoQuantizeChange: (auto: boolean) => void;
}

export function ScaleAssistant({
  enabled,
  rootNote,
  scaleType,
  autoQuantize,
  onEnabledChange,
  onRootNoteChange,
  onScaleTypeChange,
  onAutoQuantizeChange,
}: Props) {
  const [showKeyboard, setShowKeyboard] = useState(false);

  // 获取当前音阶的音符
  const scaleNotes = getScaleVisualNotes(rootNote, scaleType);

  // 检查单个音符是否在音阶内
  const checkNote = useCallback((noteIndex: number) => {
    const noteName = ROOT_NOTES[noteIndex];
    return scaleNotes.includes(noteName);
  }, [scaleNotes]);

  return (
    <div className="bg-[#1a1a1a] rounded-xl p-4 border border-[#2a2a2a]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-lg">🎹</span>
          <div>
            <h3 className="text-white font-medium">音阶辅助</h3>
            <p className="text-xs text-[#777777]">防止弹错音，自动修正到音阶内</p>
          </div>
        </div>
        <button
          onClick={() => onEnabledChange(!enabled)}
          className={`px-3 py-1 rounded text-sm font-medium transition ${
            enabled
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
              : 'bg-[#2a2a2a] text-[#777777]'
          }`}
        >
          {enabled ? '已启用' : '已禁用'}
        </button>
      </div>

      {enabled && (
        <>
          {/* 设置选项 */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            {/* 根音选择 */}
            <div>
              <label className="text-xs text-[#777777] mb-1 block">根音</label>
              <select
                value={rootNote}
                onChange={(e) => onRootNoteChange(e.target.value)}
                className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded px-2 py-1.5 text-sm text-white"
              >
                {ROOT_NOTES.map(note => (
                  <option key={note} value={note}>{note}</option>
                ))}
              </select>
            </div>

            {/* 音阶类型 */}
            <div>
              <label className="text-xs text-[#777777] mb-1 block">音阶</label>
              <select
                value={scaleType}
                onChange={(e) => onScaleTypeChange(e.target.value as ScaleType)}
                className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded px-2 py-1.5 text-sm text-white"
              >
                {(Object.keys(SCALES) as ScaleType[]).map((key) => (
                  <option key={key} value={key}>{SCALES[key].name}</option>
                ))}
              </select>
            </div>

            {/* 自动修正 */}
            <div>
              <label className="text-xs text-[#777777] mb-1 block">自动修正</label>
              <button
                onClick={() => onAutoQuantizeChange(!autoQuantize)}
                className={`w-full px-3 py-1.5 rounded text-sm font-medium transition ${
                  autoQuantize
                    ? 'bg-purple-500 text-white'
                    : 'bg-[#2a2a2a] text-[#777777]'
                }`}
              >
                {autoQuantize ? '开启 ✓' : '关闭 ✕'}
              </button>
            </div>
          </div>

          {/* 音阶可视化 */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-[#777777]">音阶内音符:</p>
              <button
                onClick={() => setShowKeyboard(!showKeyboard)}
                className="text-xs text-purple-400 hover:text-purple-300"
              >
                {showKeyboard ? '隐藏键盘' : '显示键盘'}
              </button>
            </div>
            <div className="flex gap-1 flex-wrap">
              {scaleNotes.map((note: string, i: number) => (
                <div
                  key={i}
                  className="w-8 h-8 rounded bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold"
                >
                  {note}
                </div>
              ))}
            </div>
          </div>

          {/* MIDI 键盘预览 */}
          {showKeyboard && (
            <div className="bg-[#2a2a2a] rounded-lg p-3">
              <div className="grid grid-cols-12 gap-1">
                {ROOT_NOTES.map((note, idx) => {
                  const isInScale = checkNote(idx);
                  return (
                    <div
                      key={note}
                      className={`h-12 rounded flex items-end justify-center pb-1 text-xs ${
                        isInScale
                          ? 'bg-gradient-to-b from-purple-500 to-pink-500 text-white font-bold'
                          : 'bg-[#3a3a3a] text-[#555555]'
                      }`}
                    >
                      {note}
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-[#777777] mt-2 text-center">
                彩色 = 音阶内音符 · 灰色 = 音阶外音符
              </p>
            </div>
          )}

          {/* 提示信息 */}
          <div className="mt-3 p-2 bg-purple-500/10 border border-purple-500/20 rounded-lg">
            <p className="text-xs text-purple-300">
              💡 提示: 启用"自动修正"后，MIDI 输入会自动调整到最近的音阶内音符
            </p>
          </div>
        </>
      )}
    </div>
  );
}

export default ScaleAssistant;