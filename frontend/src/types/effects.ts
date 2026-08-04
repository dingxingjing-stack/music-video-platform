/**
 * 效果器链类型定义
 */

export type EffectType = 
  | 'eq' 
  | 'compressor' 
  | 'reverb' 
  | 'delay' 
  | 'gain'
  | 'chorus'
  | 'flanger'
  | 'phaser'
  | 'distortion'
  | 'filter'
  | 'tremolo'
  | 'bitcrusher';

export interface EQParams {
  low: number;   // -12 to +12 dB
  mid: number;   // -12 to +12 dB
  high: number;  // -12 to +12 dB
}

export interface CompressorParams {
  threshold: number; // -60 to 0 dB
  ratio: number;     // 1:1 to 20:1
  attack: number;    // 0.001 to 1 sec
  release: number;   // 0.01 to 2 sec
  knee: number;      // 0 to 40 dB
}

export interface ReverbParams {
  wet: number;    // 0 to 1
  decay: number;  // 0.1 to 10 sec
  preDelay: number; // 0 to 0.5 sec
}

export interface DelayParams {
  wet: number;      // 0 to 1
  time: number;     // 0 to 2 sec
  feedback: number; // 0 to 0.99
}

export interface GainParams {
  gain: number; // -∞ to +∞ dB (practically -60 to +20)
}

// P2 新增效果器
export interface ChorusParams {
  wet: number;      // 0 to 1
  rate: number;     // 0.1 to 10 Hz
  depth: number;    // 0 to 1
  delay: number;    // 0.001 to 0.1 sec
}

export interface FlangerParams {
  wet: number;      // 0 to 1
  rate: number;     // 0.1 to 5 Hz
  depth: number;    // 0 to 1
  feedback: number; // -0.9 to 0.9
}

export interface PhaserParams {
  wet: number;      // 0 to 1
  rate: number;     // 0.1 to 5 Hz
  depth: number;    // 0 to 1
  feedback: number; // 0 to 0.9
  stages: number;   // 2, 4, 6, 8
}

export interface DistortionParams {
  drive: number;    // 0 to 100
  tone: number;     // 0 to 1 (lowpass filter)
  wet: number;      // 0 to 1
}

export interface FilterParams {
  type: 'lowpass' | 'highpass' | 'bandpass' | 'notch';
  frequency: number; // 20 to 20000 Hz
  q: number;         // 0.1 to 50
  wet: number;       // 0 to 1
}

export interface TremoloParams {
  rate: number;     // 0.1 to 20 Hz
  depth: number;    // 0 to 1
  wet: number;      // 0 to 1
}

export interface BitcrusherParams {
  bitDepth: number; // 1 to 24 bits
  sampleRate: number; // 1000 to 48000 Hz
  wet: number;      // 0 to 1
}

export interface EffectChain {
  eq: EQParams;
  compressor: CompressorParams;
  reverb: ReverbParams;
  delay: DelayParams;
  gain: GainParams;
  // P2 新增
  chorus: ChorusParams;
  flanger: FlangerParams;
  phaser: PhaserParams;
  distortion: DistortionParams;
  filter: FilterParams;
  tremolo: TremoloParams;
  bitcrusher: BitcrusherParams;
  enabled: {
    eq: boolean;
    compressor: boolean;
    reverb: boolean;
    delay: boolean;
    gain: boolean;
    // P2 新增
    chorus: boolean;
    flanger: boolean;
    phaser: boolean;
    distortion: boolean;
    filter: boolean;
    tremolo: boolean;
    bitcrusher: boolean;
  };
}

export const defaultEffectChain: EffectChain = {
  eq: { low: 0, mid: 0, high: 0 },
  compressor: {
    threshold: -24,
    ratio: 4,
    attack: 0.003,
    release: 0.25,
    knee: 30,
  },
  reverb: {
    wet: 0.3,
    decay: 2.5,
    preDelay: 0.05,
  },
  delay: {
    wet: 0.2,
    time: 0.3,
    feedback: 0.4,
  },
  gain: {
    gain: 0,
  },
  // P2 新增效果器默认值
  chorus: {
    wet: 0.3,
    rate: 1.5,
    depth: 0.5,
    delay: 0.03,
  },
  flanger: {
    wet: 0.3,
    rate: 0.5,
    depth: 0.7,
    feedback: 0.5,
  },
  phaser: {
    wet: 0.4,
    rate: 1.0,
    depth: 0.6,
    feedback: 0.3,
    stages: 4,
  },
  distortion: {
    drive: 30,
    tone: 0.7,
    wet: 0.5,
  },
  filter: {
    type: 'lowpass',
    frequency: 5000,
    q: 1,
    wet: 1.0,
  },
  tremolo: {
    rate: 4.0,
    depth: 0.5,
    wet: 0.5,
  },
  bitcrusher: {
    bitDepth: 16,
    sampleRate: 44100,
    wet: 0.5,
  },
  enabled: {
    eq: false,
    compressor: false,
    reverb: false,
    delay: false,
    gain: false,
    // P2 新增
    chorus: false,
    flanger: false,
    phaser: false,
    distortion: false,
    filter: false,
    tremolo: false,
    bitcrusher: false,
  },
};