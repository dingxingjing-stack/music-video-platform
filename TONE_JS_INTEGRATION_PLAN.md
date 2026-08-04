# Tone.js 音频引擎集成指南

## 当前状态

**WaveSurfer.js** 已用于基础音频播放和波形可视化。  
**Tone.js** 集成暂缓，留待后续作为高级功能开发。

## 为什么暂缓 Tone.js 集成？

1. **类型配置复杂**: Tone.js 的 TypeScript 类型定义与项目 TSConfig 目标 (ES5) 不兼容
2. **当前方案可用**: WaveSurfer.js 已经满足基础播放需求
3. **开发优先级**: 核心 DAW 功能已完成，音频引擎优化可稍后处理

## 未来集成计划

### 阶段 1: 基础 Tone.js 支持 (2-3 小时)
- [ ] 更新 `tsconfig.json` lib 配置为 ES2015+
- [ ] 创建简化的 `audioEngine.ts` 单例服务
- [ ] 实现基础播放/暂停/停止
- [ ] 与 MultiTrackTimeline 同步进度

### 阶段 2: 多轨混音 (4-6 小时)
- [ ] 每轨道独立 Gain 节点
- [ ] 音量滑块实时控制
- [ ] 声像 (Pan) 控制
- [ ] 静音/独奏功能

### 阶段 3: 效果器链 (6-8 小时)
- [ ] EQ (三频段均衡器)
- [ ] Compressor (动态压缩)
- [ ] Reverb (混响)
- [ ] Delay (延迟)
- [ ] 效果器旁路开关

### 阶段 4: 高级功能 (8-12 小时)
- [ ] 自动化曲线播放
- [ ] MIDI 音源合成
- [ ] 音频录制
- [ ] 实时频谱分析

## 快速开始（阶段 1）

### 1. 更新 tsconfig.json

```json
{
  "compilerOptions": {
    "lib": ["ES2015", "DOM", "DOM.Iterable"]
  }
}
```

### 2. 创建简化版音频引擎

```typescript
// frontend/src/utils/audioEngine.ts
import * as Tone from 'tone';

class AudioEngine {
  private static instance: AudioEngine;
  private masterGain: Tone.Gain;
  private isPlaying = false;
  
  private constructor() {
    this.masterGain = new Tone.Gain(0.8).toDestination();
  }
  
  static getInstance(): AudioEngine {
    if (!AudioEngine.instance) {
      AudioEngine.instance = new AudioEngine();
    }
    return AudioEngine.instance;
  }
  
  async initialize(): Promise<void> {
    await Tone.start();
  }
  
  async play(): Promise<void> {
    if (!this.isPlaying) {
      await Tone.start();
      Tone.Transport.start();
      this.isPlaying = true;
    }
  }
  
  pause(): void {
    Tone.Transport.pause();
    this.isPlaying = false;
  }
  
  stop(): void {
    Tone.Transport.stop();
    this.isPlaying = false;
  }
  
  get isPlayingState(): boolean {
    return this.isPlaying;
  }
}

export default AudioEngine.getInstance();
```

### 3. 在 React 组件中使用

```typescript
import audioEngine from '@/utils/audioEngine';

// 播放控制
const handlePlay = async () => {
  await audioEngine.initialize();
  await audioEngine.play();
};

const handlePause = () => {
  audioEngine.pause();
};
```

## 备用方案

如果 Tone.js 集成持续遇到类型问题，可以考虑：

1. **使用 Web Audio API 原生接口**（更底层，无类型问题）
2. **使用 Howler.js**（更轻量，类型友好）
3. **继续使用 WaveSurfer.js**（已满足 80% 需求）

## 相关资源

- [Tone.js 官方文档](https://tonejs.github.io/docs/)
- [Tone.js GitHub](https://github.com/Tonejs/Tone.js)
- [Web Audio API MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

---

**创建时间**: 2026-07-10  
**状态**: 暂缓开发（WaveSurfer.js 已满足当前需求）