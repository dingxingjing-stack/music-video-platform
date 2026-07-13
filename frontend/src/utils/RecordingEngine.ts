/**
 * 专业录音引擎
 * 
 * 功能:
 * - 多轨音频录制 (麦克风/线路/乐器)
 * - MIDI 输入录制
 * - 实时监听 (带效果器)
 * - 电平表显示
 * - 量化修正
 * - Comping 支持
 * 
 * 技术架构:
 * - Web Audio API: 音频捕获和处理
 * - Web MIDI API: MIDI 输入
 * - AudioWorklet: 低延迟监听
 */

import {
  RecordingSession,
  RecordingTrackConfig,
  LevelMeterData,
  MidiEvent,
  MonitoringConfig,
  QuantizeConfig
} from '../types/vst';

export class RecordingEngine {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private analyserNodes: Map<string, AnalyserNode> = new Map();
  private sourceNodes: Map<string, MediaStreamAudioSourceNode> = new Map();
  private gainNodes: Map<string, GainNode> = new Map();
  private session: RecordingSession | null = null;
  private recordedChunks: Map<string, Blob[]> = new Map();
  private monitoringConfig: MonitoringConfig;
  private quantizeConfig: QuantizeConfig;
  private midiEvents: MidiEvent[] = [];

  // 录音状态
  private isRecording = false;
  private startTime = 0;
  private animationFrameId: number | null = null;

  constructor() {
    this.monitoringConfig = {
      enabled: true,
      lowLatency: true,
      inputEffectChain: [],
      outputEffectChain: []
    };

    this.quantizeConfig = {
      enabled: false,
      gridType: '1/16',
      strength: 100,
      swing: 0,
      include: {
        notes: true,
        velocity: true,
        duration: true
      }
    };
  }

  /**
   * 初始化录音引擎
   */
  async initialize(sampleRate = 44100): Promise<boolean> {
    try {
      this.audioContext = new AudioContext({ sampleRate });
      console.log('[RecordingEngine] 初始化完成');
      return true;
    } catch (error) {
      console.error('[RecordingEngine] 初始化失败:', error);
      return false;
    }
  }

  /**
   * 获取可用音频输入设备
   */
  async getAudioInputDevices(): Promise<MediaDeviceInfo[]> {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices.filter(device => device.kind === 'audioinput');
    } catch (error) {
      console.error('[RecordingEngine] 获取设备失败:', error);
      return [];
    }
  }

  /**
   * 开始录音 (多轨)
   */
  async startRecording(tracks: RecordingTrackConfig[]): Promise<RecordingSession | null> {
    if (!this.audioContext) {
      console.error('[RecordingEngine] 音频上下文未初始化');
      return null;
    }

    try {
      // 创建录音会话
      this.session = {
        id: `session-${Date.now()}`,
        tracks,
        isRecording: true,
        startTime: Date.now(),
        duration: 0,
        filePaths: [],
        midiEvents: []
      };

      // 为每个轨道设置录音链
      for (const track of tracks) {
        await this.setupRecordingTrack(track);
      }

      // 启动录音
      this.isRecording = true;
      this.startTime = Date.now();
      this.startLevelMetering();

      console.log(`[RecordingEngine] 开始录音: ${tracks.length}轨道`);
      return this.session;
    } catch (error) {
      console.error('[RecordingEngine] 开始录音失败:', error);
      return null;
    }
  }

  /**
   * 停止录音
   */
  async stopRecording(): Promise<RecordingSession | null> {
    if (!this.session || !this.isRecording) {
      return null;
    }

    // 停止所有录制
    this.isRecording = false;
    this.session.isRecording = false;
    this.session.duration = Date.now() - this.startTime;

    // 停止电平表
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    // 停止媒体流
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    console.log(`[RecordingEngine] 停止录音，时长：${this.session.duration}ms`);
    return this.session;
  }

  /**
   * 设置单个录音轨道
   */
  private async setupRecordingTrack(track: RecordingTrackConfig): Promise<void> {
    if (!this.audioContext) return;

    // 创建音频链: Input -> Gain -> Analyser -> Destination
    const analyser = this.audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.3;

    const gainNode = this.audioContext.createGain();
    gainNode.gain.value = this.dbToLinear(track.inputGain || 0);

    this.analyserNodes.set(track.trackId, analyser);
    this.gainNodes.set(track.trackId, gainNode);

    // 如果轨道需要监听
    if (track.monitoringEnabled) {
      this.setupMonitoring(track, analyser);
    }

    console.log(`[RecordingEngine] 设置轨道: ${track.name}`);
  }

  /**
   * 设置实时监听
   */
  private setupMonitoring(track: RecordingTrackConfig, analyser: AnalyserNode): void {
    if (!this.audioContext) return;

    // 低延迟监听模式
    if (this.monitoringConfig.lowLatency) {
      // 直接路由到输出 (最小延迟)
      analyser.connect(this.audioContext.destination);
    } else {
      // 通过效果器链
      // 创建效果器链：Compressor -> EQ -> Reverb
      const inputGain = this.audioContext.createGain();
      const compressor = this.audioContext.createDynamicsCompressor();
      const eq = this.audioContext.createBiquadFilter();
      const outputGain = this.audioContext.createGain();
      
      // 配置效果器参数
      compressor.threshold.value = -50;
      compressor.knee.value = 40;
      compressor.ratio.value = 12;
      compressor.attack.value = 0.003;
      compressor.release.value = 0.25;
      
      eq.type = "peaking";
      eq.frequency.value = 1000;
      eq.Q.value = 1;
      eq.gain.value = 0;
      
      // 连接效果器链
      analyser.connect(inputGain);
      inputGain.connect(compressor);
      compressor.connect(eq);
      eq.connect(outputGain);
      outputGain.connect(this.audioContext.destination);
      
      // 保存效果器引用以便后续调整
      this.gainNodes.set(`${track.id}_input`, inputGain);
      this.gainNodes.set(`${track.id}_output`, outputGain);
    }

    console.log(`[RecordingEngine] 设置监听: ${track.name}, 低延迟=${this.monitoringConfig.lowLatency}`);
  }

  /**
   * 开始电平表检测
   */
  private startLevelMetering(): void {
    const measureLevel = () => {
      if (!this.isRecording) return;

      for (const [trackId, analyser] of this.analyserNodes.entries()) {
        const dataArray = new Float32Array(analyser.frequencyBinCount);
        analyser.getFloatTimeDomainData(dataArray);

        // 计算 RMS
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i] * dataArray[i];
        }
        const rms = Math.sqrt(sum / dataArray.length);
        const db = 20 * Math.log10(Math.max(rms, 0.00001));

        // 检测削波
        let clipping = false;
        for (let i = 0; i < dataArray.length; i++) {
          if (Math.abs(dataArray[i]) > 0.99) {
            clipping = true;
            break;
          }
        }

        // 发送到 UI 更新电平表
        const meterData: LevelMeterData = {
          trackId,
          inputLevel: db,
          outputLevel: db,
          peakLevel: db,
          rmsLevel: db,
          clipping
        };

        // 触发自定义事件 (供外部监听)
        window.dispatchEvent(new CustomEvent('levelmeter', { detail: meterData }));
        
        // 回调通知 (如果注册了)
        if (this.onLevelUpdate) {
          this.onLevelUpdate(meterData);
        }
      }

      // 更新录音时长
      if (this.session) {
        this.session.duration = Date.now() - this.startTime;
      }

      this.animationFrameId = requestAnimationFrame(measureLevel);
    };

    measureLevel();
  }

  /**
   * 开始 MIDI 录音
   */
  async startMidiRecording(): Promise<void> {
    this.midiEvents = [];
    this.isRecording = true;
    this.startTime = Date.now();

    // 监听 MIDI 输入
    if (navigator.requestMIDIAccess) {
      try {
        const midiAccess = await navigator.requestMIDIAccess();
        midiAccess.inputs.forEach(input => {
          input.onmidimessage = (event) => {
            const midiEvent = this.parseMidiMessage(event.data);
            if (midiEvent) {
              midiEvent.time = Date.now() - this.startTime;
              this.midiEvents.push(midiEvent);
            }
          };
        });
        console.log('[RecordingEngine] MIDI 录音已启动');
      } catch (error) {
        console.error('[RecordingEngine] MIDI 访问失败:', error);
      }
    }
  }

  /**
   * 停止 MIDI 录音
   */
  stopMidiRecording(): MidiEvent[] {
    this.isRecording = false;
    console.log(`[RecordingEngine] MIDI 录音停止，录制了 ${this.midiEvents.length} 个事件`);
    return this.midiEvents;
  }

  /**
   * 解析 MIDI 消息
   */
  private parseMidiMessage(data: Uint8Array): MidiEvent | null {
    const [status, note, velocity] = data;
    const channel = status & 0x0f;
    const command = status & 0xf0;

    switch (command) {
      case 0x90: // Note On
        if (velocity > 0) {
          return {
            type: 'noteOn',
            note,
            velocity,
            channel,
            time: Date.now()
          };
        }
        return {
          type: 'noteOff',
          note,
          velocity: 0,
          channel,
          time: Date.now()
        };

      case 0xb0: // Control Change
        return {
          type: 'controlChange',
          controller: note,
          value: velocity,
          channel,
          time: Date.now()
        };

      case 0xc0: // Program Change
        return {
          type: 'programChange',
          program: note,
          channel,
          time: Date.now()
        };

      case 0xe0: // Pitch Bend
        return {
          type: 'pitchBend',
          pitch: (velocity << 7) | note,
          channel,
          time: Date.now()
        };

      default:
        return null;
    }
  }

  /**
   * 量化 MIDI 音符
   */
  quantizeMidiEvents(events: MidiEvent[], config: QuantizeConfig): MidiEvent[] {
    if (!config.enabled) return events;

    // 计算网格值 (毫秒)
    const bpm = 120; // 假设 BPM
    const beatDuration = 60000 / bpm;
    let gridDuration: number;

    switch (config.gridType) {
      case '1/4': gridDuration = beatDuration; break;
      case '1/8': gridDuration = beatDuration / 2; break;
      case '1/16': gridDuration = beatDuration / 4; break;
      case '1/32': gridDuration = beatDuration / 8; break;
      default: gridDuration = beatDuration / 4;
    }

    return events.map(event => {
      if (event.type === 'noteOn' && event.note !== undefined) {
        const originalTime = event.time;
        const gridTime = Math.round(originalTime / gridDuration) * gridDuration;
        
        // 应用强度
        const strength = config.strength / 100;
        event.time = originalTime + (gridTime - originalTime) * strength;
      }
      return event;
    });
  }

  /**
   * 获取当前录音会话
   */
  getSession(): RecordingSession | null {
    return this.session;
  }

  /**
   * 设置监听配置
   */
  setMonitoringConfig(config: MonitoringConfig): void {
    this.monitoringConfig = config;
    console.log('[RecordingEngine] 监听配置已更新');
  }

  /**
   * 设置量化配置
   */
  setQuantizeConfig(config: QuantizeConfig): void {
    this.quantizeConfig = config;
    console.log('[RecordingEngine] 量化配置已更新');
  }

  /**
   * dB 转线性增益
   */
  private dbToLinear(db: number): number {
    return Math.pow(10, db / 20);
  }

  /**
   * 清理资源
   */
  async dispose(): Promise<void> {
    await this.stopRecording();
    
    this.analyserNodes.clear();
    this.sourceNodes.clear();
    this.gainNodes.clear();
    this.recordedChunks.clear();

    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }

    console.log('[RecordingEngine] 资源已清理');
  }
}