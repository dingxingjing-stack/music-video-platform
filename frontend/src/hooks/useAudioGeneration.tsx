/**
 * useAudioGeneration — AI 音频生成异步 hook（Path A / Path D 等页面使用）
 *
 * 协议与 useAiMusicTask 一致：POST /api/v1/ai/generate -> { task_id } -> 轮询
 * /api/v1/ai/task/{id} 直到 completed/failed/cancelled。
 * - 已移除 SoundHelix mock 兜底（真实音频才可商用），失败即返回 null 并暴露 error。
 * - 429（限流）走 onRateLimited 回调。
 * - 暴露 status/progress/error 供页面展示阶段状态。
 * - 所有请求携带 X-User-ID（当前公测安全限制下的身份绑定）。
 */

import { useState, useCallback } from 'react';
import { getUserId } from './useAiMusicTask';
import { api } from '../config/api';
import { useTranslation } from '../i18n/useTranslation';

const API = api.base;

interface UseAudioGenOptions {
  onSuccess?: (url: string) => void;
  onRateLimited?: () => void;
}

const POLL_INTERVAL = 1500;
const TERMINAL = ['completed', 'failed', 'cancelled'];

export function useAudioGeneration(opts?: UseAudioGenOptions) {
  const [loading, setLoading] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const generate = useCallback(async (endpoint: string, body: Record<string, unknown>) => {
    setLoading(true);
    setError(null);
    setStatus('submitting');
    setProgress(0);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const uid = getUserId();
      if (uid) headers['X-User-ID'] = uid;

      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });

      if (res.status === 429) {
        setRateLimited(true);
        setStatus('rate_limited');
        opts?.onRateLimited?.();
        return null;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      if (!data.success || !data.task_id) {
        throw new Error(data.error || 'API failed');
      }

      const taskId: string = data.task_id;

      // ── 轮询任务状态 ─────────────────────────────
      for (;;) {
        await new Promise(r => setTimeout(r, POLL_INTERVAL));
        const r = await fetch(`${API}/ai/task/${taskId}`, { headers });
        if (!r.ok) throw new Error(t('errors.queryFailed', { status: r.status }));
        const tData = await r.json();
        setStatus(tData.state || '');
        setProgress(tData.progress ?? 0);

        if (tData.state === 'completed') {
          const url = tData.audio_url || tData.url;
          setProgress(100);
          if (url) opts?.onSuccess?.(url);
          return (url as string) || null;
        }
        if (tData.state === 'failed' || tData.state === 'cancelled') {
          const msg = tData.error || (tData.state === 'cancelled' ? t('common.cancelled') : t('errors.generationFailed'));
          setError(msg);
          throw new Error(msg);
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('errors.generationFailed');
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [opts, t]);

  return { loading, generate, rateLimited, setRateLimited, status, progress, error };
}

/** 限流提示横幅 */
export function RateLimitBanner({ onDismiss }: { onDismiss: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[200] bg-[#2a1a1a] border border-[#cc3333] rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3">
      <span className="text-lg">⏳</span>
      <div>
        <p className="text-sm text-[#fca5a5] font-medium">{t('audioGen.rateError')}</p>
        <p className="text-xs text-[#888888]">{t('audioGen.rateLimitDesc')}</p>
      </div>
      <button onClick={onDismiss} className="text-[#888888] hover:text-white ml-2">✕</button>
    </div>
  );
}

/** PathB 占位弹窗 */
export function ComingSoonModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl p-6 max-w-sm mx-4 text-center" onClick={e => e.stopPropagation()}>
        <div className="text-5xl mb-4">🚧</div>
        <h3 className="text-lg font-bold text-white mb-2">{t('comingSoon.title')}</h3>
        <p className="text-sm text-[#888888] mb-4">{t('comingSoon.desc')}</p>
        <button onClick={onClose} className="w-full py-2 rounded-lg bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-medium">{t('comingSoon.ok')}</button>
      </div>
    </div>
  );
}