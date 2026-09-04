/**
 * VoiceCloningPanel — 声音克隆面板
 * 
 * 功能:
 * - {t('voiceClone.uploadTitle')}
 * - 声音档案管理
 * - 声音克隆合成
 * - 音色库浏览
 */

import { useState, useCallback, useEffect } from 'react';
import { api } from '../../config/api';
import { useTranslation } from '../../i18n/useTranslation';

interface VoiceProfile {
  id: string;
  name: string;
  description?: string;
  sample_duration: number;
  tags: string[];
  created_at: string;
}

interface Props {
  onClose: () => void;
}

export function VoiceCloningPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'upload' | 'clone' | 'library'>('upload');
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [cloneText, setCloneText] = useState('');
  const [cloneSpeed, setCloneSpeed] = useState(1.0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [cloneResult, setCloneResult] = useState<any>(null);

  // 加载声音库
  useEffect(() => {
    if (activeTab === 'library') {
      fetch(api.url('/api/v1/voice/voices?limit=20'))
        .then(r => r.json())
        .then(data => {
          if (data.success) {
            setVoices(data.voices);
          }
        })
        .catch(console.error);
    }
  }, [activeTab]);

  // {t('voiceClone.uploadTitle')}
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsProcessing(true);
    
    // Mock 上传
    setTimeout(() => {
      const newVoice: VoiceProfile = {
        id: `voice_${Date.now()}`,
        name: file.name.replace(/\.[^.]+$/, ''),
        description: t('voiceClone.userUploaded'),
        sample_duration: 120,
        tags: ['user-uploaded'],
        created_at: new Date().toISOString(),
      };
      setVoices(prev => [...prev, newVoice]);
      setSelectedVoice(newVoice.id);
      setActiveTab('clone');
      setIsProcessing(false);
    }, 1500);
  }, []);

  // 执行声音克隆
  const handleClone = useCallback(async () => {
    if (!selectedVoice || !cloneText) return;

    setIsProcessing(true);

    // Mock 克隆
    setTimeout(() => {
      setCloneResult({
        success: true,
        audio_url: `mock://cloned_${selectedVoice}.wav`,
        duration: cloneText.length * 0.08,
        voice_name: t('voiceClone.clonedVoice'),
        processing_time: 2.5,
      });
      setIsProcessing(false);
    }, 2000);
  }, [selectedVoice, cloneText, cloneSpeed]);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-5xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎤 {t('voiceClone.title')}</h2>
            <p className="text-sm text-zinc-400 mt-1">{t('voiceClone.subtitle')}</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            {t('voiceClone.close')}
          </button>
        </div>

        {/* Tab 导航 */}
        <div className="flex gap-2 mb-6 border-b border-zinc-700">
          {[
            { id: 'upload', label: 'voiceClone.uploadTab', icon: '📤' },
            { id: 'clone', label: 'voiceClone.cloneTab', icon: '🎙️' },
            { id: 'library', label: 'voiceClone.libraryTab', icon: '📚' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 font-medium transition ${
                activeTab === tab.id
                  ? 'text-purple-400 border-b-2 border-purple-500'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              {t(tab.label)}
            </button>
          ))}
        </div>

        {activeTab === 'upload' && (
          /* 上传样本 */
          <div>
            <div className="text-center py-12">
              <div className="text-5xl mb-4">🎤</div>
              <h3 className="text-xl font-bold text-white mb-2">{t('voiceClone.uploadTitle')}</h3>
              <p className="text-zinc-400 mb-6">
                {t('voiceClone.uploadDesc')}
              </p>

              <div className="max-w-md mx-auto mb-6 p-6 bg-zinc-800/50 rounded-xl border border-zinc-700">
                <h4 className="text-sm font-medium text-white mb-3">{t('voiceClone.recordReqs')}</h4>
                <ul className="text-left text-sm text-zinc-400 space-y-2">
                  <li>✓ {t('voiceClone.req1')}</li>
                  <li>✓ {t('voiceClone.req2')}</li>
                  <li>✓ {t('voiceClone.req3')}</li>
                  <li>✓ {t('voiceClone.req4')}</li>
                  <li>✓ {t('voiceClone.req5')}</li>
                </ul>
              </div>

              <label className="inline-block px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition cursor-pointer">
                {isProcessing ? t('voiceClone.uploading') : t('voiceClone.selectAudio')}
                <input
                  type="file"
                  accept="audio/*"
                  onChange={handleUpload}
                  disabled={isProcessing}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        )}

        {activeTab === 'clone' && !cloneResult && (
          /* 声音克隆 */
          <div>
            {/* 声音选择 */}
            <div className="mb-6">
              <label className="text-sm font-medium text-white mb-2 block">{t('voiceClone.selectVoice')}</label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {voices.length === 0 ? (
                  <div className="col-span-full text-center text-zinc-400 py-4">
                    {t('voiceClone.noVoices')}
                  </div>
                ) : (
                  voices.map(voice => (
                    <button
                      key={voice.id}
                      onClick={() => setSelectedVoice(voice.id)}
                      className={`p-3 rounded-lg border-2 transition text-left ${
                        selectedVoice === voice.id
                          ? 'border-purple-500 bg-purple-500/10'
                          : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-500'
                      }`}
                    >
                      <div className="text-white font-bold text-sm">{voice.name}</div>
                      <div className="text-xs text-zinc-400">
                        {t('voiceClone.durationMin', { n: (voice.sample_duration / 60).toFixed(1) })}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* 文本输入 */}
            <div className="mb-6">
              <label className="text-sm font-medium text-white mb-2 block">{t('voiceClone.cloneText')}</label>
              <textarea
                value={cloneText}
                onChange={(e) => setCloneText(e.target.value)}
                placeholder={t('voiceClone.cloneTextPlaceholder')}
                rows={4}
                maxLength={1000}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <div className="text-xs text-zinc-400 mt-1 text-right">
                {t('voiceClone.cloneTextCount', { n: cloneText.length })}
              </div>
            </div>

            {/* {t('voiceClone.advanced')} */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <h4 className="text-sm font-medium text-white mb-3">⚙️ {t('voiceClone.advanced')}</h4>
              
              <div>
                <label className="text-xs text-zinc-400 mb-2 block">
                  {t('voiceClone.speed', { value: cloneSpeed.toFixed(2) })}
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.1"
                  value={cloneSpeed}
                  onChange={(e) => setCloneSpeed(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>{t('voiceClone.speed0_5')}</span>
                  <span>{t('voiceClone.speed1_0')}</span>
                  <span>{t('voiceClone.speed2_0')}</span>
                </div>
              </div>
            </div>

            {/* 执行按钮 */}
            <button
              onClick={handleClone}
              disabled={!selectedVoice || !cloneText || isProcessing}
              className="w-full py-4 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-xl font-bold text-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? t('voiceClone.synthesizing') : t('voiceClone.startClone')}
            </button>
          </div>
        )}

        {activeTab === 'clone' && cloneResult && (
          /* 克隆结果 */
          <div>
            <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-xl mb-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="text-3xl">✅</div>
                <div>
                  <div className="text-green-400 font-bold text-lg">{t('voiceClone.cloneComplete')}</div>
                  <div className="text-sm text-zinc-400">{t('voiceClone.cloneDesc')}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-zinc-400">{t('voiceClone.voice')}:</span>
                  <span className="text-white ml-2">{cloneResult.voice_name}</span>
                </div>
                <div>
                  <span className="text-zinc-400">{t('voiceClone.duration')}:</span>
                  <span className="text-white ml-2">{t('voiceClone.durationSec', { n: cloneResult.duration.toFixed(2) })}</span>
                </div>
                <div>
                  <span className="text-zinc-400">{t('voiceClone.processingTime')}:</span>
                  <span className="text-white ml-2">{t('voiceClone.processingSec', { n: cloneResult.processing_time.toFixed(2) })}</span>
                </div>
              </div>
            </div>

            {/* 音频播放器 (Mock) */}
            <div className="p-4 bg-zinc-800/50 rounded-xl mb-6">
              <div className="flex items-center gap-3">
                <button className="w-12 h-12 rounded-full bg-purple-500 hover:bg-purple-600 flex items-center justify-center text-white text-xl transition">
                  ▶
                </button>
                <div className="flex-1 h-12 bg-zinc-700 rounded-lg flex items-center px-4">
                  <div className="text-sm text-zinc-400">{t('voiceClone.waveform')}</div>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setCloneResult(null)}
                className="px-4 py-3 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg font-medium transition"
              >
                🔄 {t('voiceClone.cloneAgain')}
              </button>
              <button className="px-4 py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition">
                📥 {t('voiceClone.exportAudio')}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'library' && (
          /* 音色库 */
          <div>
            <h3 className="text-lg font-bold text-white mb-4">📚 {t('voiceClone.libraryTitle', { n: voices.length })}</h3>
            
            {voices.length === 0 ? (
              <div className="text-center text-zinc-400 py-12">
                <div className="text-4xl mb-4">📦</div>
                <div>{t('voiceClone.noVoices')}</div>
                <button
                  onClick={() => setActiveTab('upload')}
                  className="mt-4 px-4 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-sm transition"
                >
                  {t('voiceClone.uploadOne')}
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {voices.map(voice => (
                  <div
                    key={voice.id}
                    className="p-4 bg-zinc-800/50 rounded-xl border border-zinc-700"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-white font-bold">{voice.name}</h4>
                      <span className="text-xs text-zinc-400">
                        {t('voiceClone.durationMin', { n: (voice.sample_duration / 60).toFixed(1) })}
                      </span>
                    </div>
                    {voice.description && (
                      <p className="text-sm text-zinc-400 mb-3">{voice.description}</p>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      {voice.tags.map((tag, i) => (
                        <span
                          key={i}
                          className="text-xs px-2 py-1 bg-zinc-700 text-zinc-300 rounded"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                    <button
                      onClick={() => {
                        setSelectedVoice(voice.id);
                        setActiveTab('clone');
                      }}
                      className="mt-3 w-full px-3 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-sm transition"
                    >
                      {t('voiceClone.useVoice')}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default VoiceCloningPanel;