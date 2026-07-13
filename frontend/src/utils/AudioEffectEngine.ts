/**
 * Web Audio 效果器引擎
 * 
 * 实现 12 种效果器的真实音频处理：
 * - EQ (3 段均衡)
 * - Compressor (动态压缩)
 * - Reverb (混响)
 * - Delay (延迟)
 * - Gain (增益)
 * - Chorus (合唱)
 * - Flanger (镶边)
 * - Phaser (移相)
 * - Distortion (失真)
 * - Filter (滤波器)
 * - Tremolo (颤音)
 * - Bitcrusher (位压缩)
 */

import { EffectChain, EffectType } from '../types/effects';

export class AudioEffectEngine {
  private audioContext: AudioContext | null = null;
  private gainNode: GainNode | null = null;
  
  // 效果器节点
  private nodes: { [key in EffectType]?: AudioNode } = {};
  private filters: { [key: string]: BiquadFilterNode } = {};
  private delayNode: DelayNode | null = null;
  private waveShaperNode: WaveShaperNode | null = null;
  private oscillatorNode: OscillatorNode | null = null;

  constructor() {
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
  }

  /**
   * 初始化效果器链
   */
  initialize(chain: EffectChain) {
    if (!this.audioContext) return;

    // 1. 创建输入增益节点
    this.gainNode = this.audioContext.createGain();
    
    // 2. 创建效果器节点
    this.createEQ(chain.eq);
    this.createCompressor(chain.compressor);
    this.createReverb(chain.reverb);
    this.createDelay(chain.delay);
    this.createChorus(chain.chorus);
    this.createFlanger(chain.flanger);
    this.createPhaser(chain.phaser);
    this.createDistortion(chain.distortion);
    this.createFilter(chain.filter);
    this.createTremolo(chain.tremolo);
    this.createBitcrusher(chain.bitcrusher);
    
    // 3. 创建输出增益节点
    const outputGain = this.audioContext.createGain();
    outputGain.gain.value = chain.gain.gain / 10; // dB to linear
    
    // 4. 连接到输出
    // Source → EQ → Compressor → Filter → Chorus → Flanger → Phaser → 
    // Distortion → Tremolo → Delay → Reverb → Gain → Output
  }

  /**
   * 创建 EQ (3 段均衡)
   */
  private createEQ(params: { low: number; mid: number; high: number }) {
    if (!this.audioContext) return;

    // Low shelf (100Hz)
    const lowFilter = this.audioContext.createBiquadFilter();
    lowFilter.type = 'lowshelf';
    lowFilter.frequency.value = 100;
    lowFilter.gain.value = params.low;
    
    // Peaking (1kHz)
    const midFilter = this.audioContext.createBiquadFilter();
    midFilter.type = 'peaking';
    midFilter.frequency.value = 1000;
    midFilter.Q.value = 1;
    midFilter.gain.value = params.mid;
    
    // High shelf (10kHz)
    const highFilter = this.audioContext.createBiquadFilter();
    highFilter.type = 'highshelf';
    highFilter.frequency.value = 10000;
    highFilter.gain.value = params.high;
    
    lowFilter.connect(midFilter);
    midFilter.connect(highFilter);
    
    this.nodes.eq = lowFilter;
    this.filters.low = lowFilter;
    this.filters.mid = midFilter;
    this.filters.high = highFilter;
  }

  /**
   * 更新 EQ 参数
   */
  updateEQ(params: { low: number; mid: number; high: number }) {
    if (this.filters.low) this.filters.low.gain.value = params.low;
    if (this.filters.mid) this.filters.mid.gain.value = params.mid;
    if (this.filters.high) this.filters.high.gain.value = params.high;
  }

  /**
   * 创建压缩器
   */
  private createCompressor(params: { threshold: number; ratio: number; attack: number; release: number; knee: number }) {
    if (!this.audioContext) return;

    const compressor = this.audioContext.createDynamicsCompressor();
    compressor.threshold.value = params.threshold;
    compressor.knee.value = params.knee;
    compressor.ratio.value = params.ratio;
    compressor.attack.value = params.attack;
    compressor.release.value = params.release;
    
    this.nodes.compressor = compressor;
  }

  /**
   * 更新压缩器参数
   */
  updateCompressor(params: { threshold: number; ratio: number; attack: number; release: number; knee: number }) {
    const node = this.nodes.compressor as DynamicsCompressorNode;
    if (node) {
      node.threshold.value = params.threshold;
      node.knee.value = params.knee;
      node.ratio.value = params.ratio;
      node.attack.value = params.attack;
      node.release.value = params.release;
    }
  }

  /**
   * 创建混响 (Reverb)
   */
  private createReverb(params: { wet: number; decay: number; preDelay: number }) {
    if (!this.audioContext) return;

    const convolver = this.audioContext.createConvolver();
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    // 生成脉冲响应 (简化版)
    const sampleRate = this.audioContext.sampleRate;
    const length = sampleRate * params.decay;
    const impulse = this.audioContext.createBuffer(2, length, sampleRate);
    
    for (let channel = 0; channel < 2; channel++) {
      const channelData = impulse.getChannelData(channel);
      for (let i = 0; i < length; i++) {
        channelData[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 2);
      }
    }
    
    convolver.buffer = impulse;
    convolver.connect(wetGain);
    
    this.nodes.reverb = wetGain;
  }

  /**
   * 更新混响参数
   */
  updateReverb(params: { wet: number; decay: number; preDelay: number }) {
    const wetNode = this.nodes.reverb as GainNode;
    if (wetNode) {
      wetNode.gain.value = params.wet;
    }
  }

  /**
   * 创建延迟 (Delay)
   */
  private createDelay(params: { time: number; feedback: number; wet: number }) {
    if (!this.audioContext) return;

    const delay = this.audioContext.createDelay(5.0);
    delay.delayTime.value = params.time;
    
    const feedback = this.audioContext.createGain();
    feedback.gain.value = params.feedback;
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    delay.connect(feedback);
    feedback.connect(delay);
    delay.connect(wetGain);
    
    this.delayNode = delay;
    this.nodes.delay = wetGain;
  }

  /**
   * 更新延迟参数
   */
  updateDelay(params: { time: number; feedback: number; wet: number }) {
    if (this.delayNode) {
      this.delayNode.delayTime.value = params.time;
    }
    const wetNode = this.nodes.delay as GainNode;
    if (wetNode) {
      wetNode.gain.value = params.wet;
    }
  }

  /**
   * 创建合唱效果 (Chorus)
   */
  private createChorus(params: { wet: number; rate: number; depth: number; delay: number }) {
    if (!this.audioContext) return;

    const delay = this.audioContext.createDelay(0.1);
    delay.delayTime.value = params.delay;
    
    const lfo = this.audioContext.createOscillator();
    lfo.frequency.value = params.rate;
    
    const lfoGain = this.audioContext.createGain();
    lfoGain.gain.value = params.depth * 0.005; // Depth modulation
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    lfo.connect(lfoGain);
    lfoGain.connect(delay.delayTime);
    delay.connect(wetGain);
    
    this.oscillatorNode = lfo;
    this.nodes.chorus = wetGain;
  }

  /**
   * 更新合唱参数
   */
  updateChorus(params: { wet: number; rate: number; depth: number; delay: number }) {
    if (this.oscillatorNode) {
      this.oscillatorNode.frequency.value = params.rate;
    }
    const wetNode = this.nodes.chorus as GainNode;
    if (wetNode) {
      wetNode.gain.value = params.wet;
    }
  }

  /**
   * 创建镶边效果 (Flanger)
   */
  private createFlanger(params: { wet: number; rate: number; depth: number; feedback: number }) {
    // 类似 Chorus，但延迟时间更短 (<10ms)
    this.createChorus({ wet: params.wet, rate: params.rate, depth: params.depth, delay: 0.005 });
    this.nodes.flanger = this.nodes.chorus;
  }

  /**
   * 更新镶边参数
   */
  updateFlanger(params: { wet: number; rate: number; depth: number; feedback: number }) {
    this.updateChorus({ wet: params.wet, rate: params.rate, depth: params.depth, delay: 0.005 });
  }

  /**
   * 创建移相效果 (Phaser)
   */
  private createPhaser(params: { wet: number; rate: number; depth: number; feedback: number; stages: number }) {
    // 使用多个全通滤波器创建相位偏移
    if (!this.audioContext) return;

    const filters: BiquadFilterNode[] = [];
    for (let i = 0; i < params.stages; i++) {
      const filter = this.audioContext.createBiquadFilter();
      filter.type = 'allpass';
      filter.frequency.value = 1000;
      filter.Q.value = 5;
      filters.push(filter);
    }
    
    // 串联滤波器
    for (let i = 0; i < filters.length - 1; i++) {
      filters[i].connect(filters[i + 1]);
    }
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    filters[filters.length - 1].connect(wetGain);
    
    this.nodes.phaser = wetGain;
  }

  /**
   * 更新移相参数
   */
  updatePhaser(params: { wet: number; rate: number; depth: number; feedback: number; stages: number }) {
    const wetNode = this.nodes.phaser as GainNode;
    if (wetNode) {
      wetNode.gain.value = params.wet;
    }
  }

  /**
   * 创建失真效果 (Distortion)
   */
  private createDistortion(params: { drive: number; tone: number; wet: number }) {
    if (!this.audioContext) return;

    const shaper = this.audioContext.createWaveShaper();
    
    // 创建失真曲线
    const curve = new Float32Array(44100);
    const drive = params.drive / 100;
    
    for (let i = 0; i < 44100; i++) {
      const x = (i * 2) / 44100 - 1;
      curve[i] = ((1 + drive) * x) / (1 + drive * Math.abs(x));
    }
    
    shaper.curve = curve;
    shaper.oversample = '4x';
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    shaper.connect(wetGain);
    
    this.waveShaperNode = shaper;
    this.nodes.distortion = wetGain;
  }

  /**
   * 更新失真参数
   */
  updateDistortion(params: { drive: number; tone: number; wet: number }) {
    const wetNode = this.nodes.distortion as GainNode;
    if (wetNode) {
      wetNode.gain.value = params.wet;
    }
    // 重新创建失真曲线
    if (this.waveShaperNode) {
      const curve = new Float32Array(44100);
      const drive = params.drive / 100;
      for (let i = 0; i < 44100; i++) {
        const x = (i * 2) / 44100 - 1;
        curve[i] = ((1 + drive) * x) / (1 + drive * Math.abs(x));
      }
      this.waveShaperNode.curve = curve;
    }
  }

  /**
   * 创建滤波器 (Filter)
   */
  private createFilter(params: { type: string; frequency: number; q: number; wet: number }) {
    if (!this.audioContext) return;

    const filter = this.audioContext.createBiquadFilter();
    filter.type = params.type as BiquadFilterType;
    filter.frequency.value = params.frequency;
    filter.Q.value = params.q;
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    filter.connect(wetGain);
    
    this.nodes.filter = wetGain;
  }

  /**
   * 更新滤波器参数
   */
  updateFilter(params: { type: string; frequency: number; q: number; wet: number }) {
    // 简化实现：实际应用中应维护滤波器引用
    console.log('Update filter:', params);
  }

  /**
   * 创建颤音效果 (Tremolo)
   */
  private createTremolo(params: { rate: number; depth: number; wet: number }) {
    if (!this.audioContext) return;

    const gainNode = this.audioContext.createGain();
    
    const lfo = this.audioContext.createOscillator();
    lfo.frequency.value = params.rate;
    
    const lfoGain = this.audioContext.createGain();
    lfoGain.gain.value = params.depth;
    
    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    lfo.connect(lfoGain);
    lfoGain.connect(gainNode.gain);
    gainNode.connect(wetGain);
    
    lfo.start();
    
    this.nodes.tremolo = wetGain;
  }

  /**
   * 更新颤音参数
   */
  updateTremolo(params: { rate: number; depth: number; wet: number }) {
    // 需要重新创建 LFO
    this.createTremolo(params);
  }

  /**
   * 创建位压缩效果 (Bitcrusher)
   */
  private createBitcrusher(params: { bitDepth: number; sampleRate: number; wet: number }) {
    if (!this.audioContext) return;

    const wetGain = this.audioContext.createGain();
    wetGain.gain.value = params.wet;
    
    // Bitcrusher 需要 ScriptProcessorNode 或 AudioWorklet
    // 简化实现：使用 WaveShaper 模拟
    const shaper = this.audioContext.createWaveShaper();
    const bits = Math.pow(2, params.bitDepth);
    
    const curve = new Float32Array(44100);
    for (let i = 0; i < 44100; i++) {
      const x = (i * 2) / 44100 - 1;
      curve[i] = Math.round(x * bits) / bits;
    }
    
    shaper.curve = curve;
    shaper.connect(wetGain);
    
    this.nodes.bitcrusher = wetGain;
  }

  /**
   * 更新位压缩参数
   */
  updateBitcrusher(params: { bitDepth: number; sampleRate: number; wet: number }) {
    this.createBitcrusher(params);
  }

  /**
   * 连接音频源
   */
  connectSource(source: AudioBufferSourceNode | MediaElementAudioSourceNode) {
    if (!this.audioContext || !this.gainNode) return;
    
    let currentNode: AudioNode = source;
    
    // 按顺序连接效果器链
    const effectOrder: EffectType[] = [
      'eq', 'compressor', 'filter', 'chorus', 'flanger', 
      'phaser', 'distortion', 'tremolo', 'delay', 'reverb'
    ];
    
    for (const effect of effectOrder) {
      const node = this.nodes[effect];
      if (node) {
        currentNode.connect(node);
        currentNode = node;
      }
    }
    
    // 连接到输出
    const outputGain = this.audioContext.createGain();
    outputGain.connect(this.audioContext.destination);
    currentNode.connect(outputGain);
  }

  /**
   * 销毁引擎
   */
  destroy() {
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.nodes = {};
  }
}

// 全局单例
export const effectEngine = new AudioEffectEngine();