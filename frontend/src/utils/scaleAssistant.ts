/**
 * 音阶助手 (Scale Assistant)
 * 
 * 功能:
 * - 定义常用音阶 (大调/小调/五声音阶等)
 * - 检查音符是否属于当前音阶
 * - 提供"安全音符"提示
 * - MIDI 编辑时高亮显示音阶内音符
 */

// 音阶类型定义
export type ScaleType = 
  | 'major'           // 大调
  | 'natural_minor'   // 自然小调
  | 'harmonic_minor'  // 和声小调
  | 'melodic_minor'   // 旋律小调
  | 'major_pentatonic'  // 大调五声
  | 'minor_pentatonic'  // 小调五声
  | 'blues'           // 蓝调
  | 'chromatic';      // 半音阶

// 音调定义 (C, C#, D, ...)
export type Note = string;

// 音阶数据结构
export interface ScaleDefinition {
  name: string;
  intervals: number[];  // 音程 (半音数)
}

// 所有音阶定义
export const SCALES: Record<ScaleType, ScaleDefinition> = {
  major: {
    name: '大调',
    intervals: [0, 2, 4, 5, 7, 9, 11],  // W-W-H-W-W-W-H
  },
  natural_minor: {
    name: '自然小调',
    intervals: [0, 2, 3, 5, 7, 8, 10],  // W-H-W-W-H-W-W
  },
  harmonic_minor: {
    name: '和声小调',
    intervals: [0, 2, 3, 5, 7, 8, 11],  // 自然小调 + 升 7 音
  },
  melodic_minor: {
    name: '旋律小调',
    intervals: [0, 2, 3, 5, 7, 9, 11],  // 上行：升 6、7 音
  },
  major_pentatonic: {
    name: '大调五声',
    intervals: [0, 2, 4, 7, 9],  // 1-2-3-5-6
  },
  minor_pentatonic: {
    name: '小调五声',
    intervals: [0, 3, 5, 7, 10],  // 1-b3-4-5-b7
  },
  blues: {
    name: '蓝调',
    intervals: [0, 3, 5, 6, 7, 10],  // 小调五声 + b5
  },
  chromatic: {
    name: '半音阶',
    intervals: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  // 所有音符
  },
};

// 音调列表 (12 平均律)
const NOTES: Note[] = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

/**
 * 获取指定音调的音阶音符
 * @param rootNote 根音 (如 "C", "D#", "F")
 * @param scaleType 音阶类型
 * @returns 音阶内的所有音符 (MIDI 音符编号 0-127)
 */
export function getScaleNotes(rootNote: Note, scaleType: ScaleType): number[] {
  const rootIndex = NOTES.indexOf(rootNote);
  if (rootIndex === -1) {
    console.warn('Invalid root note:', rootNote);
    return [];
  }

  const intervals = SCALES[scaleType].intervals;
  const scaleNotes: number[] = [];

  // 生成 8 个八度的音阶音符
  for (let octave = 0; octave < 8; octave++) {
    for (const interval of intervals) {
      const noteIndex = (rootIndex + interval) % 12;
      const midiNote = noteIndex + (octave + 1) * 12;  // MIDI: C1=12, C2=24, ...
      if (midiNote <= 127) {
        scaleNotes.push(midiNote);
      }
    }
  }

  return scaleNotes;
}

/**
 * 检查音符是否在音阶内
 * @param midiNote MIDI 音符编号 (0-127)
 * @param rootNote 根音
 * @param scaleType 音阶类型
 * @returns 是否在音阶内
 */
export function isNoteInScale(midiNote: number, rootNote: Note, scaleType: ScaleType): boolean {
  const scaleNotes = getScaleNotes(rootNote, scaleType);
  return scaleNotes.includes(midiNote);
}

/**
 * 获取离指定音符最近的音阶内音符
 * @param midiNote MIDI 音符编号
 * @param rootNote 根音
 * @param scaleType 音阶类型
 * @returns 最近的音阶内音符 (可能与原音符相同)
 */
export function getClosestScaleNote(midiNote: number, rootNote: Note, scaleType: ScaleType): number {
  const scaleNotes = getScaleNotes(rootNote, scaleType);
  if (scaleNotes.length === 0) return midiNote;

  let closest = scaleNotes[0];
  let minDistance = Math.abs(midiNote - closest);

  for (const note of scaleNotes) {
    const distance = Math.abs(midiNote - note);
    if (distance < minDistance) {
      minDistance = distance;
      closest = note;
    }
  }

  return closest;
}

/**
 * 修正音符到音阶内 (自动纠正错音)
 * @param midiNote MIDI 音符编号
 * @param rootNote 根音
 * @param scaleType 音阶类型
 * @returns 修正后的音符
 */
export function quantizeToScale(midiNote: number, rootNote: Note, scaleType: ScaleType): number {
  if (isNoteInScale(midiNote, rootNote, scaleType)) {
    return midiNote;  // 已经在音阶内
  }
  return getClosestScaleNote(midiNote, rootNote, scaleType);
}

/**
 * 获取音阶的可视化信息 (用于 UI 渲染)
 * @param rootNote 根音
 * @param scaleType 音阶类型
 * @returns 音阶内所有音符的名称
 */
export function getScaleVisualNotes(rootNote: Note, scaleType: ScaleType): string[] {
  const rootIndex = NOTES.indexOf(rootNote);
  if (rootIndex === -1) return [];

  const intervals = SCALES[scaleType].intervals;
  return intervals.map(interval => {
    const noteIndex = (rootIndex + interval) % 12;
    return NOTES[noteIndex];
  });
}

export default {
  SCALES,
  getScaleNotes,
  isNoteInScale,
  getClosestScaleNote,
  quantizeToScale,
  getScaleVisualNotes,
};