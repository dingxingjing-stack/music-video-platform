/**
 * 音频分离组件
 * 
 * 功能:
 * - 上传音频文件
 * - 实时进度显示
 * - 四轨播放预览 (人声/鼓/贝斯/其他)
 * - 分轨下载
 */

import { useState, useRef } from 'react';
import { api } from '../config/api';
import { supabase } from '../lib/supabase';
import { useTranslation } from '../i18n/useTranslation';

// 当前生产没有可用的 stem separation（后端在 ENVIRONMENT=production 直接返回不可用），
// 因此这个页面上的 Start 必须始终不可执行。将来接上真实能力时改回 true 即可。
const SEPARATION_AVAILABLE: boolean = false;

export function AudioSeparationPanel() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [isSeparating, setIsSeparating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stems, setStems] = useState<string[]>([]);
  // 后端 production 分离实现从不读取该参数（P3-3 审计），保留发送以维持既有请求契约。
  const [model] = useState('htdemucs');
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
      // 后端 /audio/separate 强制 JWT（get_verified_user_id）；FormData 不能走 authFetch
      // （其固定 Content-Type: application/json 会破坏 multipart 边界），手动注入 Authorization。
      const { data: sess } = await supabase.auth.getSession();
      const token = sess?.session?.access_token;
      if (!token) throw new Error(t('auth.pleaseLogin'));

      const response = await fetch(api.url('/api/v1/audio/separate'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await response.json();

      if (response.status === 401) throw new Error(t('auth.pleaseLogin'));
      if (response.status === 429) throw new Error(t('errors.rateLimited'));
      if (!response.ok || !data.success) {
        // 机器可读错误码优先：映射到前端既有的不可用文案，不回显后端英文 message。
        if (data?.error_code === 'stem_separation_unavailable') {
          throw new Error(t('audioTools.separationDesc'));
        }
        // 未知 error_code / 无 error_code：保留原有 detail→message→本地兜底顺序。
        throw new Error(data.detail || data.message || t('separation.failed'));
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

        {/* 生产后端当前没有可用的分轨能力：页面级明示（复用既有 i18n，不新增 key） */}
        <div className="mb-6 p-4 rounded-lg bg-gray-800/60 border border-gray-600 flex items-center gap-3">
          <span className="shrink-0 px-3 py-1 rounded-full bg-gray-700 border border-gray-600 text-xs text-gray-300">
            {t('audioTools.comingSoon')}
          </span>
          <span className="text-sm text-gray-300">{t('audioTools.separationDesc')}</span>
        </div>

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

        {/* 分离按钮：能力开关为 false 时始终禁用，避免呈现一个必然失败的操作 */}
        <button
          onClick={handleSeparate}
          disabled={!file || isSeparating || !SEPARATION_AVAILABLE}
          className={`w-full py-3 rounded-lg font-semibold transition-all ${
            !file || isSeparating || !SEPARATION_AVAILABLE
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