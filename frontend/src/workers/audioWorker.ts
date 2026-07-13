/**
 * Audio Worker — 后台音频处理
 * 
 * 在 Web Worker 中处理音频分析，避免阻塞 UI
 * 支持: BPM 检测、音高分析、波形可视化数据
 */

// 类型定义
interface WorkerRequest {
  type: 'analyze' | 'waveform' | 'bpm';
  audioData: ArrayBuffer;
  sampleRate: number;
}

interface WorkerResponse {
  type: string;
  success: boolean;
  data?: any;
  error?: string;
}

self.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const { type, audioData, sampleRate } = e.data;
  
  try {
    switch (type) {
      case 'bpm':
        handleBpmDetection(audioData, sampleRate);
        break;
      case 'waveform':
        handleWaveform(audioData, sampleRate);
        break;
      case 'analyze':
        handleFullAnalysis(audioData, sampleRate);
        break;
      default:
        respond({ type, success: false, error: `Unknown type: ${type}` });
    }
  } catch (err) {
    respond({ type, success: false, error: String(err) });
  }
};

function respond(msg: WorkerResponse) {
  (self as any).postMessage(msg);
}

/**
 * BPM 检测 (简化版)
 * 正式版使用 librosa.beat.beat_track (后端)
 */
function handleBpmDetection(audioData: ArrayBuffer, sampleRate: number) {
  // 将 ArrayBuffer 转为 Float32Array
  const float32 = new Float32Array(audioData);
  
  // 简化能量峰值检测
  const windowSize = Math.floor(sampleRate * 0.05); // 50ms 窗口
  const numWindows = Math.floor(float32.length / windowSize);
  const energy = new Float32Array(numWindows);
  
  for (let i = 0; i < numWindows; i++) {
    let sum = 0;
    const start = i * windowSize;
    const end = start + windowSize;
    for (let j = start; j < end; j++) {
      sum += float32[j] * float32[j];
    }
    energy[i] = sum / windowSize;
  }
  
  // 找峰值 (简化)
  const threshold = computeAverage(energy) * 1.5;
  const peaks: number[] = [];
  for (let i = 1; i < numWindows - 1; i++) {
    if (energy[i] > threshold && energy[i] > energy[i-1] && energy[i] > energy[i+1]) {
      peaks.push(i);
    }
  }
  
  // 计算平均峰值间隔 → BPM
  let bpm = 120; // 默认
  if (peaks.length > 2) {
    const intervals: number[] = [];
    for (let i = 1; i < peaks.length; i++) {
      intervals.push(peaks[i] - peaks[i-1]);
    }
    const avgInterval = computeAverage(new Float32Array(intervals));
    const secondsPerBeat = (avgInterval * windowSize) / sampleRate;
    bpm = 60 / secondsPerBeat;
    
    // 限制在合理范围
    if (bpm < 60) bpm *= 2;
    if (bpm > 200) bpm /= 2;
  }
  
  respond({
    type: 'bpm',
    success: true,
    data: {
      bpm: Math.round(bpm * 10) / 10,
      peakCount: peaks.length,
      duration: float32.length / sampleRate,
    },
  });
}

/**
 * 波形数据生成 (用于可视化)
 */
function handleWaveform(audioData: ArrayBuffer, sampleRate: number) {
  const float32 = new Float32Array(audioData);
  const targetBars = 200; // 200 条波形柱
  const samplesPerBar = Math.floor(float32.length / targetBars);
  
  const waveform: { min: number; max: number; rms: number }[] = [];
  
  for (let i = 0; i < targetBars; i++) {
    let min = 0, max = 0, sum = 0;
    const start = i * samplesPerBar;
    const end = Math.min(start + samplesPerBar, float32.length);
    
    for (let j = start; j < end; j++) {
      const v = float32[j];
      if (v < min) min = v;
      if (v > max) max = v;
      sum += v * v;
    }
    
    waveform.push({
      min,
      max,
      rms: Math.sqrt(sum / (end - start)),
    });
  }
  
  respond({
    type: 'waveform',
    success: true,
    data: {
      waveform,
      bars: targetBars,
      duration: float32.length / sampleRate,
    },
  });
}

/**
 * 完整分析 (BPM + 波形 + 能量)
 */
function handleFullAnalysis(audioData: ArrayBuffer, sampleRate: number) {
  const float32 = new Float32Array(audioData);
  const duration = float32.length / sampleRate;
  
  // 能量
  let totalEnergy = 0;
  for (let i = 0; i < float32.length; i++) {
    totalEnergy += float32[i] * float32[i];
  }
  const rms = Math.sqrt(totalEnergy / float32.length);
  
  // 峰值
  let peak = 0;
  for (let i = 0; i < float32.length; i++) {
    const abs = Math.abs(float32[i]);
    if (abs > peak) peak = abs;
  }
  
  // 简化 BPM
  const windowSize = Math.floor(sampleRate * 0.05);
  const numWindows = Math.floor(float32.length / windowSize);
  const energy = new Float32Array(numWindows);
  
  for (let i = 0; i < numWindows; i++) {
    let sum = 0;
    const start = i * windowSize;
    const end = start + windowSize;
    for (let j = start; j < end; j++) {
      sum += float32[j] * float32[j];
    }
    energy[i] = sum / windowSize;
  }
  
  const threshold = computeAverage(energy) * 1.5;
  let peakCount = 0;
  for (let i = 1; i < numWindows - 1; i++) {
    if (energy[i] > threshold && energy[i] > energy[i-1] && energy[i] > energy[i+1]) {
      peakCount++;
    }
  }
  
  const avgInterval = (numWindows * windowSize) / sampleRate / (peakCount || 1);
  let bpm = 60 / avgInterval;
  if (bpm < 60) bpm *= 2;
  if (bpm > 200) bpm /= 2;
  
  respond({
    type: 'analyze',
    success: true,
    data: {
      bpm: Math.round(bpm * 10) / 10,
      duration,
      rms,
      peak,
      peakCount,
      energy: totalEnergy / duration,
    },
  });
}

function computeAverage(arr: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < arr.length; i++) sum += arr[i];
  return sum / arr.length;
}

export {};