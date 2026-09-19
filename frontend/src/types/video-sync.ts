/**
 * 音乐功能共享类型定义（原 video-sync.ts 拆分后）
 *
 * 保留：仍被音乐功能实际引用的类型 ——
 *   歌词字幕、歌词样式、节拍标记、音频波形数据。
 *
 * 已移除（MV/视频功能取消）：VideoClip / VideoTrack / TransitionType /
 *   VideoFilter / StockVideo / StockCategory / VideoProject / ExportConfig /
 *   ExportProgress 等纯视频类型（全仓库引用扫描确认已无引用）。
 */

// 歌词字幕
export interface LyricLine {
  id: string;
  text: string;
  startTime: number; // 秒
  endTime: number; // 秒
  trackId: string;
  style: LyricStyle;
}

// 歌词样式
export interface LyricStyle {
  fontSize: number; // 像素
  fontFamily: string;
  color: string;
  backgroundColor?: string;
  position: 'top' | 'center' | 'bottom';
  offsetY: number; // 垂直偏移
  animation: 'none' | 'karaoke' | 'scroll';
}

// 节拍标记
export interface BeatMarker {
  time: number; // 秒
  type: 'beat' | 'downbeat' | 'bar';
  strength: number; // 0-1
  label?: string;
}

// 音频波形数据
export interface WaveformData {
  channels: number;
  sampleRate: number;
  duration: number;
  samples: Float32Array[];
  peaks: number[]; // 用于可视化的简化数据
}