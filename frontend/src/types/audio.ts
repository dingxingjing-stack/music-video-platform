// 音频类型定义

export interface AudioBuffer {
  sampleRate: number;
  channels: number;
  duration: number;
  data: Float32Array[];
  peaks?: number[];
}

export interface AudioTrack {
  id: string;
  name: string;
  buffer: AudioBuffer;
  volume: number;
  pan: number;
  muted: boolean;
  solo: boolean;
  effects: string[];
  clipStart: number;
  clipEnd: number;
}
