/**
 * VST 插件系统类型定义
 * 
 * 支持:
 * - VST3 插件加载 (WebAssembly 版本)
 * - 效果器插件 (VST Effects)
 * - 虚拟乐器 (VST Instruments)
 * - 插件预设管理
 * - 参数自动化
 */

// 插件类型
export type PluginType = 'effect' | 'instrument';

// 插件参数类型
export type ParameterType = 'continuous' | 'discrete' | 'toggle';

// 插件参数
export interface PluginParameter {
  id: string;
  name: string;
  value: number; // 0-1
  minValue: number;
  maxValue: number;
  defaultValue: number;
  type: ParameterType;
  unit: string; // 'dB', 'Hz', 'ms', '%'
  steps?: number; // 离散值的步数
}

// 插件信息
export interface PluginInfo {
  id: string;
  name: string;
  vendor: string;
  version: string;
  type: PluginType;
  category: string; // 'EQ', 'Compressor', 'Reverb', 'Synth', 'Sampler'
  description: string;
  parameters: PluginParameter[];
  presetCount: number;
  hasUI: boolean;
  midiChannel?: number;
  uiWidth?: number;
  uiHeight?: number;
}

// 加载的插件实例
export interface LoadedPlugin {
  instanceId: string;
  pluginId: string;
  name: string;
  type: PluginType;
  info?: PluginInfo;
  midiChannel?: number;
  parameters: { [key: string]: number };
  presetIndex: number;
  enabled: boolean;
  bypassed: boolean;
}

// 插件轨道插入
export interface PluginInsert {
  trackId: string;
  slotIndex: number;
  plugin: LoadedPlugin;
}

// 插件预设
export interface PluginPreset {
  id: string;
  pluginId: string;
  name: string;
  parameters: { [key: string]: number };
  isUserPreset: boolean;
}

// 插件扫描结果
export interface PluginScanResult {
  total: number;
  found: PluginInfo[];
  failed: Array<{ path: string; error: string }>;
  scanTime: number; // ms
}

// WebAssembly VST3 宿主配置
export interface WasmVSTConfig {
  wasmPath: string;
  soundfontPath?: string;
  maxPolyphony: number;
  sampleRate: number;
  bufferSize: number;
}

// MIDI 事件
export interface MidiEvent {
  type: 'noteOn' | 'noteOff' | 'controlChange' | 'programChange' | 'pitchBend';
  note?: number; // 0-127
  velocity?: number; // 0-127
  controller?: number;
  value?: number;
  program?: number;
  pitch?: number;
  channel: number; // 0-15
  time: number; // 毫秒
}

// 音频输入配置
export interface AudioInputConfig {
  deviceId?: string;
  channels: number; // 1=mono, 2=stereo
  sampleRate: number;
  bufferSize: number;
  latency: number; // 毫秒
}

// 录音轨道配置
export interface RecordingTrackConfig {
  trackId: string;
  name: string;
  inputType: 'mic' | 'line' | 'instrument' | 'midi';
  inputChannel: number;
  monitoringEnabled: boolean;
  monitoringType: 'off' | 'input' | 'output';
  recordArmed: boolean;
  recordMonitor: boolean;
  inputGain: number; // dB
  phaseReverse: boolean;
  phantomPower: boolean; // 48V
}

// 录音会话
export interface RecordingSession {
  id: string;
  tracks: RecordingTrackConfig[];
  isRecording: boolean;
  startTime: number | null;
  duration: number; // ms
  filePaths: string[];
  midiEvents: MidiEvent[];
}

// 电平表数据
export interface LevelMeterData {
  trackId: string;
  inputLevel: number; // dBFS (-∞ to 0)
  outputLevel: number;
  peakLevel: number;
  rmsLevel: number;
  clipping: boolean;
}

// 监听配置
export interface MonitoringConfig {
  enabled: boolean;
  lowLatency: boolean;
  inputEffectChain: LoadedPlugin[];
  outputEffectChain: LoadedPlugin[];
}

// Quantize 配置
export interface QuantizeConfig {
  enabled: boolean;
  gridType: '1/4' | '1/8' | '1/16' | '1/32' | '1/4T' | '1/8T';
  strength: number; // 0-100%
  swing: number; // 0-100%
  include: {
    notes: boolean;
    velocity: boolean;
    duration: boolean;
  };
}