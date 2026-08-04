/**
 * MIDI 量化工具
 * 
 * P1-4: 专业级 MIDI 量化功能
 * 支持：
 * - 节奏量化 (Quantize)
 * - 音高量化 (Pitch Correction)
 * - 速度对齐 (Tempo Alignment)
 * - 摇摆量化 (Swing)
 * 
 * 目标：让用户录制的 MIDI 更精准，达到专业水准
 */

export type NoteEvent = {
  pitch: number;      // 音高 (MIDI note number, 0-127)
  velocity: number;   // 力度 (0-127)
  startTime: number;  // 开始时间 (秒)
  duration: number;   // 时长 (秒)
};

export type QuantizePreset = '8th' | '16th' | '32nd' | '8th_triplet' | '16th_triplet';

export interface QuantizeOptions {
  resolution: QuantizePreset;  // 量化精度
  strength: number;             // 量化强度 (0-1, 1=完全量化)
  swing: number;                // 摇摆度 (0-1, 0=无摇摆)
  preserveVelocity: boolean;    // 保留原始力度
  preserveDuration: boolean;    // 保留原始时长
}

/**
 * 量化精度对应的秒数 (基于 BPM)
 */
function getQuantizeGrid(bpm: number, resolution: QuantizePreset): number {
  const beatDuration = 60 / bpm;
  
  switch (resolution) {
    case '8th':
      return beatDuration / 2;
    case '16th':
      return beatDuration / 4;
    case '32nd':
      return beatDuration / 8;
    case '8th_triplet':
      return (beatDuration / 3) / 2;
    case '16th_triplet':
      return (beatDuration / 3) / 4;
    default:
      return beatDuration / 4;
  }
}

/**
 * MIDI 量化主函数
 * 
 * @param notes MIDI 音符数组
 * @param bpm 速度 (BPM)
 * @param options 量化选项
 * @returns 量化后的音符数组
 */
export function quantizeMIDI(
  notes: NoteEvent[],
  bpm: number = 120,
  options: QuantizeOptions = {
    resolution: '16th',
    strength: 1.0,
    swing: 0.0,
    preserveVelocity: true,
    preserveDuration: true,
  }
): NoteEvent[] {
  const grid = getQuantizeGrid(bpm, options.resolution);
  
  return notes.map(note => {
    // 1. 找到最近的网格点
    const rawPosition = note.startTime;
    const gridPosition = Math.round(rawPosition / grid) * grid;
    
    // 2. 应用摇摆 (Swing)
    // 摇摆只应用于非整数拍位置 (如 8 分音符的第二个音符)
    const beatInBar = (rawPosition / (grid * 2)) % 1;
    let swingOffset = 0;
    
    if (beatInBar >= 0.5 && options.swing > 0) {
      // 这是弱拍，应用摇摆延迟
      swingOffset = grid * options.swing * 0.5;
    }
    
    // 3. 计算量化后的位置 (混合原始位置和网格位置)
    const quantizedTime = gridPosition + swingOffset;
    const finalTime = rawPosition + (quantizedTime - rawPosition) * options.strength;
    
    // 4. 构建结果
    const result: NoteEvent = {
      pitch: note.pitch,
      velocity: options.preserveVelocity ? note.velocity : note.velocity,
      startTime: finalTime,
      duration: options.preserveDuration ? note.duration : note.duration,
    };
    
    return result;
  });
}

/**
 * 音高量化 (简单的音高修正)
 * 
 * 将音符量化到最近的合法音高 (基于调性)
 * 
 * @param notes MIDI 音符数组
 * @param scale 音阶 (如 C 大调：[0, 2, 4, 5, 7, 9, 11])
 * @param rootNote 根音 (如 C=0, C#=1, ...)
 * @returns 修正后的音符数组
 */
export function quantizePitch(
  notes: NoteEvent[],
  scale: number[] = [0, 2, 4, 5, 7, 9, 11], // C 大调
  rootNote: number = 0
): NoteEvent[] {
  return notes.map(note => {
    // 1. 计算相对于根音的音程
    const octave = Math.floor(note.pitch / 12);
    const noteInOctave = note.pitch % 12;
    
    // 2. 找到音阶中最近的音
    let closestNote = noteInOctave;
    let minDistance = 12;
    
    for (const scaleNote of scale) {
      const distance = Math.abs(scaleNote - noteInOctave);
      const wrappedDistance = Math.min(distance, 12 - distance);
      
      if (wrappedDistance < minDistance) {
        minDistance = wrappedDistance;
        closestNote = scaleNote;
      }
    }
    
    // 3. 构建修正后的音符
    const correctedPitch = octave * 12 + closestNote;
    
    return {
      ...note,
      pitch: correctedPitch,
    };
  });
}

/**
 * 检测和弦进行
 * 
 * 分析一组音符，识别可能的和弦
 * 
 * @param notes 同时发声的音符
 * @returns 识别的和弦名称 (如 "C", "Cm", "C7", "Cmaj7")
 */
export function detectChord(notes: NoteEvent[]): string | null {
  if (notes.length < 3) {
    return null; // 至少需要 3 个音符才能构成和弦
  }
  
  // 1. 提取音高并去重
  const pitches = [...new Set(notes.map(n => n.pitch % 12))].sort((a, b) => a - b);
  
  if (pitches.length < 3) {
    return null;
  }
  
  // 2. 计算音程
  const intervals = pitches.map((pitch, i) => {
    if (i === 0) return 0;
    return (pitches[i] - pitches[i - 1] + 12) % 12;
  });
  
  // 3. 和弦识别模式
  const chordPatterns: Record<string, string> = {
    '0,4,3': 'minor',        // 小三和弦
    '0,3,4': 'minor (inv)',  // 小三和弦转位
    '0,4,5': 'major (inv)',  // 大三和弦转位
    '0,3,5': 'minor (inv)',  // 小三和弦转位
    '0,4,7': 'major',        // 大三和弦
    '0,3,7': 'minor',        // 小三和弦
    '0,4,8': 'augmented',    // 增三和弦
    '0,3,6': 'diminished',   // 减三和弦
  };
  
  const intervalKey = intervals.join(',');
  const chordType = chordPatterns[intervalKey] || 'unknown';
  
  // 4. 确定根音名称
  const noteNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const rootName = noteNames[pitches[0]];
  
  return `${rootName} ${chordType}`;
}

/**
 * 自动量化 (智能检测 BPM 并应用量化)
 * 
 * @param notes MIDI 音符数组
 * @param estimatedBPM 预估 BPM
 * @returns 量化后的音符数组 + 检测到的 BPM
 */
export function autoQuantize(notes: NoteEvent[], estimatedBPM: number = 120): {
  quantizedNotes: NoteEvent[];
  detectedBPM: number;
} {
  // 1. 从音符间隔检测 BPM
  const onsets = notes.map(n => n.startTime).sort((a, b) => a - b);
  const intervals: number[] = [];
  
  for (let i = 1; i < onsets.length; i++) {
    intervals.push(onsets[i] - onsets[i - 1]);
  }
  
  // 2. 找到最常见的间隔
  const medianInterval = intervals.sort((a, b) => a - b)[Math.floor(intervals.length / 2)];
  const detectedBPM = Math.round(60 / medianInterval);
  
  // 3. 应用量化
  const quantizedNotes = quantizeMIDI(notes, detectedBPM, {
    resolution: '16th',
    strength: 0.9,
    swing: 0.0,
    preserveVelocity: true,
    preserveDuration: true,
  });
  
  return {
    quantizedNotes,
    detectedBPM,
  };
}

// ========== 导出便捷函数 ==========

export default {
  quantizeMIDI,
  quantizePitch,
  detectChord,
  autoQuantize,
};