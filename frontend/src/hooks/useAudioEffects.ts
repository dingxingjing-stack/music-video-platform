/**
 * useAudioEffects Hook
 * 
 * 将 EffectRack 组件与 Web Audio 引擎连接
 * 自动同步效果器参数到真实音频处理
 */

import { useEffect, useRef, useCallback } from 'react';
import { EffectChain, EffectType } from '../types/effects';
import { effectEngine } from '../utils/AudioEffectEngine';

interface UseAudioEffectsOptions {
  /** 音频元素引用 */
  audioElement: HTMLAudioElement | null;
  /** 是否启用效果器 */
  enabled: EffectChain['enabled'];
}

/**
 * Web Audio 效果器 Hook
 */
export function useAudioEffects(
  chain: EffectChain,
  options: UseAudioEffectsOptions
) {
  const { audioElement, enabled } = options;
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const isInitializedRef = useRef(false);

  // 初始化效果器链
  useEffect(() => {
    if (!audioElement || isInitializedRef.current) return;

    // 创建音频源节点
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const source = audioContext.createMediaElementSource(audioElement);
    sourceNodeRef.current = source;

    // 初始化效果器引擎
    effectEngine.initialize(chain);

    // 连接音频源
    effectEngine.connectSource(source);

    isInitializedRef.current = true;

    return () => {
      // 清理（组件卸载时）
      // effectEngine.destroy();
    };
  }, [audioElement, chain]);

  // 更新效果器参数的辅助函数
  const updateEffect = useCallback((type: EffectType, params: any) => {
    if (!enabled[type]) return;

    switch (type) {
      case 'eq':
        effectEngine.updateEQ(params);
        break;
      case 'compressor':
        effectEngine.updateCompressor(params);
        break;
      case 'reverb':
        effectEngine.updateReverb(params);
        break;
      case 'delay':
        effectEngine.updateDelay(params);
        break;
      case 'chorus':
        effectEngine.updateChorus(params);
        break;
      case 'flanger':
        effectEngine.updateFlanger(params);
        break;
      case 'phaser':
        effectEngine.updatePhaser(params);
        break;
      case 'distortion':
        effectEngine.updateDistortion(params);
        break;
      case 'filter':
        effectEngine.updateFilter(params);
        break;
      case 'tremolo':
        effectEngine.updateTremolo(params);
        break;
      case 'bitcrusher':
        effectEngine.updateBitcrusher(params);
        break;
    }
  }, [enabled]);

  // 监听参数变化并更新
  useEffect(() => {
    if (!isInitializedRef.current) return;

    // 批量更新所有效果器参数
    Object.keys(chain).forEach((key) => {
      if (key === 'enabled') return;
      
      const effectType = key as EffectType;
      if (enabled[effectType]) {
        const params = (chain as any)[effectType];
        updateEffect(effectType, params);
      }
    });
  }, [chain, enabled, updateEffect]);

  // 启用/禁用效果器的辅助函数
  const toggleEffect = useCallback((type: EffectType) => {
    // 实际应用中应该重新连接节点
    console.log(`Toggle effect: ${type} = ${!enabled[type]}`);
  }, [enabled]);

  return {
    toggleEffect,
  };
}