/**
 * useAiMusicTask — AI 音乐生成异步任务 hook（对接后端 /api/v1/ai/*）
 *
 * 协议（复用后端现有 task_id / stems / stems_state，不另建第二套任务系统）：
 *   POST /api/v1/ai/generate              -> { task_id, status_url }
 *   轮询 GET /api/v1/ai/task/{task_id}    -> state 变化
 *         pending -> processing -> generating -> separating -> uploading
 *         -> completed | failed | cancelled
 *   completed 时返回：audio_url（完整歌，预签名）、stems{4轨，预签名}、stems_state
 *   POST /api/v1/ai/task/{id}/retry-stems -> 分轨失败重试（不扣生成额度，受 MAX_AUTO_RETRIES 限制）
 *   GET  /api/v1/ai/task/{id}/download    -> 授权下载预签名 URL（owner 归属校验）
 *
 * 安全：所有请求携带 Authorization: Bearer <Supabase access_token>（Phase 3B-2 后统一由 authFetch 注入，
 * 不再使用 X-User-ID / localStorage 自造用户）。
 * 前端不接触 Modal 内部路径 / R2 密钥 / 永久 URL，仅使用后端签发的短期预签名 URL。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../config/api';

export const AI_API_BASE = api.url('/api/v1/ai');

import { authFetch, AuthenticationError } from '../api/http';

export type AiStage =
  | 'idle' | 'pending' | 'processing' | 'generating' | 'separating' | 'uploading'
  | 'completed' | 'failed' | 'cancelled';

export type StemsState = 'ok' | 'failed' | 'skipped' | null;

export interface AiStems {
  vocals?: string;
  drums?: string;
  bass?: string;
  other?: string;
}

/**
 * 结构化任务错误。hook 只返回 key（+动态参数），不直接写任何语言文本；
 * UI 层渲染时用 resolveTaskError(t, err) 翻译，保证跟随当前 locale。
 */
export interface TaskError {
  key: string;
  status?: number | string;
}

export interface AiMusicTask {
  taskId: string | null;
  stage: AiStage;
  progress: number;
  audioUrl: string | null;
  stems: AiStems | null;
  stemsState: StemsState;
  error: string | TaskError | null;
  retries: number;
  stemRetries: number;
}

/** 把 task.error 解析为最终展示文本（string 透传多为后端返回信息；对象走 t 翻译）。 */
export function resolveTaskError(
  t: (key: string, params?: Record<string, string | number>) => string,
  err: string | TaskError | null | undefined,
): string | null {
  if (err == null) return null;
  if (typeof err === 'string') return err;
  return t(err.key, err.status === undefined ? undefined : { status: err.status });
}

/** 供 download() 等 Promise 场景抛出结构化错误（Error.message 保持可读的 key 本身）。 */
function throwTaskError(key: string, status?: number | string): never {
  const err = new Error(key);
  (err as unknown as { taskError: TaskError }).taskError =
    status === undefined ? { key } : { key, status };
  throw err;
}

/** 从 download() 抛出的 Error 中取出结构化 i18n 错误（若有）。 */
export function getThrownTaskError(e: unknown): TaskError | undefined {
  if (e instanceof Error) {
    const info = (e as unknown as { taskError?: TaskError }).taskError;
    if (info && typeof info.key === 'string') return info;
  }
  return undefined;
}

export const STAGE_LABEL: Record<AiStage, string> = {
  idle: 'aiStage.idle',
  pending: 'aiStage.pending',
  processing: 'aiStage.processing',
  generating: 'aiStage.generating',
  separating: 'aiStage.separating',
  uploading: 'aiStage.uploading',
  completed: 'aiStage.completed',
  failed: 'aiStage.failed',
  cancelled: 'aiStage.cancelled',
};

export const STEM_NAMES: { key: keyof AiStems; label: string; color: string }[] = [
  { key: 'vocals', label: 'aiStem.vocals', color: '#ef4444' },
  { key: 'drums', label: 'aiStem.drums', color: '#3b82f6' },
  { key: 'bass', label: 'aiStem.bass', color: '#22c55e' },
  { key: 'other', label: 'aiStem.other', color: '#a855f7' },
];

const EMPTY: AiMusicTask = {
  taskId: null,
  stage: 'idle',
  progress: 0,
  audioUrl: null,
  stems: null,
  stemsState: null,
  error: null,
  retries: 0,
  stemRetries: 0,
};

const TERMINAL: AiStage[] = ['completed', 'failed', 'cancelled'];

export interface GenerateParams {
  prompt: string;
  style?: string;
  duration?: number;
  lyrics?: string | null;
  type?: string;
}

export function useAiMusicTask() {
  const [task, setTask] = useState<AiMusicTask>(EMPTY);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const poll = useCallback((taskId: string) => {
    const tick = async () => {
      if (!mountedRef.current) return;
      try {
        const d = await authFetch<Record<string, any>>(`${AI_API_BASE}/task/${taskId}`);
        if (mountedRef.current) {
          setTask({
            taskId,
            stage: d.state,
            progress: d.progress ?? 0,
            audioUrl: d.audio_url || null,
            stems: d.stems || null,
            stemsState: d.stems_state || null,
            error: d.error || null,
            retries: d.retries ?? 0,
            stemRetries: d.stem_retries ?? 0,
          });
        }
        if (TERMINAL.includes(d.state)) {
          setLoading(false);
          return;
        }
      } catch (e) {
        if (mountedRef.current) {
          if (e instanceof AuthenticationError) {
            setTask(t => ({ ...t, stage: 'failed', error: { key: 'aiTask.authRequired', status: 401 } }));
          } else {
            setTask(t => ({ ...t, error: { key: 'aiTask.queryFailed' } }));
          }
        }
        setLoading(false);
        return;
      }
      if (mountedRef.current) timerRef.current = setTimeout(tick, 1500);
    };
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(tick, 300);
  }, []);

  const submit = useCallback(async (params: GenerateParams): Promise<string | null> => {
    setLoading(true);
    setTask(EMPTY);
    try {
      const d = await authFetch<{ success?: boolean; task_id?: string; error?: any }>(`${AI_API_BASE}/generate`, {
        method: 'POST',
        body: { type: 'song', ...params },
      });
      if (!d.success || !d.task_id) {
        if (mountedRef.current) {
          setTask({ ...EMPTY, stage: 'failed', error: d.error || { key: 'aiTask.submitFailed' } });
        }
        setLoading(false);
        return null;
      }
      const taskId: string = d.task_id;
      if (mountedRef.current) setTask({ ...EMPTY, taskId, stage: 'pending' });
      poll(taskId);
      return taskId;
    } catch (e) {
      if (mountedRef.current) {
        if (e instanceof AuthenticationError) {
          setTask({ ...EMPTY, stage: 'failed', error: { key: 'aiTask.authRequired', status: 401 } });
        } else {
          setTask({ ...EMPTY, stage: 'failed', error: { key: 'aiTask.submitFailedNetwork' } });
        }
      }
      setLoading(false);
      return null;
    }
  }, [poll]);

  const retryStems = useCallback(async () => {
    if (!task.taskId) return;
    try {
      await authFetch(`${AI_API_BASE}/task/${task.taskId}/retry-stems`, { method: 'POST' });
      setLoading(true);
      if (mountedRef.current) setTask(t => ({ ...t, stage: 'separating', error: null, stemRetries: t.stemRetries + 1 }));
      poll(task.taskId);
    } catch (e) {
      if (mountedRef.current) {
        if (e instanceof AuthenticationError) {
          setTask(t => ({ ...t, error: { key: 'aiTask.authRequired', status: 401 } }));
        } else {
          setTask(t => ({ ...t, error: { key: 'aiTask.retryFailedNetwork' } }));
        }
      }
    }
  }, [task.taskId, poll]);

  const download = useCallback(
    async (file: 'full' | 'vocals' | 'drums' | 'bass' | 'other', fmt = 'mp3'): Promise<string> => {
      if (!task.taskId) throwTaskError('aiTask.taskNotFound');
      try {
        const d = await authFetch<{ url: string }>(
          `${AI_API_BASE}/task/${task.taskId}/download?file=${file}&fmt=${fmt}`,
        );
        return d.url;
      } catch (e) {
        if (e instanceof AuthenticationError) throw new Error('Authentication required');
        if (e instanceof Error && e.message.startsWith('HTTP ')) throw e;
        throwTaskError('aiTask.downloadFailed');
      }
    },
    [task.taskId],
  );

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setTask(EMPTY);
    setLoading(false);
  }, []);

  return { task, loading, submit, retryStems, download, reset };
}