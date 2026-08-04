/**
 * EffectRack — 效果器链（EQ，压缩，混响，延迟，增益）
 */

import { useCallback } from 'react';
import { EffectChain, EQParams, CompressorParams, ReverbParams, DelayParams, GainParams, ChorusParams, FlangerParams, PhaserParams, DistortionParams, FilterParams, TremoloParams, BitcrusherParams } from '../../types/effects';

interface Props {
  chain: EffectChain;
  onChange: (chain: EffectChain) => void;
}

// 滑块组件
function Knob({
  label,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  format = (v: number) => v.toFixed(2),
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  format?: (v: number) => string;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs text-[#777777]">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-[#3a3a3a] rounded-lg appearance-none cursor-pointer accent-orange-500"
      />
      <span className="text-xs text-[#e0e0e0] font-mono">{format(value)}</span>
    </div>
  );
}

// EQ 三段均衡器
function EQSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: EQParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: EQParams) => void;
}) {
  const handleChange = useCallback((key: keyof EQParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🎚️ 均衡器 (EQ)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="低" value={params.low} min={-12} max={12} step={0.5} onChange={(v) => handleChange('low', v)} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`} />
        <Knob label="中" value={params.mid} min={-12} max={12} step={0.5} onChange={(v) => handleChange('mid', v)} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`} />
        <Knob label="高" value={params.high} min={-12} max={12} step={0.5} onChange={(v) => handleChange('high', v)} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`} />
      </div>
    </div>
  );
}

// 压缩器
function CompressorSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: CompressorParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: CompressorParams) => void;
}) {
  const handleChange = useCallback((key: keyof CompressorParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🔊 压缩器</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <Knob label="阈值" value={params.threshold} min={-60} max={0} step={1} onChange={(v) => handleChange('threshold', v)} format={(v) => `${v} dB`} />
        <Knob label="比例" value={params.ratio} min={1} max={20} step={0.5} onChange={(v) => handleChange('ratio', v)} format={(v) => `${v}:1`} />
        <Knob label="启动" value={params.attack} min={0.001} max={1} step={0.001} onChange={(v) => handleChange('attack', v)} format={(v) => `${v.toFixed(3)}s`} />
        <Knob label="释放" value={params.release} min={0.01} max={2} step={0.01} onChange={(v) => handleChange('release', v)} format={(v) => `${v.toFixed(2)}s`} />
      </div>
    </div>
  );
}

// 混响
function ReverbSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: ReverbParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: ReverbParams) => void;
}) {
  const handleChange = useCallback((key: keyof ReverbParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🌊 混响</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="衰减" value={params.decay} min={0.1} max={10} step={0.1} onChange={(v) => handleChange('decay', v)} format={(v) => `${v.toFixed(1)}s`} />
        <Knob label="预延迟" value={params.preDelay} min={0} max={0.5} step={0.01} onChange={(v) => handleChange('preDelay', v)} format={(v) => `${(v * 1000).toFixed(0)}ms`} />
      </div>
    </div>
  );
}

// 延迟
function DelaySection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: DelayParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: DelayParams) => void;
}) {
  const handleChange = useCallback((key: keyof DelayParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🔁 延迟</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="时间" value={params.time} min={0} max={2} step={0.01} onChange={(v) => handleChange('time', v)} format={(v) => `${v.toFixed(2)}s`} />
        <Knob label="反馈" value={params.feedback} min={0} max={0.99} step={0.01} onChange={(v) => handleChange('feedback', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

// 增益
function GainSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: GainParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: GainParams) => void;
}) {
  const handleChange = useCallback((value: number) => {
    onChange({ gain: value });
  }, [onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">📈 增益</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="flex items-center gap-3">
        <Knob label="输出" value={params.gain} min={-60} max={20} step={0.5} onChange={handleChange} format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`} />
      </div>
    </div>
  );
}

// ========== P2 新增效果器 ==========

// 合唱效果
function ChorusSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: ChorusParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: ChorusParams) => void;
}) {
  const handleChange = useCallback((key: keyof ChorusParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🎼 合唱 (Chorus)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="速率" value={params.rate} min={0.1} max={10} step={0.1} onChange={(v) => handleChange('rate', v)} format={(v) => `${v.toFixed(1)}Hz`} />
        <Knob label="深度" value={params.depth} min={0} max={1} step={0.05} onChange={(v) => handleChange('depth', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="延迟" value={params.delay} min={0.001} max={0.1} step={0.001} onChange={(v) => handleChange('delay', v)} format={(v) => `${(v * 1000).toFixed(0)}ms`} />
      </div>
    </div>
  );
}

// 镶边效果
function FlangerSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: FlangerParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: FlangerParams) => void;
}) {
  const handleChange = useCallback((key: keyof FlangerParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🌀 镶边 (Flanger)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="速率" value={params.rate} min={0.1} max={5} step={0.1} onChange={(v) => handleChange('rate', v)} format={(v) => `${v.toFixed(1)}Hz`} />
        <Knob label="深度" value={params.depth} min={0} max={1} step={0.05} onChange={(v) => handleChange('depth', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="反馈" value={params.feedback} min={-0.9} max={0.9} step={0.05} onChange={(v) => handleChange('feedback', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

// 移相效果
function PhaserSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: PhaserParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: PhaserParams) => void;
}) {
  const handleChange = useCallback((key: keyof PhaserParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🌊 移相 (Phaser)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-5 gap-2">
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="速率" value={params.rate} min={0.1} max={5} step={0.1} onChange={(v) => handleChange('rate', v)} format={(v) => `${v.toFixed(1)}Hz`} />
        <Knob label="深度" value={params.depth} min={0} max={1} step={0.05} onChange={(v) => handleChange('depth', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="反馈" value={params.feedback} min={0} max={0.9} step={0.05} onChange={(v) => handleChange('feedback', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="级数" value={params.stages} min={2} max={8} step={2} onChange={(v) => handleChange('stages', v)} format={(v) => `${v}`} />
      </div>
    </div>
  );
}

// 失真效果
function DistortionSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: DistortionParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: DistortionParams) => void;
}) {
  const handleChange = useCallback((key: keyof DistortionParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🔥 失真 (Distortion)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="驱动" value={params.drive} min={0} max={100} step={1} onChange={(v) => handleChange('drive', v)} format={(v) => `${v.toFixed(0)}%`} />
        <Knob label="音色" value={params.tone} min={0} max={1} step={0.05} onChange={(v) => handleChange('tone', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

// 滤波器
function FilterSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: FilterParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: FilterParams) => void;
}) {
  const handleChange = useCallback((key: keyof FilterParams, value: number | string) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🎚️ 滤波器 (Filter)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="mb-3">
        <select
          value={params.type}
          onChange={(e) => handleChange('type', e.target.value)}
          className="w-full px-3 py-2 bg-[#2a2a2a] border border-[#3a3a3a] rounded text-xs text-[#e0e0e0] focus:outline-none focus:border-orange-500"
        >
          <option value="lowpass">低通 (Lowpass)</option>
          <option value="highpass">高通 (Highpass)</option>
          <option value="bandpass">带通 (Bandpass)</option>
          <option value="notch">陷波 (Notch)</option>
        </select>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Knob label="频率" value={params.frequency} min={20} max={20000} step={100} onChange={(v) => handleChange('frequency', v)} format={(v) => `${v.toFixed(0)}Hz`} />
        <Knob label="Q 值" value={params.q} min={0.1} max={50} step={0.1} onChange={(v) => handleChange('q', v)} format={(v) => `${v.toFixed(1)}`} />
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

// 颤音效果
function TremoloSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: TremoloParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: TremoloParams) => void;
}) {
  const handleChange = useCallback((key: keyof TremoloParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">💫 颤音 (Tremolo)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="速率" value={params.rate} min={0.1} max={20} step={0.1} onChange={(v) => handleChange('rate', v)} format={(v) => `${v.toFixed(1)}Hz`} />
        <Knob label="深度" value={params.depth} min={0} max={1} step={0.05} onChange={(v) => handleChange('depth', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

// 位压缩效果
function BitcrusherSection({
  params,
  enabled,
  onToggle,
  onChange,
}: {
  params: BitcrusherParams;
  enabled: boolean;
  onToggle: () => void;
  onChange: (params: BitcrusherParams) => void;
}) {
  const handleChange = useCallback((key: keyof BitcrusherParams, value: number) => {
    onChange({ ...params, [key]: value });
  }, [params, onChange]);

  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'border-orange-500/50 bg-[#1e1e1e]' : 'border-[#2a2a2a] bg-[#121212]'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-[#e0e0e0]">🤖 位压缩 (Bitcrusher)</h3>
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 text-xs rounded transition-colors ${
            enabled ? 'bg-orange-500 text-white' : 'bg-[#3a3a3a] text-[#777777]'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Knob label="位深" value={params.bitDepth} min={1} max={24} step={1} onChange={(v) => handleChange('bitDepth', v)} format={(v) => `${v.toFixed(0)} bit`} />
        <Knob label="采样率" value={params.sampleRate} min={1000} max={48000} step={1000} onChange={(v) => handleChange('sampleRate', v)} format={(v) => `${(v / 1000).toFixed(1)}k`} />
        <Knob label="湿" value={params.wet} min={0} max={1} step={0.05} onChange={(v) => handleChange('wet', v)} format={(v) => `${(v * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

export function EffectRack({ chain, onChange }: Props) {
  const toggleEffect = useCallback(<T extends keyof EffectChain['enabled']>(
    effect: T
  ) => {
    onChange({
      ...chain,
      enabled: { ...chain.enabled, [effect]: !chain.enabled[effect] },
    });
  }, [chain, onChange]);

  return (
    <div className="space-y-3 p-4 bg-[#121212]">
      <EQSection
        params={chain.eq}
        enabled={chain.enabled.eq}
        onToggle={() => toggleEffect('eq')}
        onChange={(params) => onChange({ ...chain, eq: params })}
      />
      <CompressorSection
        params={chain.compressor}
        enabled={chain.enabled.compressor}
        onToggle={() => toggleEffect('compressor')}
        onChange={(params) => onChange({ ...chain, compressor: params })}
      />
      <ReverbSection
        params={chain.reverb}
        enabled={chain.enabled.reverb}
        onToggle={() => toggleEffect('reverb')}
        onChange={(params) => onChange({ ...chain, reverb: params })}
      />
      <DelaySection
        params={chain.delay}
        enabled={chain.enabled.delay}
        onToggle={() => toggleEffect('delay')}
        onChange={(params) => onChange({ ...chain, delay: params })}
      />
      <GainSection
        params={chain.gain}
        enabled={chain.enabled.gain}
        onToggle={() => toggleEffect('gain')}
        onChange={(params) => onChange({ ...chain, gain: params })}
      />
      {/* P2 新增效果器 */}
      <ChorusSection
        params={chain.chorus}
        enabled={chain.enabled.chorus}
        onToggle={() => toggleEffect('chorus')}
        onChange={(params) => onChange({ ...chain, chorus: params })}
      />
      <FlangerSection
        params={chain.flanger}
        enabled={chain.enabled.flanger}
        onToggle={() => toggleEffect('flanger')}
        onChange={(params) => onChange({ ...chain, flanger: params })}
      />
      <PhaserSection
        params={chain.phaser}
        enabled={chain.enabled.phaser}
        onToggle={() => toggleEffect('phaser')}
        onChange={(params) => onChange({ ...chain, phaser: params })}
      />
      <DistortionSection
        params={chain.distortion}
        enabled={chain.enabled.distortion}
        onToggle={() => toggleEffect('distortion')}
        onChange={(params) => onChange({ ...chain, distortion: params })}
      />
      <FilterSection
        params={chain.filter}
        enabled={chain.enabled.filter}
        onToggle={() => toggleEffect('filter')}
        onChange={(params) => onChange({ ...chain, filter: params })}
      />
      <TremoloSection
        params={chain.tremolo}
        enabled={chain.enabled.tremolo}
        onToggle={() => toggleEffect('tremolo')}
        onChange={(params) => onChange({ ...chain, tremolo: params })}
      />
      <BitcrusherSection
        params={chain.bitcrusher}
        enabled={chain.enabled.bitcrusher}
        onToggle={() => toggleEffect('bitcrusher')}
        onChange={(params) => onChange({ ...chain, bitcrusher: params })}
      />
    </div>
  );
}