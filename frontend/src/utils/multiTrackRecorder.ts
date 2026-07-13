/**
 * 多轨录音引擎 (P4-5)
 * 
 * 功能:
 * - 多轨道同步录音
 * - 输入增益控制
 * - 录音电平监控
 * - 录音量化 (自动对齐节拍)
 * - 监听混音
 * - 录音编辑 (裁剪/淡入淡出)
 */

import type { AudioTrack } from '../types/audio';
import type { Project } from '../types/project';

export interface RecordingConfig {
  trackId: string;
  inputDevice: string;
  channels: number;        // 1=mono, 2=stereo
  sampleRate: number;      // 44100/48000/96000
  bitDepth: number;        // 16/24/32 bit
  gain: number;            // 输入增益 (0.0-2.0)
  monitorEnabled: boolean; // 是否开启监听
  quantizeEnabled: boolean;// 是否开启录音量化
  quantizeGrid: number;    // 量化网格 (1/4, 1/8, 1/16...)
  countInBars: number;     // 预备拍小节数
  loopRecording: boolean;  // 循环录音
}

export interface RecordingState {
  isRecording: boolean;
  isPlaying: boolean;
  isPaused: boolean;
  currentBar: number;
  currentBeat: number;
  recordingDuration: number; // 毫秒
  inputLevel: number;        // 输入电平 (L/R)
  outputLevel: number;       // 输出电平 (L/R)
  clipDetected: boolean;     // 是否爆音
  recordedClips: Array<{
    clipId: string;
    trackId: string;
    startTime: number;
    duration: number;
    audioBuffer: AudioBuffer;
  }>;
}

export interface METask {
  name: string;
  description: string;
  icon: string;
  isCompleted: boolean;
}

class MultiTrackRecorder {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private gainNode: GainNode | null = null;
  private analyzerNode: AnalyserNode | null = null;
  private recorder: MediaRecorder | null = null;
  private recordedChunks: Blob[] = [];
  
  private config: RecordingConfig | null = null;
  private state: RecordingState = {
    isRecording: false,
    isPlaying: false,
    isPaused: false,
    currentBar: 1,
    currentBeat: 1,
    recordingDuration: 0,
    inputLevel: 0,
    outputLevel: 0,
    clipDetected: false,
    recordedClips: [],
  };

  private levelUpdateInterval: number | null = null;
  private recordingStartTime: number = 0;

  /** 初始化录音引擎 */
  async initialize(): Promise<void> {
    if (!this.audioContext) {
      this.audioContext = new AudioContext({
        sampleRate: 44100,
        latencyHint: 'interactive',
      });
    }

    // 创建音频节点链
    this.gainNode = this.audioContext.createGain();
    this.analyzerNode = this.audioContext.createAnalyser();
    this.analyzerNode.fftSize = 256;
    this.analyzerNode.smoothingTimeConstant = 0.8;

    // 启动电平监控
    this.startLevelMonitoring();
  }

  /** 请求麦克风权限 */
  async requestMicrophonePermission(): Promise<MediaStream> {
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 2,
          sampleRate: 44100,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      return this.mediaStream;
    } catch (error) {
      console.error('麦克风权限请求失败:', error);
      throw new Error('无法访问麦克风');
    }
  }

  /** 配置录音轨道 */
  async setupTrack(config: RecordingConfig): Promise<void> {
    this.config = config;

    if (!this.mediaStream) {
      await this.requestMicrophonePermission();
    }

    if (!this.audioContext || !this.mediaStream) {
      throw new Error('录音引擎未初始化');
    }

    // 创建音源节点
    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
    
    // 连接节点链：Source -> Gain -> Analyzer
    this.sourceNode.connect(this.gainNode!);
    this.gainNode!.connect(this.analyzerNode!);

    // 设置增益
    this.gainNode.gain.value = config.gain;

    // 设置监听
    if (config.monitorEnabled) {
      this.analyzerNode!.connect(this.audioContext.destination);
    }

    console.log(`✅ 录音轨道 ${config.trackId} 配置完成`);
  }

  /** 开始录音 */
  async startRecording(project: Project): Promise<void> {
    if (!this.config || !this.audioContext) {
      throw new Error('录音未配置');
    }

    this.recordedChunks = [];
    this.recordingStartTime = Date.now();

    // 创建 MediaRecorder
    const dest = this.audioContext.createMediaStreamDestination();
    this.analyzerNode!.connect(dest);

    this.recorder = new MediaRecorder(dest.stream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 320000,
    });

    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.recordedChunks.push(event.data);
      }
    };

    this.recorder.onstop = async () => {
      await this.finalizeRecording(project);
    };

    // 启动录音
    this.recorder.start(1000); // 每秒保存一次数据块
    this.state.isRecording = true;
    this.state.isPlaying = true;
    this.state.isPaused = false;

    // 启动录音计时器
    this.startRecordingTimer();

    console.log('🎙️ 开始录音...');
  }

  /** 停止录音 */
  stopRecording(): void {
    if (this.recorder && this.state.isRecording) {
      this.recorder.stop();
      this.state.isRecording = false;
      this.state.isPlaying = false;
      
      if (this.levelUpdateInterval) {
        clearInterval(this.levelUpdateInterval);
      }

      console.log('⏹️ 录音停止');
    }
  }

  /** 暂停/继续录音 */
  togglePause(): void {
    if (!this.recorder) return;

    if (this.state.isPaused) {
      this.recorder.resume();
      this.state.isPaused = false;
      console.log('▶️ 录音继续');
    } else {
      this.recorder.pause();
      this.state.isPaused = true;
      console.log('⏸️ 录音暂停');
    }
  }

  /** 设置输入增益 */
  setInputGain(gain: number): void {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(2, gain));
    }
  }

  /** 获取当前输入电平 */
  getInputLevel(): { left: number; right: number } {
    if (!this.analyzerNode) {
      return { left: 0, right: 0 };
    }

    const dataArray = new Uint8Array(this.analyzerNode.frequencyBinCount);
    this.analyzerNode.getByteTimeDomainData(dataArray);

    // 计算 RMS
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const sample = (dataArray[i] - 128) / 128;
      sum += sample * sample;
    }
    const rms = Math.sqrt(sum / dataArray.length);

    return {
      left: rms,
      right: rms, // 简化：单声道输入
    };
  }

  /** 检测爆音 */
  checkClipping(dataArray: Uint8Array): boolean {
    for (let i = 0; i < dataArray.length; i++) {
      if (dataArray[i] === 0 || dataArray[i] === 255) {
        return true;
      }
    }
    return false;
  }

  /** 启动电平监控 */
  private startLevelMonitoring(): void {
    if (this.levelUpdateInterval) {
      clearInterval(this.levelUpdateInterval);
    }

    this.levelUpdateInterval = window.setInterval(() => {
      const level = this.getInputLevel();
      this.state.inputLevel = (level.left + level.right) / 2;
      
      // 检查爆音
      if (this.analyzerNode) {
        const dataArray = new Uint8Array(this.analyzerNode.frequencyBinCount);
        this.analyzerNode.getByteTimeDomainData(dataArray);
        this.state.clipDetected = this.checkClipping(dataArray);
      }
    }, 100);
  }

  /** 启动录音计时器 */
  private startRecordingTimer(): void {
    const updateTimer = () => {
      if (!this.state.isRecording || this.state.isPaused) {
        return;
      }

      this.state.recordingDuration = Date.now() - this.recordingStartTime;
      
      // 更新当前小节/拍子 (假设 120 BPM, 4/4 拍)
      const bpm = 120;
      const seconds = this.state.recordingDuration / 1000;
      const beats = (seconds * bpm) / 60;
      this.state.currentBeat = Math.floor(beats % 4) + 1;
      this.state.currentBar = Math.floor(beats / 4) + 1;

      requestAnimationFrame(updateTimer);
    };

    updateTimer();
  }

  /** 完成录音并创建音频片段 */
  private async finalizeRecording(project: Project): Promise<void> {
    if (this.recordedChunks.length === 0 || !this.config) {
      return;
    }

    const blob = new Blob(this.recordedChunks, { type: 'audio/webm;codecs=opus' });
    const arrayBuffer = await blob.arrayBuffer();
    
    if (!this.audioContext) {
      return;
    }

    // 解码为 AudioBuffer
    const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

    // 创建音频片段
    const clip = {
      clipId: `clip_${Date.now()}`,
      trackId: this.config.trackId,
      startTime: 0, // 从第 1 小节开始
      duration: audioBuffer.duration * 1000,
      audioBuffer: audioBuffer,
    };

    this.state.recordedClips.push(clip);

    // 如果启用量化，自动对齐节拍
    if (this.config.quantizeEnabled) {
      this.quantizeClip(clip, this.config.quantizeGrid);
    }

    console.log(`✅ 录音完成：${clip.duration.toFixed(2)}秒`);

    // TODO: 将 clip 添加到项目的轨道中
    // project.addAudioClip(clip);
  }

  /** 录音量化 (自动对齐节拍) */
  private quantizeClip(clip: any, grid: number): void {
    // 简化实现：将 clip 起始时间对齐到最近的网格点
    const gridMs = (60000 / 120) / grid; // 120 BPM
    const quantizedStart = Math.round(clip.startTime / gridMs) * gridMs;
    
    const offset = quantizedStart - clip.startTime;
    if (Math.abs(offset) > 10) { // 大于 10ms 才调整
      clip.startTime = quantizedStart;
      console.log(`📐 量化完成：对齐到 ${grid} 分音符，偏移 ${offset.toFixed(0)}ms`);
    }
  }

  /** 获取录音状态 */
  getState(): RecordingState {
    return { ...this.state };
  }

  /** 清理资源 */
  async dispose(): Promise<void> {
    if (this.recorder) {
      this.recorder.stop();
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
    }

    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }

    if (this.levelUpdateInterval) {
      clearInterval(this.levelUpdateInterval);
    }

    console.log('🧹 录音引擎已清理');
  }
}

// 全局单例
export const multiTrackRecorder = new MultiTrackRecorder();

// 便捷函数
export const initializeRecorder = () => multiTrackRecorder.initialize();
export const setupRecordingTrack = (config: RecordingConfig) => multiTrackRecorder.setupTrack(config);
export const startRecording = (project: Project) => multiTrackRecorder.startRecording(project);
export const stopRecording = () => multiTrackRecorder.stopRecording();
export const pauseRecording = () => multiTrackRecorder.togglePause();
export const setRecordingGain = (gain: number) => multiTrackRecorder.setInputGain(gain);
export const getRecorderState = () => multiTrackRecorder.getState();
export const disposeRecorder = () => multiTrackRecorder.dispose();

export default MultiTrackRecorder;