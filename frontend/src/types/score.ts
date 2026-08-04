/**
 * 乐谱编辑类型定义
 * 
 * 支持:
 * - 五线谱显示 (Staff Notation)
 * - 简谱显示 (Numbered Notation)
 * - MIDI 音符编辑
 * - 和弦符号
 * - 节拍/调号
 */

// 音符名称 (C D E F G A B)
export type NoteName = 'C' | 'D' | 'E' | 'F' | 'G' | 'A' | 'B';

// 变音记号
export type Accidental = 'natural' | 'sharp' | 'flat' | 'double-sharp' | 'double-flat';

// 音符时值
export type NoteDuration = 'whole' | 'half' | 'quarter' | 'eighth' | 'sixteenth' | 'thirty-second';

// 五线谱位置 (linenumber: 1=底线, 5=顶线, 6=上加一线...)
export type StaffPosition = number;

// 单个音符
export interface Note {
  id: string;
  // 音高
  noteName: NoteName;
  octave: number; // 4=中央 C 所在八度
  accidental?: Accidental;
  
  // 时值
  duration: NoteDuration;
  dotted?: boolean; // 附点
  
  // 位置
  staffPosition: StaffPosition; // 在五线谱上的位置
  x: number; // 水平位置 (像素)
  
  // 状态
  selected?: boolean;
  velocity?: number; // MIDI 力度 (0-127)
  
  // 连音线
  tied?: boolean;
}

// 节拍
export type TimeSignature = '4/4' | '3/4' | '2/4' | '6/8' | '9/8' | '12/8';

// 调号
export type KeySignature = 
  | 'C' | 'G' | 'D' | 'A' | 'E' | 'B' | 'F#' | 'C#' // 升号调
  | 'F' | 'Bb' | 'Eb' | 'Ab' | 'Db' | 'Gb' | 'Cb' | 'Fm'; // 降号调

// 小节
export interface Measure {
  number: number;
  notes: Note[];
  timeSignature?: TimeSignature;
  keySignature?: KeySignature;
}

// 谱表类型
export type StaffType = 'treble' | 'bass' | 'alto' | 'tenor' | 'grand'; // 高音/低音/中音/次中音/大谱表

// 五线谱配置
export interface StaffConfig {
  type: StaffType;
  keySignature: KeySignature;
  timeSignature: TimeSignature;
  tempo: number; // BPM
  measures: Measure[];
}

// MIDI 事件
export interface MidiEvent {
  type: 'noteOn' | 'noteOff' | 'controlChange' | 'pitchBend';
  note?: number; // 0-127
  velocity?: number; // 0-127
  time: number; // 毫秒
  track?: number;
}

// MIDI 文件元数据
export interface MidiMeta {
  title?: string;
  artist?: string;
  tempo?: number;
  timeSignature?: TimeSignature;
  keySignature?: KeySignature;
  tracks: number;
  duration: number; // 毫秒
}

// 钢琴卷帘状态
export interface PianoRollState {
  selectedNotes: string[]; // Note ID 列表
  loopStart: number; // 小节
  loopEnd: number;
  zoom: number; // 缩放级别
  snapToGrid: NoteDuration; // 吸附网格
}

// 和弦
export interface ChordSymbol {
  root: NoteName;
  accidental?: Accidental;
  quality: 'major' | 'minor' | 'diminished' | 'augmented' | '7' | 'maj7' | 'm7';
  inversion?: number; // 转位
  x: number; // 水平位置
  measure: number; // 小节号
}

// 导出格式
export type ExportFormat = 'musicxml' | 'midi' | 'pdf' | 'png' | 'svg';