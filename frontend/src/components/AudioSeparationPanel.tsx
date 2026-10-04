/**
 * 音频分离组件（P2：TemPolor Stems v2 已启用）
 *
 * 功能:
 * - 上传音频文件（≤50MB）
 * - 异步任务提交 + 轮询（后端: POST /api/v1/ai/stems/separate → GET /stems/task/{id}）
 * - 四轨 + 原曲播放预览 (人声/鼓/贝斯/其他/原曲)
 * - 分轨下载（FLAC）
 * - 计价展示：60 Credits / 次（不足 402 提示；失败/超时后端自动退回）
 *
 * 安全边界（不得出现）：API endpoint 细节、callback、provider 名称、
 * item_id、R2 key / 签名参数 —— 前端只拿到后端签发的短期预签名 URL。
 */

import { useState, useRef, useEffect } from 'react';
import { api } from '../config/api';
import { supabase } from '../lib/supabase';
import { useTranslation } from '../i18n/useTranslation';

// P2：后端已接入 TemPolor Stems v2（生产 fail-closed 语义保留在后端：
// 未配置 callback/密钥时后端自行拒绝，前端无需再关心 provider 细节）。
const SEPARATION_AVAILABLE: boolean = true;

const STEMS_POLL_INTERVAL_MS = 3000;
const STEMS_POLL_MAX_MS = 10 * 60 * 1000; // 与后端单任务 10 分钟硬顶一致

export function AudioSeparationPanel() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [isSeparating, setIsSeparating] = useState(false);
  const [progress, setProgress] = useState(0);
  // 逻辑名 → 后端签发的短期预签名 URL（vocals/drums/bass/other[/original]）
  const [stems, setStems] = useState<Record<string, string>>({});
  const [error, setError] = useState('');

  const audioRefs = useRef<{ [key: string]: HTMLAudioElement | null }>({});
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const STEM_LABELS: Array<[string, string]> = [
    ['vocals', t('separation.vocals')],
    ['drums', t('separation.drums')],
    ['bass', t('separation.bass')],
    ['other', t('separation.other')],
  ];

  // 组件卸载时停止轮询，避免内存泄漏
  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  const authHeaders = async (): Promise<Record<string, string>> => {
    const { data: sess } = await supabase.auth.getSession();
    const token = sess?.session?.access_token;
    if (!token) throw new Error(t('auth.pleaseLogin'));
    return { Authorization: `Bearer ${token}` };
  };

  // 提交并轮询直到终态
  const handleSeparate = async () => {
    if (!file) return;

    setIsSeparating(true);
    setProgress(0);
    setError('');
    setStems({});

    try {
      const headers = await authHeaders();

      // 提交（multipart：不能走 authFetch 的固定 JSON Content-Type）
      const form = new FormData();
      form.append('file', file);
      const submitResp = await fetch(api.url('/api/v1/ai/stems/separate'), {
        method: 'POST',
        headers,
        body: form,
      });

      if (submitResp.status === 401) throw new Error(t('auth.pleaseLogin'));
      if (submitResp.status === 402) throw new Error(t('separation.insufficientCredits'));
      if (submitResp.status === 429) throw new Error(t('errors.rateLimited'));
      const submitData = await submitResp.json().catch(() => ({}));
      if (!submitResp.ok || !submitData.success) {
        throw new Error(submitData.detail || t('separation.failed'));
      }

      const taskId: string = submitData.task_id;
      if (!taskId) throw new Error(t('separation.failed'));

      // 轮询任务状态（后端 10 分钟硬顶，超时自动退款）
      const startedAt = Date.now();
      const poll = async () => {
        try {
          const h = await authHeaders();
          const resp = await fetch(api.url(`/api/v1/ai/stems/task/${taskId}`), { headers: h });
          if (resp.status === 401) throw new Error(t('auth.pleaseLogin'));
          if (!resp.ok) throw new Error(t('separation.failedRetry'));
          const data = await resp.json();

          setProgress(Math.min(95, Number(data.progress) || 0));

          if (data.state === 'completed' && data.stems_state === 'ok' && data.stems) {
            setStems(data.stems as Record<string, string>);
            setProgress(100);
            setIsSeparating(false);
            return;
          }
          if (data.state === 'failed' || data.state === 'completed_with_stems_failed') {
            const msg = String(data.error || '');
            throw new Error(
              msg.includes('超时') ? t('separation.timeout') : t('separation.failedRetry')
            );
          }

          if (Date.now() - startedAt > STEMS_POLL_MAX_MS) {
            throw new Error(t('separation.timeout'));
          }
          pollTimer.current = setTimeout(poll, STEMS_POLL_INTERVAL_MS);
        } catch (err: any) {
          setError(err.message || t('separation.failedRetry'));
          setIsSeparating(false);
        }
      };
      poll();
    } catch (err: any) {
      setError(err.message || t('separation.failedRetry'));
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

  // 下载分轨（Stems v2 产物为 FLAC）
  const downloadStem = (url: string, name: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.flac`;
    a.click();
  };

  const stemEntries = STEM_LABELS.filter(([key]) => stems[key]);
  const hasOriginal = Boolean(stems.original);

  return (
    <div className="p-6 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-white mb-2">
          🎵 {t('separation.title')}
        </h2>
        {/* P2 计价展示：60 Credits / 次 */}
        <p className="text-sm text-gray-400 mb-4">{t('separation.credits')}</p>

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
                  {t('separation.supported')} · ≤50MB
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* 分离按钮 */}
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

        {/* 分离结果：4 分轨 */}
        {stemEntries.length > 0 && (
          <div className="mt-8">
            <h3 className="text-xl font-bold text-white mb-4">
              ✅ {t('separation.completed')}
            </h3>

            <div className="space-y-4">
              {stemEntries.map(([key, label]) => (
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
                        onClick={() => downloadStem(stems[key], key)}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⬇️ {t('separation.download')}
                      </button>
                    </div>
                  </div>

                  <audio
                    ref={(el) => (audioRefs.current[key] = el)}
                    src={stems[key]}
                    className="w-full"
                  />
                </div>
              ))}

              {/* 原曲 */}
              {hasOriginal && (
                <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-lg font-semibold text-white">
                      {t('separation.original')}
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => playStem('original')}
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
                        onClick={() => downloadStem(stems.original, 'original')}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⬇️ {t('separation.download')}
                      </button>
                    </div>
                  </div>
                  <audio
                    ref={(el) => (audioRefs.current['original'] = el)}
                    src={stems.original}
                    className="w-full"
                  />
                </div>
              )}
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
