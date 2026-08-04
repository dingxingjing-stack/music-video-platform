/**
 * 音频波形分析器
 * 
 * 功能:
 * - 加载音频文件
 * - 提取波形数据
 * - 检测节拍
 * - 生成可视化数据
 */

import { WaveformData, BeatMarker } from '../types/video-sync';

export class WaveformAnalyzer {
  private audioContext: AudioContext | null = null;
  private audioBuffer: AudioBuffer | null = null;

  /**
   * 加载音频文件并提取波形
   */
  async loadAudio(fileUrl: string): Promise<WaveformData> {
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    
    // 获取音频数据
    const response = await fetch(fileUrl);
    const arrayBuffer = await response.arrayBuffer();
    
    // 解码音频
    this.audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
    
    // 提取波形数据
    const channels = this.audioBuffer.numberOfChannels;
    const sampleRate = this.audioBuffer.sampleRate;
    const duration = this.audioBuffer.duration;
    const samples: Float32Array[] = [];
    
    for (let i = 0; i < channels; i++) {
      samples.push(this.audioBuffer.getChannelData(i));
    }
    
    // 生成峰值数据 (用于可视化)
    const peaks = this.generatePeaks(samples[0], 1000);
    
    return {
      channels,
      sampleRate,
      duration,
      samples,
      peaks
    };
  }

  /**
   * 生成简化的峰值数据
   */
  private generatePeaks(samples: Float32Array, targetLength: number): number[] {
    const blockSize = Math.floor(samples.length / targetLength);
    const peaks: number[] = [];
    
    for (let i = 0; i < targetLength; i++) {
      let max = 0;
      for (let j = 0; j < blockSize; j++) {
        const index = i * blockSize + j;
        const abs = Math.abs(samples[index] || 0);
        if (abs > max) max = abs;
      }
      peaks.push(max);
    }
    
    return peaks;
  }

  /**
   * 检测音频节拍
   */
  async detectBeats(): Promise<BeatMarker[]> {
    if (!this.audioBuffer) {
      throw new Error('请先加载音频文件');
    }

    const markers: BeatMarker[] = [];
    const channelData = this.audioBuffer.getChannelData(0);
    const sampleRate = this.audioBuffer.sampleRate;
    
    // 简单的节拍检测算法 (基于能量变化)
    const windowSize = 2048;
    const hopSize = 512;
    const threshold = 0.3;
    
    let previousEnergy = 0;
    let barCount = 0;
    
    for (let i = 0; i < channelData.length - windowSize; i += hopSize) {
      // 计算当前窗口能量
      let energy = 0;
      for (let j = 0; j < windowSize; j++) {
        energy += Math.pow(channelData[i + j], 2);
      }
      energy = Math.sqrt(energy / windowSize);
      
      // 检测能量突增 (可能是节拍)
      if (energy > previousEnergy * (1 + threshold)) {
        const time = i / sampleRate;
        
        // 每 4 个节拍标记为一个小节
        const isBar = barCount % 4 === 0;
        const isDownbeat = barCount % 4 === 0;
        
        markers.push({
          time,
          type: isBar ? 'bar' : (isDownbeat ? 'downbeat' : 'beat'),
          strength: Math.min(1, energy * 2),
          label: isBar ? `Bar ${barCount / 4 + 1}` : undefined
        });
        
        barCount++;
      }
      
      previousEnergy = energy * 0.9 + previousEnergy * 0.1; // 平滑
    }
    
    return markers;
  }

  /**
   * 获取指定时间的波形振幅
   */
  getAmplitudeAtTime(time: number): number {
    if (!this.audioBuffer) return 0;
    
    const sampleRate = this.audioBuffer.sampleRate;
    const channelData = this.audioBuffer.getChannelData(0);
    const index = Math.floor(time * sampleRate);
    
    if (index < 0 || index >= channelData.length) {
      return 0;
    }
    
    return Math.abs(channelData[index]);
  }

  /**
   * 计算音频的 BPM
   */
  calculateBPM(): number {
    if (!this.audioBuffer) return 0;
    
    // 简化的 BPM 计算 (基于自相关)
    const channelData = this.audioBuffer.getChannelData(0);
    const sampleRate = this.audioBuffer.sampleRate;
    
    // 取样分析 (前 30 秒)
    const analysisLength = Math.min(30 * sampleRate, channelData.length);
    const data = channelData.slice(0, analysisLength);
    
    // 计算自相关
    const bpmRange = { min: 60, max: 180 };
    const bestBPM = this.findBestBPM(data, sampleRate, bpmRange);
    
    return bestBPM;
  }

  private findBestBPM(
    data: Float32Array,
    sampleRate: number,
    range: { min: number; max: number }
  ): number {
    let bestBPM = 120;
    let bestScore = 0;
    
    for (let bpm = range.min; bpm <= range.max; bpm++) {
      const period = Math.floor(sampleRate * 60 / bpm);
      let score = 0;
      
      // 计算自相关
      for (let i = 0; i < period * 4 && i + period < data.length; i++) {
        score += data[i] * data[i + period];
      }
      
      score /= period * 4;
      
      if (score > bestScore) {
        bestScore = score;
        bestBPM = bpm;
      }
    }
    
    return bestBPM;
  }

  /**
   * 清理资源
   */
  dispose() {
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.audioBuffer = null;
  }
}