/**
 * EffectsPanel — 效果器链面板（可在多轨编辑器中使用）
 */

import { useState, useCallback } from 'react';
import { EffectRack } from './EffectRack';
import { EffectChain, defaultEffectChain, EffectType } from '../../types/effects';

// 应用效果器到 Tone.js (简化实现)
function applyEffectsToToneJS(trackId: string, chain: EffectChain) {
  // 实际实现需要 Tone.js 效果器实例
  // 这里提供框架，待 Tone.js 集成后完善
  console.log(`[Tone.js] Applying ${chain.effects.length} effects to track ${trackId}`);
  
  chain.effects.forEach((effect, index) => {
    const effectType = effect.type as EffectType;
    console.log(`  [${index}] ${effectType}:`, effect.params);
    
    // TODO: 实际 Tone.js 实现:
    // switch (effectType) {
    //   case 'compressor':
    //     const compressor = new Tone.Compressor(effect.params.threshold, effect.params.ratio);
    //     compressor.connect(destination);
    //     break;
    //   case 'eq':
    //     const eq = new Tone.EQ3(effect.params.low, effect.params.mid, effect.params.high);
    //     eq.connect(destination);
    //     break;
    //   case 'reverb':
    //     const reverb = new Tone.Reverb(effect.params.decay).toDestination();
    //     reverb.connect(destination);
    //     break;
    //   // ... 其他效果器
    // }
  });
  
  // 触发自定义事件，供实际 Tone.js 实现监听
  window.dispatchEvent(new CustomEvent('tonejs-effects-update', {
    detail: { trackId, chain }
  }));
}

interface Props {
  trackId: string;
  trackName: string;
  onClose: () => void;
}

export function EffectsPanel({ trackId, trackName, onClose }: Props) {
  const [chain, setChain] = useState<EffectChain>(defaultEffectChain);

  const handleChange = useCallback((newChain: EffectChain) => {
    setChain(newChain);
    // 应用到 Tone.js 效果器
    applyEffectsToToneJS(trackId, newChain);
    console.log('Effect chain updated:', trackId, newChain);
  }, [trackId]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[600px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">🎛️ 效果器链</h2>
            <p className="text-xs text-[#777777]">{trackName}</p>
          </div>
          <button
            onClick={onClose}
            className="text-[#777777] hover:text-white transition"
          >
            ✕
          </button>
        </div>
        <div className="overflow-auto max-h-[60vh]">
          <EffectRack chain={chain} onChange={handleChange} />
        </div>
        <div className="p-4 border-t border-[#2a2a2a] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}