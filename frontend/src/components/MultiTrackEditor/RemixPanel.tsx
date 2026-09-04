/**
 * RemixPanel — AI Remix 引擎面板
 * 
 * 功能:
 * - 风格转换 (10 种风格)
 * - 强度控制
 * - 节奏调整
 * - Drop/Buildup 添加
 * - 和弦转调
 */

import { useState, useCallback, useEffect } from 'react';
import { api } from '../../config/api';
import { useTranslation } from '../../i18n/useTranslation';

interface RemixStyle {
  id: string;
  name: string;
  description: string;
  typical_bpm: [number, number];
}

interface Props {
  onClose: () => void;
}

export function RemixPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const [styles, setStyles] = useState<RemixStyle[]>([]);
  const [selectedStyle, setSelectedStyle] = useState<string | null>(null);
  const [intensity, setIntensity] = useState('moderate');
  const [tempoMultiplier, setTempoMultiplier] = useState(1.0);
  const [addDrops, setAddDrops] = useState(false);
  const [addBuildups, setAddBuildups] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [remixResult, setRemixResult] = useState<any>(null);

  // 加载风格列表
  useEffect(() => {
    fetch(api.url('/api/v1/remix/styles'))
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setStyles(data.styles);
        }
      })
      .catch(console.error);
  }, []);

  // 执行 Remix
  const handleRemix = useCallback(async () => {
    if (!selectedStyle) return;
    
    setIsProcessing(true);
    
    // Mock Remix 调用
    setTimeout(() => {
      const result = {
        success: true,
        remixed_style: selectedStyle,
        original_bpm: 120,
        remixed_bpm: 128,
        changes_applied: [
          t('remix.rhythmMode', { style: selectedStyle }),
          t('remix.intensity', { intensity }),
          addDrops ? t('remix.addDropSection') : '',
          addBuildups ? t('remix.addBuildupSection') : '',
        ].filter(Boolean),
        remixed_audio_url: `mock://remix_${selectedStyle}.wav`,
      };
      setRemixResult(result);
      setIsProcessing(false);
    }, 2000);
  }, [selectedStyle, intensity, addDrops, addBuildups]);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-5xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎛️ {t('remix.title')}</h2>
            <p className="text-sm text-zinc-400 mt-1">{t('remix.subtitle')}</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            {t('remix.close')}
          </button>
        </div>

        {!remixResult ? (
          /* Remix 配置界面 */
          <div>
            {/* 风格选择 */}
            <div className="mb-6">
              <h3 className="text-lg font-bold text-white mb-3">{t('remix.selectTarget')}</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                {styles.map(style => (
                  <button
                    key={style.id}
                    onClick={() => setSelectedStyle(style.id)}
                    className={`p-4 rounded-xl border-2 transition text-left ${
                      selectedStyle === style.id
                        ? 'border-purple-500 bg-purple-500/10'
                        : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-500'
                    }`}
                  >
                    <div className="text-white font-bold text-sm mb-1">{style.name}</div>
                    <div className="text-xs text-zinc-400 line-clamp-2">{style.description}</div>
                    <div className="text-xs text-purple-400 mt-2">
                      {style.typical_bpm[0]}-{style.typical_bpm[1]} BPM
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* 强度控制 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <h4 className="text-sm font-medium text-white mb-3">{t('remix.strength')}</h4>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: 'subtle', name: 'remix.strengthSubtle', desc: 'remix.strengthSubtleDesc' },
                  { id: 'moderate', name: 'remix.strengthModerate', desc: 'remix.strengthModerateDesc' },
                  { id: 'extreme', name: 'remix.strengthExtreme', desc: 'remix.strengthExtremeDesc' },
                ].map(opt => (
                  <button
                    key={opt.id}
                    onClick={() => setIntensity(opt.id)}
                    className={`p-3 rounded-lg border transition ${
                      intensity === opt.id
                        ? 'border-purple-500 bg-purple-500/20'
                        : 'border-zinc-700 bg-zinc-700/50 hover:border-zinc-500'
                    }`}
                  >
                    <div className={`font-bold ${intensity === opt.id ? 'text-purple-400' : 'text-white'}`}>
                      {t(opt.name)}
                    </div>
                    <div className="text-xs text-zinc-400">{t(opt.desc)}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* 高级选项 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <h4 className="text-sm font-medium text-white mb-3">{t('remix.advanced')}</h4>
              
              {/* 节奏倍率 */}
              <div className="mb-4">
                <label className="text-xs text-zinc-400 mb-2 block">
                  {t('remix.tempoMultiplier', { value: tempoMultiplier.toFixed(2) })}
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.1"
                  value={tempoMultiplier}
                  onChange={(e) => setTempoMultiplier(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>{t('remix.tempo0_5')}</span>
                  <span>{t('remix.tempo1_0')}</span>
                  <span>{t('remix.tempo2_0')}</span>
                </div>
              </div>

              {/* 特殊效果 */}
              <div className="grid grid-cols-2 gap-3">
                <label className="flex items-center gap-3 p-3 bg-zinc-700/50 rounded-lg cursor-pointer hover:bg-zinc-700 transition">
                  <input
                    type="checkbox"
                    checked={addDrops}
                    onChange={(e) => setAddDrops(e.target.checked)}
                    className="w-5 h-5 rounded accent-purple-500"
                  />
                  <div>
                    <div className="text-white text-sm font-medium">{t('remix.addDrop')}</div>
                    <div className="text-xs text-zinc-400">{t('remix.addDropDesc')}</div>
                  </div>
                </label>

                <label className="flex items-center gap-3 p-3 bg-zinc-700/50 rounded-lg cursor-pointer hover:bg-zinc-700 transition">
                  <input
                    type="checkbox"
                    checked={addBuildups}
                    onChange={(e) => setAddBuildups(e.target.checked)}
                    className="w-5 h-5 rounded accent-purple-500"
                  />
                  <div>
                    <div className="text-white text-sm font-medium">{t('remix.addBuildup')}</div>
                    <div className="text-xs text-zinc-400">{t('remix.addBuildupDesc')}</div>
                  </div>
                </label>
              </div>
            </div>

            {/* 执行按钮 */}
            <button
              onClick={handleRemix}
              disabled={!selectedStyle || isProcessing}
              className="w-full py-4 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-xl font-bold text-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? t('remix.processing') : t('remix.start')}
            </button>
          </div>
        ) : (
          /* Remix 结果界面 */
          <div>
            <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-xl mb-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="text-3xl">✅</div>
                <div>
                  <div className="text-green-400 font-bold text-lg">{t('remix.done')}</div>
                  <div className="text-sm text-zinc-400">{t('remix.newVersion')}</div>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-zinc-400">{t('remix.originalStyle')}:</span>
                  <span className="text-white ml-2">{remixResult.original_style}</span>
                </div>
                <div>
                  <span className="text-zinc-400">{t('remix.newStyle')}:</span>
                  <span className="text-white ml-2 text-purple-400 font-bold">{remixResult.remixed_style}</span>
                </div>
                <div>
                  <span className="text-zinc-400">{t('remix.originalBpm')}:</span>
                  <span className="text-white ml-2">{remixResult.original_bpm}</span>
                </div>
                <div>
                  <span className="text-zinc-400">{t('remix.newBpm')}:</span>
                  <span className="text-white ml-2">{remixResult.remixed_bpm}</span>
                </div>
              </div>
            </div>

            {/* 应用的变化 */}
            <div className="mb-6">
              <h4 className="text-sm font-medium text-white mb-3">{t('remix.appliedChanges')}</h4>
              <ul className="space-y-2">
                {remixResult.changes_applied.map((change: string, i: number) => (
                  <li key={i} className="flex items-center gap-2 text-sm">
                    <span className="text-purple-400">✓</span>
                    <span className="text-zinc-300">{change}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* 操作按钮 */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setRemixResult(null)}
                className="px-4 py-3 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg font-medium transition"
              >
                🔄 {t('remix.again')}
              </button>
              <button className="px-4 py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition">
                📥 {t('remix.export')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default RemixPanel;