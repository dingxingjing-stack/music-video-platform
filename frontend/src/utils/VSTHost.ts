/**
 * VST 插件宿主引擎
 * 
 * 功能:
 * - 加载 VST3 插件 (WebAssembly)
 * - 管理插件实例
 * - 参数自动化
 * - 预设系统
 * - MIDI 路由到虚拟乐器
 * 
 * 技术架构:
 * - 使用 webaudiox-vst 或類似库进行 WASM 加载
 * - AudioWorklet 用于低延迟音频处理
 * - Web MIDI API 用于 MIDI 输入
 */

import {
  PluginInfo,
  LoadedPlugin,
  MidiEvent,
  WasmVSTConfig,
  PluginPreset
} from '../types/vst';

export class VSTHost {
  private audioContext: AudioContext | null = null;
  private plugins: Map<string, LoadedPlugin> = new Map();
  private pluginPresets: Map<string, PluginPreset[]> = new Map();
  private config: WasmVSTConfig;
  private wasmModule: WebAssembly.Module | null = null;

  constructor(config?: Partial<WasmVSTConfig>) {
    this.config = {
      wasmPath: '/vst-host/vst3-scanner.wasm',
      soundfontPath: '/soundfonts',
      maxPolyphony: 64,
      sampleRate: 44100,
      bufferSize: 512,
      ...config
    };
  }

  /**
   * 初始化音频上下文和 WASM 模块
   */
  async initialize(): Promise<boolean> {
    try {
      // 创建音频上下文
      this.audioContext = new AudioContext({
        sampleRate: this.config.sampleRate,
        latencyHint: 'interactive'
      });

      // 加载 WASM 模块
      const response = await fetch(this.config.wasmPath);
      const wasmBytes = await response.arrayBuffer();
      this.wasmModule = await WebAssembly.compile(wasmBytes);

      console.log('[VSTHost] 初始化完成');
      return true;
    } catch (error) {
      console.error('[VSTHost] 初始化失败:', error);
      return false;
    }
  }

  /**
   * 扫描并加载 VST3 插件
   * 
   * 注意: 浏览器环境限制，只能加载预编译为 WASM 的 VST3 插件
   * 实际部署时需要:
   * 1. 使用 Emscripten 编译 VST3 SDK 为 WASM
   * 2. 或使用现有方案如 webaudiox-vst
   */
  async loadPlugin(pluginPath: string): Promise<PluginInfo | null> {
    try {
      if (!this.wasmModule) {
        throw new Error('WASM 模块未初始化');
      }

      // 模拟插件加载 (实际实现需要调用 WASM 接口)
      const pluginInfo: PluginInfo = {
        id: `vst-${Date.now()}`,
        name: this.extractPluginName(pluginPath),
        vendor: 'Third Party',
        version: '1.0.0',
        type: pluginPath.includes('instrument') ? 'instrument' : 'effect',
        category: this.guessCategory(pluginPath),
        description: 'VST3 Plugin',
        parameters: [],
        presetCount: 0,
        hasUI: true,
        uiWidth: 400,
        uiHeight: 300
      };

      // TODO: 实际实现需要:
      // 1. 加载 WASM 模块
      // 2. 创建插件实例
      // 3. 获取参数列表
      // 4. 加载预设

      console.log(`[VSTHost] 加载插件: ${pluginInfo.name}`);
      return pluginInfo;
    } catch (error) {
      console.error('[VSTHost] 加载插件失败:', error);
      return null;
    }
  }

  /**
   * 创建插件实例
   */
  createInstance(pluginId: string): LoadedPlugin | null {
    const pluginInfo = this.getPluginInfo(pluginId);
    if (!pluginInfo) {
      return null;
    }

    const instance: LoadedPlugin = {
      instanceId: `${pluginId}-${Date.now()}`,
      pluginId,
      name: pluginInfo.name,
      type: pluginInfo.type,
      parameters: {},
      presetIndex: -1,
      enabled: true,
      bypassed: false
    };

    // 初始化参数为默认值
    pluginInfo.parameters.forEach(param => {
      instance.parameters[param.id] = param.defaultValue;
    });

    this.plugins.set(instance.instanceId, instance);
    console.log(`[VSTHost] 创建实例: ${instance.instanceId}`);
    return instance;
  }

  /**
   * 设置插件参数
   */
  setParameter(instanceId: string, parameterId: string, value: number): boolean {
    const plugin = this.plugins.get(instanceId);
    if (!plugin) {
      return false;
    }

    plugin.parameters[parameterId] = Math.max(0, Math.min(1, value));
    
    // TODO: 通知 AudioWorklet 更新参数
    console.log(`[VSTHost] 参数更新: ${parameterId} = ${value}`);
    return true;
  }

  /**
   * 获取插件参数
   */
  getParameter(instanceId: string, parameterId: string): number | undefined {
    const plugin = this.plugins.get(instanceId);
    return plugin?.parameters[parameterId];
  }

  /**
   * 加载插件预设
   */
  loadPreset(instanceId: string, presetIndex: number): boolean {
    const plugin = this.plugins.get(instanceId);
    if (!plugin) {
      return false;
    }

    const presets = this.pluginPresets.get(plugin.pluginId) || [];
    const preset = presets[presetIndex];
    
    if (!preset) {
      return false;
    }

    plugin.presetIndex = presetIndex;
    plugin.parameters = { ...preset.parameters };
    
    console.log(`[VSTHost] 加载预设: ${preset.name}`);
    return true;
  }

  /**
   * 保存用户预设
   */
  saveUserPreset(instanceId: string, name: string): PluginPreset | null {
    const plugin = this.plugins.get(instanceId);
    if (!plugin) {
      return null;
    }

    const preset: PluginPreset = {
      id: `preset-${Date.now()}`,
      pluginId: plugin.pluginId,
      name,
      parameters: { ...plugin.parameters },
      isUserPreset: true
    };

    const presets = this.pluginPresets.get(plugin.pluginId) || [];
    presets.push(preset);
    this.pluginPresets.set(plugin.pluginId, presets);

    return preset;
  }

  /**
   * 处理 MIDI 事件 (发送到虚拟乐器)
   */
  handleMidiEvent(midiEvent: MidiEvent): void {
    // 将 MIDI 事件路由到对应的虚拟乐器插件
    // 1. 查找接收该 MIDI 通道的乐器
    const targetPlugins = Array.from(this.plugins.values()).filter(
      p => p?.info.type === 'instrument' && p?.info.midiChannel === midiEvent.channel
    );
    
    if (targetPlugins.length === 0) {
      console.log(`[VSTHost] 无插件接收通道 ${midiEvent.channel} 的 MIDI 事件`);
      return;
    }
    
    // 2. 调用插件的 MIDI 处理方法
    for (const plugin of targetPlugins) {
      if (midiEvent.type === 'noteOn' && midiEvent.velocity !== undefined && midiEvent.velocity >= 0) {
        this.processNoteOn(plugin, midiEvent.note, midiEvent.velocity);
      } else if (midiEvent.type === 'noteOff' && midiEvent.note !== undefined) {
        this.processNoteOff(plugin, midiEvent.note);
      } else if (midiEvent.type === 'controlChange' && midiEvent.controller !== undefined && midiEvent.value !== undefined) {
        this.processControlChange(plugin, midiEvent.controller, midiEvent.value);
      }
    }
    
    console.log(`[VSTHost] MIDI 路由: ${midiEvent.type} note=${midiEvent.note} → ${targetPlugins.length} 个乐器`);
  }
  
  // 处理 Note On
  private processNoteOn(plugin: LoadedPlugin, note: number, velocity: number): void {
    if (!this.audioContext) return;
    
    // Web Audio API 即时合成 (替代 WASM VST)
    const freq = 440 * Math.pow(2, (note - 69) / 12);
    const osc = this.audioContext.createOscillator();
    const gain = this.audioContext.createGain();
    
    osc.type = 'triangle';
    osc.frequency.value = freq;
    gain.gain.value = 0.3 * (velocity / 127);
    
    osc.connect(gain);
    gain.connect(this.audioContext.destination);
    
    osc.start();
    
    // 存储活跃音符以便 Note Off 时释放
    if (!this._activeNotes) this._activeNotes = new Map();
    this._activeNotes.set(`${plugin.instanceId}_${note}`, { osc, gain });
  }
  
  // 处理 Note Off
  private processNoteOff(plugin: LoadedPlugin, note: number): void {
    const key = `${plugin.instanceId}_${note}`;
    if (this._activeNotes?.has(key)) {
      const { osc, gain } = this._activeNotes.get(key)!;
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioContext?.currentTime || 0 + 0.1);
      setTimeout(() => { osc.stop(); osc.disconnect(); gain.disconnect(); }, 200);
      this._activeNotes.delete(key);
    }
  }
  
  // 处理 Control Change
  private processControlChange(plugin: LoadedPlugin, controller: number, value: number): void {
    console.log(`[VSTHost] CC 控制器 ${controller} = ${value}`);
    // 实际 VST: plugin.wasmInstance.vst_setParameter(controller, value / 127);
  }
  
  private _activeNotes?: Map<string, { osc: OscillatorNode; gain: GainNode }>;

  /**
   * 连接插件到音频链路
   */
  connectToAudioGraph(
    instanceId: string,
    inputNode: AudioNode,
    outputNode: AudioNode
  ): boolean {
    const plugin = this.plugins.get(instanceId);
    if (!plugin || !this.audioContext) {
      return false;
    }

    // TODO: 实际实现需要:
    // 1. 创建 AudioWorkletNode 用于插件处理
    // 2. 连接 inputNode -> AudioWorkletNode -> outputNode
    // 3. 如果是乐器，不需要 inputNode

    console.log(`[VSTHost] 连接音频链路: ${instanceId}`);
    return true;
  }

  /**
   * 断开插件
   */
  disconnect(instanceId: string): boolean {
    const plugin = this.plugins.get(instanceId);
    if (!plugin) {
      return false;
    }

    // TODO: 断开 AudioWorklet 连接
    this.plugins.delete(instanceId);
    console.log(`[VSTHost] 断开插件: ${instanceId}`);
    return true;
  }

  /**
   * 获取所有加载的插件
   */
  getLoadedPlugins(): LoadedPlugin[] {
    return Array.from(this.plugins.values());
  }

  /**
   * 获取插件信息
   */
  getPluginInfo(pluginId: string): PluginInfo | undefined {
    // 实际实现需要从 WASM 模块获取
    return undefined;
  }

  /**
   * 清理资源
   */
  async dispose(): Promise<void> {
    this.plugins.clear();
    this.pluginPresets.clear();
    
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }
    
    this.wasmModule = null;
    console.log('[VSTHost] 资源已清理');
  }

  // ===== 辅助方法 =====

  private extractPluginName(path: string): string {
    const fileName = path.split('/').pop() || path;
    return fileName.replace(/\.(vst3|wasm)$/i, '');
  }

  private guessCategory(path: string): string {
    const lowerPath = path.toLowerCase();
    if (lowerPath.includes('eq')) return 'EQ';
    if (lowerPath.includes('compress')) return 'Compressor';
    if (lowerPath.includes('reverb')) return 'Reverb';
    if (lowerPath.includes('delay')) return 'Delay';
    if (lowerPath.includes('synth') || lowerPath.includes('instrument')) return 'Synth';
    return 'Utility';
  }
}

// ===== Web Audio Worklet 处理器 (用于 VST 音频处理) =====

/**
 * AudioWorklet 处理器
 * 
 * 这段代码会作为单独的 worklet 脚本加载
 * 用于低延迟音频处理 (<10ms)
 */
export const VST_PROCESSOR_CODE = `
class VSTProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.plugins = new Map();
    
    // 接收来自主线程的消息
    this.port.onmessage = (event) => {
      const { type, data } = event.data;
      
      switch (type) {
        case 'load-plugin':
          this.loadPlugin(data);
          break;
        case 'set-parameter':
          this.setParameter(data.instanceId, data.parameterId, data.value);
          break;
        case 'process-midi':
          this.processMidi(data);
          break;
      }
    };
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    const output = outputs[0];

    // 处理每个插件
    for (const [id, plugin] of this.plugins) {
      if (plugin.enabled && !plugin.bypassed) {
        // TODO: 调用 VST 插件的 process 方法
        // 实际实现需要调用 WASM 导出的函数
        this.processVST(plugin, input, output);
      }
    }

    return true;
  }

  processVST(plugin, input, output) {
    // 实际 VST 处理逻辑
    // 需要调用从 WASM 导出的 vst_process 函数
    const channelCount = input.length;
    
    for (let channel = 0; channel < channelCount; channel++) {
      const inputChannel = input[channel];
      const outputChannel = output[channel];
      
      for (let i = 0; i < inputChannel.length; i++) {
        // 简单的直通 (实际是 VST 处理)
        outputChannel[i] = inputChannel[i];
      }
    }
  }

  loadPlugin(data) {
    // 加载 VST 插件实例
    this.plugins.set(data.instanceId, {
      instanceId: data.instanceId,
      wasmInstance: data.wasmInstance,
      enabled: true,
      bypassed: false,
      parameters: data.parameters
    });
  }

  setParameter(instanceId, parameterId, value) {
    const plugin = this.plugins.get(instanceId);
    if (plugin) {
      plugin.parameters[parameterId] = value;
      
      // 通知 VST 插件参数已更新
      // plugin.wasmInstance.vst_setParameter(parameterId, value);
    }
  }

  processMidi(midiEvent) {
    // 处理 MIDI 事件到虚拟乐器 — 使用 Web Audio API 即时合成
    if (!this.audioContext) return;
    
    const { note, velocity = 100, type = 'noteOn' } = midiEvent;
    
    if (type === 'noteOn') {
      const freq = 440 * Math.pow(2, (note - 69) / 12);
      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      
      osc.type = 'triangle';
      osc.frequency.value = freq;
      gain.gain.value = 0.3 * (velocity / 127);
      
      osc.connect(gain);
      gain.connect(this.audioContext.destination);
      osc.start();
      
      // 存储以便 noteOff
      if (!this._activeNotes) {
        this._activeNotes = new Map();
      }
      const noteKey = 'vstproc_' + note + '_' + Date.now();
      this._activeNotes.set(noteKey, { osc: osc, gain: gain });
    } else if (type === 'noteOff') {
      // 释放最早匹配的音符
      var keys = this._activeNotes ? Array.from(this._activeNotes.keys()) : [];
      var foundKey = null;
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].indexOf('_' + note + '_') > -1) {
          foundKey = keys[i];
          break;
        }
      }
      if (foundKey && this._activeNotes && this._activeNotes.has(foundKey)) {
        var noteData = this._activeNotes.get(foundKey);
        if (noteData) {
          var osc = noteData.osc;
          var gain = noteData.gain;
          gain.gain.exponentialRampToValueAtTime(0.001, this.audioContext.currentTime + 0.1);
          setTimeout(function() { osc.stop(); osc.disconnect(); gain.disconnect(); }, 200);
          this._activeNotes.delete(foundKey);
        }
      }
    }
  }
}

registerProcessor('vst-processor', VSTProcessor);
`;