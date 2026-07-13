/**
 * useAudioWorker — 音频 Worker Hook
 * 
 * 在组件中使用 Web Worker 进行后台音频分析
 * 避免 UI 阻塞
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface AnalysisResult {
  bpm?: number;
  duration?: number;
  rms?: number;
  peak?: number;
  peakCount?: number;
  energy?: number;
}

interface WaveformData {
  waveform: { min: number; max: number; rms: number }[];
  bars: number;
  duration: number;
}

export function useAudioWorker() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [waveform, setWaveform] = useState<WaveformData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);

  // 初始化 Worker
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  // 获取 Worker 实例 (懒加载)
  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      const workerCode = `
        // 内联 Worker 代码 (简化版)
        self.onmessage = function(e) {
          var type = e.data.type;
          var audioData = e.data.audioData;
          var sampleRate = e.data.sampleRate;
          
          try {
            var float32 = new Float32Array(audioData);
            var duration = float32.length / sampleRate;
            
            // 计算 RMS 和 Peak
            var totalEnergy = 0;
            var peak = 0;
            for (var i = 0; i < float32.length; i++) {
              totalEnergy += float32[i] * float32[i];
              var abs = Math.abs(float32[i]);
              if (abs > peak) peak = abs;
            }
            var rms = Math.sqrt(totalEnergy / float32.length);
            
            // 简化 BPM 检测
            var windowSize = Math.floor(sampleRate * 0.05);
            var numWindows = Math.floor(float32.length / windowSize);
            var energy = new Float32Array(numWindows);
            for (var i = 0; i < numWindows; i++) {
              var sum = 0;
              var start = i * windowSize;
              var end = start + windowSize;
              for (var j = start; j < end; j++) {
                sum += float32[j] * float32[j];
              }
              energy[i] = sum / windowSize;
            }
            var avgEnergy = 0;
            for (var i = 0; i < energy.length; i++) avgEnergy += energy[i];
            avgEnergy /= energy.length;
            var threshold = avgEnergy * 1.5;
            var peakCount = 0;
            for (var i = 1; i < numWindows - 1; i++) {
              if (energy[i] > threshold && energy[i] > energy[i-1] && energy[i] > energy[i+1]) {
                peakCount++;
              }
            }
            var avgInterval = duration / (peakCount || 1);
            var bpm = 60 / avgInterval;
            if (bpm < 60) bpm *= 2;
            if (bpm > 200) bpm /= 2;
            bpm = Math.round(bpm * 10) / 10;
            
            // 波形数据
            var targetBars = 200;
            var samplesPerBar = Math.floor(float32.length / targetBars);
            var wf = [];
            for (var i = 0; i < targetBars; i++) {
              var min = 0, max = 0, sqSum = 0;
              var start = i * samplesPerBar;
              var end = Math.min(start + samplesPerBar, float32.length);
              for (var j = start; j < end; j++) {
                var v = float32[j];
                if (v < min) min = v;
                if (v > max) max = v;
                sqSum += v * v;
              }
              wf.push({ min: min, max: max, rms: Math.sqrt(sqSum / (end - start)) });
            }
            
            if (type === 'bpm') {
              self.postMessage({ type: 'bpm', success: true, data: { bpm: bpm, peakCount: peakCount, duration: duration } });
            } else if (type === 'waveform') {
              self.postMessage({ type: 'waveform', success: true, data: { waveform: wf, bars: targetBars, duration: duration } });
            } else {
              self.postMessage({ type: 'analyze', success: true, data: { bpm: bpm, duration: duration, rms: rms, peak: peak, peakCount: peakCount, energy: totalEnergy / duration } });
            }
          } catch (err) {
            self.postMessage({ type: type, success: false, error: String(err) });
          }
        };
      `;
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      workerRef.current = new Worker(URL.createObjectURL(blob));

      workerRef.current.onmessage = (e: MessageEvent) => {
        const { type, success, data, error } = e.data;
        setIsProcessing(false);

        if (!success) {
          setError(error || 'Unknown error');
          return;
        }

        setError(null);
        if (type === 'analyze' || type === 'bpm') {
          setAnalysis(data);
        }
        if (type === 'waveform') {
          setWaveform(data);
        }
      };
    }
    return workerRef.current;
  }, []);

  // 分析音频
  const analyze = useCallback((audioBuffer: ArrayBuffer, sampleRate: number) => {
    const worker = getWorker();
    if (!worker) return;

    setIsProcessing(true);
    setError(null);
    worker.postMessage({ type: 'analyze', audioData: audioBuffer, sampleRate });
  }, [getWorker]);

  // 获取波形
  const getWaveform = useCallback((audioBuffer: ArrayBuffer, sampleRate: number) => {
    const worker = getWorker();
    if (!worker) return;

    setIsProcessing(true);
    setError(null);
    worker.postMessage({ type: 'waveform', audioData: audioBuffer, sampleRate });
  }, [getWorker]);

  // 检测 BPM
  const detectBpm = useCallback((audioBuffer: ArrayBuffer, sampleRate: number) => {
    const worker = getWorker();
    if (!worker) return;

    setIsProcessing(true);
    setError(null);
    worker.postMessage({ type: 'bpm', audioData: audioBuffer, sampleRate });
  }, [getWorker]);

  return {
    isProcessing,
    analysis,
    waveform,
    error,
    analyze,
    getWaveform,
    detectBpm,
  };
}

export default useAudioWorker;