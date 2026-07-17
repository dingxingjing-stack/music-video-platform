/**
 * 视频同步功能类型定义
 * 
 * 功能:
 * - 视频时间轴编辑
 * - 音频波形显示
 * - 歌词字幕同步
 * - 节拍检测
 * - 视频素材库
 * - 转场效果
 * - FFmpeg.wasm 合成
 */

// 视频剪辑
export interface VideoClip {
  id: string;
  name: string;
  url: string; // 本地文件 URL 或远程 URL
  thumbnailUrl?: string;
  duration: number; // 秒
  startTime: number; // 在时间轴上的开始时间
  endTime: number; // 在时间轴上的结束时间
  trackId: string; // 所属轨道
  transitionIn?: TransitionType; // 入场转场
  transitionOut?: TransitionType; // 出场转场
  filter?: VideoFilter; // 滤镜
  volume: number; // 0-1
}

// 视频轨道
export interface VideoTrack {
  id: string;
  name: string;
  color: string;
  visible: boolean;
  locked: boolean;
  clips: VideoClip[];
  height: number; // 轨道高度 (像素)
}

// 转场类型
export type TransitionType = 
  | 'none'
  | 'fade'
  | 'crossfade'
  | 'slide-left'
  | 'slide-right'
  | 'slide-up'
  | 'slide-down'
  | 'zoom-in'
  | 'zoom-out'
  | 'dissolve';

// 视频滤镜
export interface VideoFilter {
  brightness: number; // -100 to 100
  contrast: number; // -100 to 100
  saturation: number; // -100 to 100
  hue: number; // 0-360
  blur: number; // 0-20
  sepia: number; // 0-100
  grayscale: number; // 0-100
}

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

// 视频素材
export interface StockVideo {
  id: string;
  title: string;
  description: string;
  url: string;
  thumbnailUrl: string;
  duration: number;
  width: number;
  height: number;
  tags: string[];
  category: string;
  source: 'pexels' | 'pixabay' | 'mixkit' | 'upload';
  license: 'free' | 'premium';
  resolution?: '1080p' | '4K';
  fps?: 24 | 30 | 60;
}

export interface StockCategory {
  id: string;
  name: string;
  icon: string;
  count: number;
}

// 项目配置
export interface VideoProject {
  id: string;
  name: string;
  width: number; // 输出宽度 (1920 for 1080p)
  height: number; // 输出高度 (1080 for 1080p)
  fps: number; // 帧率 (24/30/60)
  audioFile?: string; // 音频文件 URL
  tracks: VideoTrack[];
  lyrics: LyricLine[];
  beatMarkers: BeatMarker[];
  waveformData?: WaveformData;
  createdAt: number;
  updatedAt: number;
}

// 导出配置
export interface ExportConfig {
  format: 'mp4' | 'webm' | 'gif';
  quality: 'low' | 'medium' | 'high' | 'ultra';
  resolution: '480p' | '720p' | '1080p' | '4k';
  fps: number;
  includeLyrics: boolean;
  includeWatermark: boolean;
  includeAudio?: boolean;
  watermarkText?: string;
}

// 导出进度
export interface ExportProgress {
  status: 'pending' | 'encoding' | 'completed' | 'error';
  progress: number; // 0-100
  message?: string;
  error?: string;
  outputUrl?: string;
}