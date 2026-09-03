/**
 * TimeStretchPanel — 时间伸缩面板
 * 
 * 功能:
 * - BPM 检测
 * - 变速不变调
 * - Warp Marker 编辑
 * - 量化到网格
 */

import { useState, useCallback } from 'react';
import { useTranslation } from '../../i18n/useTranslation';

interface WarpMarker {
  id: string;
  grid_time: number;
  audio_time: number;
  bpm: number;
  is_locked: boolean;
}

interface Props {
  onClose: () => void;
}

export function TimeStretchPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const [detectedBpm, setDetectedBpm] = useState<number | null>(null);
  const [targetBpm, setTargetBpm] = useState(120);
  const [isProcessing, setIsProcessing] = useState(false);
  const [markers, setMarkers] = useState<WarpMarker[]>([]);
  const [stretchRatio, setStretchRatio] = useState(1.0);

  // 检测 BPM (Mock)
  const handleDetectBpm = useCallback(async () => {
    setIsProcessing(true);
    
    // Mock 检测
    setTimeout(() => {
      setDetectedBpm(120);
      setTargetBpm(120);
      
      // 生成 Mock markers
      const mockMarkers: WarpMarker[] = [];
      for (let i = 0; i < 16; i++) {
        mockMarkers.push({
          id: `warp_${i}`,
          grid_time: i * 0.25,
          audio_time: i * 0.5,
          bpm: 120,
          is_locked: i % 4 === 0,
        });
      }
      setMarkers(mockMarkers);
      setIsProcessing(false);
    }, 1000);
  }, []);

  // 执行时间伸缩
  const handleStretch = useCallback(async () => {
    if (!detectedBpm) return;
    
    setIsProcessing(true);
    
    // 计算伸缩比例
    const ratio = detectedBpm / targetBpm;
    setStretchRatio(ratio);
    
    // Mock 处理
    setTimeout(() => {
      setIsProcessing(false);
    }, 1500);
  }, [detectedBpm, targetBpm]);

  // 锁定 marker
  const toggleLock = useCallback((markerId: string) => {
    setMarkers(prev => prev.map(m =>
      m.id === markerId ? { ...m, is_locked: !m.is_locked } : m
    ));
  }, []);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-4xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">⏱️ {t('timestretch.title')}</h2>
            <p className="text-sm text-zinc-400 mt-1">{t('timestretch.subtitle')}</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            {t('timestretch.close')}
          </button>
        </div>

        {/* BPM 检测区域 */}
        {!detectedBpm ? (
          <div className="text-center py-12">
            <div className="text-5xl mb-4">⏱️</div>
            <h3 className="text-xl font-bold text-white mb-2">{t('timestretch.detectBpmTitle')}</h3>
            <p className="text-zinc-400 mb-6">{t('timestretch.detectBpmDesc')}</p>
            
            <button
              onClick={handleDetectBpm}
              disabled={isProcessing}
              className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition disabled:opacity-50"
            >
              {isProcessing ? t('timestretch.detecting') : t('timestretch.detectBpm')}
            </button>
          </div>
        ) : (
          /* 编辑区域 */
          <div>
            {/* BPM 控制 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">{t('timestretch.originalBpm')}</label>
                  <div className="text-3xl font-bold text-purple-400">{detectedBpm}</div>
                </div>
                
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">{t('timestretch.targetBpm')}</label>
                  <input
                    type="number"
                    value={targetBpm}
                    onChange={(e) => setTargetBpm(Number(e.target.value))}
                    className="w-full bg-zinc-700 border border-zinc-600 rounded px-3 py-2 text-2xl font-bold text-white"
                  />
                </div>
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <div className="text-sm text-zinc-400">
                  {t('timestretch.stretchRatio', { value: stretchRatio.toFixed(2) })}
                </div>
                <button
                  onClick={handleStretch}
                  disabled={isProcessing}
                  className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition disabled:opacity-50"
                >
                  {isProcessing ? t('timestretch.stretching') : t('timestretch.applyStretch')}
                </button>
              </div>
            </div>

            {/* Warp Marker 列表 */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-bold text-white">{t('timestretch.warpMarkers', { n: markers.length })}</h3>
                <button className="text-xs text-purple-400 hover:text-purple-300">
                  {t('timestretch.addMarker')}
                </button>
              </div>
              
              <div className="space-y-2 max-h-64 overflow-auto">
                {markers.map((marker, idx) => (
                  <div
                    key={marker.id}
                    className={`flex items-center justify-between p-3 rounded-lg border transition ${
                      marker.is_locked
                        ? 'bg-purple-500/10 border-purple-500/30'
                        : 'bg-zinc-800/50 border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold ${
                        marker.is_locked
                          ? 'bg-purple-500 text-white'
                          : 'bg-zinc-700 text-zinc-400'
                      }`}>
                        {marker.is_locked ? '🔒' : idx + 1}
                      </div>
                      <div>
                        <div className="text-white text-sm font-medium">
                          {t('timestretch.markerTime', { time: marker.grid_time.toFixed(2) })}
                        </div>
                        <div className="text-xs text-zinc-500">
                          {marker.audio_time.toFixed(2)}s · {marker.bpm.toFixed(1)} BPM
                        </div>
                      </div>
                    </div>
                    
                    <button
                      onClick={() => toggleLock(marker.id)}
                      className={`px-3 py-1 rounded text-xs font-medium transition ${
                        marker.is_locked
                          ? 'bg-purple-500 text-white'
                          : 'bg-zinc-700 text-zinc-400 hover:text-white'
                      }`}
                    >
                      {marker.is_locked ? t('timestretch.locked') : t('timestretch.unlocked')}
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* 量化选项 */}
            <div className="p-4 bg-zinc-800/50 rounded-xl">
              <h4 className="text-sm font-medium text-white mb-3">{t('timestretch.gridQuantize')}</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">{t('timestretch.gridResolution')}</label>
                  <select className="w-full bg-zinc-700 border border-zinc-600 rounded px-3 py-2 text-sm text-white">
                    <option value="0.0625">{t('timestretch.note16')}</option>
                    <option value="0.125">{t('timestretch.note8')}</option>
                    <option value="0.25" selected>{t('timestretch.note4')}</option>
                    <option value="0.5">{t('timestretch.note2')}</option>
                    <option value="1">{t('timestretch.noteWhole')}</option>
                  </select>
                </div>
                
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">{t('timestretch.quantizeStrength')}</label>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    defaultValue="100"
                    className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                  />
                </div>
              </div>
              
              <button className="mt-3 w-full px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg text-sm font-medium transition">
                {t('timestretch.applyQuantize')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TimeStretchPanel;