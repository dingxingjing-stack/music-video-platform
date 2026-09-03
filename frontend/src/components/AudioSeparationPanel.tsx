/**
 * 音频分离组件 (Demucs)
 * 
 * 功能:
 * - 上传音频文件
 * - 选择{t('separation.model')}
 * - 实时进度显示
 * - 四轨播放预览 (人声/鼓/贝斯/其他)
 * - 分轨下载
 */

import { useState, useRef } from 'react';
import { api } from '../config/api';
import { useTranslation } from '../i18n/useTranslation';

export function AudioSeparationPanel() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [isSeparating, setIsSeparating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stems, setStems] = useState<string[]>([]);
  const [model, setModel] = useState('htdemucs');
  const [error, setError] = useState('');
  
  const audioRefs = useRef<{ [key: string]: HTMLAudioElement | null }>({});

  const STEM_LABELS = {
    vocals: t('separation.vocals'),
    drums: t('separation.drums'),
    bass: t('separation.bass'),
    other: t('separation.other'),
  };

  // 上传并分离
  const handleSeparate = async () => {
    if (!file) return;

    setIsSeparating(true);
    setProgress(0);
    setError('');
    setStems([]);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model', model);

    try {
      const response = await fetch(api.url('/api/v1/audio/separate'), {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.message || t('separation.failed'));
      }

      setStems(data.stems);
      setProgress(100);
    } catch (err: any) {
      setError(err.message || t('separation.failedRetry'));
    } finally {
      setIsSeparating(false);
    }
  };

  // 播放单独轨道
  const playStem = (stemName: string) => {
    const audio = audioRefs.current[stemName];
    if (audio) {
      audio.play();
    }
  };

  // 停止所有轨道
  const stopAll = () => {
    Object.values(audioRefs.current).forEach(audio => {
      if (audio) {
        audio.pause();
        audio.currentTime = 0;
      }
    });
  };

  // 下载分轨
  const downloadStem = (url: string, name: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.wav`;
    a.click();
  };

  return (
    <div className="p-6 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-white mb-6">
          🎵 {t('separation.title')}
        </h2>

        {/* 上传区域 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('separation.selectFile')}
          </label>
          <div className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center hover:border-orange-500 transition-colors">
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
              id="audio-upload"
            />
            <label htmlFor="audio-upload" className="cursor-pointer">
              <div className="text-gray-400">
                <span className="text-4xl">📁</span>
                <p className="mt-2">
                  {file ? file.name : t('separation.dropOrClick')}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {t('separation.supported')}
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* 模型选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('separation.model')}
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-orange-500"
          >
            <option value="htdemucs">{t('separation.modelHtdemucs')}</option>
            <option value="htdemucs_ft">{t('separation.modelFt')}</option>
            <option value="htdemucs_6s">{t('separation.model6s')}</option>
          </select>
        </div>

        {/* 分离按钮 */}
        <button
          onClick={handleSeparate}
          disabled={!file || isSeparating}
          className={`w-full py-3 rounded-lg font-semibold transition-all ${
            !file || isSeparating
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-orange-500 to-pink-500 text-white hover:opacity-90'
          }`}
        >
          {isSeparating ? t('separation.processing', { progress: progress.toFixed(0) }) : t('separation.start')}
        </button>

        {/* 进度条 */}
        {isSeparating && (
          <div className="mt-4">
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* 错误信息 */}
        {error && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-500 rounded-lg text-red-300">
            ❌ {error}
          </div>
        )}

        {/* 分离结果 */}
        {stems.length > 0 && (
          <div className="mt-8">
            <h3 className="text-xl font-bold text-white mb-4">
              ✅ {t('separation.completed')}
            </h3>

            <div className="space-y-4">
              {Object.entries(STEM_LABELS).map(([key, label], idx) => (
                <div
                  key={key}
                  className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-lg font-semibold text-white">
                      {label}
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => playStem(key)}
                        className="px-3 py-1 bg-orange-500 text-white text-sm rounded hover:bg-orange-600"
                      >
                        ▶️ {t('separation.play')}
                      </button>
                      <button
                        onClick={() => stopAll()}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⏹️ {t('separation.stop')}
                      </button>
                      <button
                        onClick={() => downloadStem(stems[idx], key)}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⬇️ {t('separation.download')}
                      </button>
                    </div>
                  </div>

                  <audio
                    ref={(el) => (audioRefs.current[key] = el)}
                    src={stems[idx]}
                    className="w-full"
                  />
                </div>
              ))}
            </div>

            <div className="mt-6 p-4 bg-blue-900/30 border border-blue-500 rounded-lg text-blue-300">
              💡 <strong>{t('separation.tipLabel')}:</strong> {t('separation.tip')}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}