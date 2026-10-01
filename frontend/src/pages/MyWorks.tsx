import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../config/api';
import { authFetch, AuthenticationError } from '../api/http';
import { useTranslation } from '../i18n/useTranslation';

interface TaskSummary {
  task_id: string;
  state: string;
  progress: number;
  audio_url: string | null;
  stems_state: string | null;
  created_at: number;
  updated_at: number;
}

// 后端 ai_tasks.state 的内部取值 → 用户可读状态词。
// 内部状态标识（completed_with_stems_failed 等）绝不直出；
// 刻意复用通用词，不用 aiStage.generating / aiStage.separating（那两条带模型名）。
const STATE_TEXT_KEY: Record<string, string> = {
  pending: 'aiStage.pending',
  processing: 'aiStage.processing',
  generating: 'aiStage.processing',
  separating: 'aiStage.processing',
  uploading: 'aiStage.uploading',
  completed: 'aiStage.completed',
  completed_with_stems_failed: 'aiStage.completed',
  failed: 'aiStage.failed',
  cancelled: 'aiStage.cancelled',
};

export default function MyWorks() {
  const { t, loading: i18nLoading } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [stemRetrying, setStemRetrying] = useState<Set<string>>(new Set());
  // 正在生成分享链接的任务（飞轮：分享按钮的 in-flight 状态）
  const [sharing, setSharing] = useState<Set<string>>(new Set());

  // completed_with_stems_failed 也是可播放/可下载的完成态（仅缺分轨）
  const isDone = (s: string) => s === 'completed' || s === 'completed_with_stems_failed';

  const stateText = (s: string) => t(STATE_TEXT_KEY[s] ?? 'aiStage.processing');

  const fetchTasks = async () => {
    setLoading(true);
    setError(null);
    try {
      const data: any = await authFetch(api.url('/api/v1/ai/tasks'));
      setTasks(data.tasks || []);
    } catch (e: any) {
      if (e instanceof AuthenticationError) {
        setTasks([]);
      } else {
        // 不直出 e.message：底层异常消息是日志性质（可能为英文），UI 一律走 i18n。
        setError(t('myCreations.loadFailed'));
        setTasks([]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const handleDownload = async (taskId: string, file: string, fmt = 'mp3') => {
    // 授权下载：先经 authFetch 携带 Bearer 换取预签名 URL，再打开（token 不进 URL）。
    if (deleting.has(taskId)) return;
    try {
      const data = await authFetch<{ url: string }>(
        api.url(`/api/v1/ai/task/${taskId}/download?file=${file}&fmt=${fmt}`),
      );
      if (data.url) window.open(data.url, '_blank');
    } catch (e: any) {
      // 不直出 e.message：下载失败复用 aiTask.downloadFailed（带 {status} 插值），
      // 网络类走 errors.networkError；均为现有 key（hi/id/ar 按回退链显示英文）。
      const m = /^HTTP (\d{3})/.exec(e?.message ?? '');
      setError(m ? t('aiTask.downloadFailed', { status: m[1] }) : t('errors.networkError'));
    }
  };

  const handleRetryStems = async (taskId: string) => {
    if (stemRetrying.has(taskId)) return;
    setStemRetrying(prev => new Set([...prev, taskId]));
    try {
      await authFetch(api.url(`/api/v1/ai/task/${taskId}/retry-stems`), { method: 'POST' });
      setTasks(prev => prev.map(tt => tt.task_id === taskId ? { ...tt, state: 'separating', stems_state: null } : tt));
      // 轮询该任务直至回到终态（GET /task/{id} 对外终态含 completed）
      const timer = setInterval(async () => {
        try {
          const d = await authFetch<Record<string, any>>(api.url(`/api/v1/ai/task/${taskId}`));
          if (d.state === 'completed' || d.state === 'failed' || d.state === 'cancelled') {
            clearInterval(timer);
            setStemRetrying(prev => { const n = new Set(prev); n.delete(taskId); return n; });
            setTasks(prev => prev.map(tt => tt.task_id === taskId
              ? { ...tt, state: d.state, stems_state: d.stems_state ?? null, audio_url: d.audio_url ?? tt.audio_url }
              : tt));
          }
        } catch { /* 单次查询失败忽略，等待下一轮 */ }
      }, 2000);
    } catch (e: any) {
      setStemRetrying(prev => { const n = new Set(prev); n.delete(taskId); return n; });
      // 不直出 e.message：HTTP 错误按 http.ts 既有 'HTTP {status}' 契约解析状态码走插值；
      // 会话/超时/网络类（无该前缀）统一走 network 文案。两个 key 均为现有 aiTask.*。
      const m = /^HTTP (\d{3})/.exec(e?.message ?? '');
      setError(m ? t('aiTask.retryFailed', { status: m[1] }) : t('aiTask.retryFailedNetwork'));
    }
  };

  const handlePlay = (audioUrl: string | null) => {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audio.play();
  };

  const handleDelete = async (taskId: string) => {
    if (deleting.has(taskId)) return;
    if (!confirm(t('myCreations.confirmDelete'))) {
      return;
    }
    setDeleting(prev => new Set([...prev, taskId]));
    try {
      await authFetch(api.url(`/api/v1/ai/task/${taskId}`), { method: 'DELETE' });
      setTasks(prev => prev.filter(tt => tt.task_id !== taskId));
    } catch (e: any) {
      // 不直出 e.message：删除失败统一走现有本地化文案。
      setError(t('myCreations.deleteError'));
    } finally {
      setDeleting(prev => {
        const ns = new Set(prev);
        ns.delete(taskId);
        return ns;
      });
    }
  };

  // 分享（PLG 病毒飞轮）：向后端申请签名令牌 → 拼出公开分享链接。
  // 后端会校验作品归属，只能分享自己的作品；令牌为 HMAC 签名，不含 PII。
  const handleShare = async (taskId: string) => {
    setSharing((prev) => new Set(prev).add(taskId));
    try {
      const data = await authFetch<{ token: string }>(
        api.url(`/api/v1/share/task/${taskId}`),
        { method: 'POST' }
      );
      const url = `${window.location.origin}/share/${data.token}`;
      try {
        if (navigator.share) {
          await navigator.share({ title: 'Melovar', text: t('myCreations.shareText'), url });
          return;
        }
        await navigator.clipboard.writeText(url);
        alert(t('myCreations.shareCopied'));
      } catch {
        // 用户取消分享或剪贴板不可用：静默忽略，不打扰
      }
    } catch (e) {
      console.error('生成分享链接失败:', e);
      alert(t('myCreations.shareFailed'));
    } finally {
      setSharing((prev) => {
        const ns = new Set(prev);
        ns.delete(taskId);
        return ns;
      });
    }
  };

  // 文案包是异步 chunk：未就绪时 t() 会原样返回 key（myCreations.empty），
  // 页面就会把 "myCreations.empty" 当成空状态标题显示出来 —— 必须一起等。
  if (loading || i18nLoading) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-10 text-center">
        <div className="animate-pulse flex items-center justify-center h-16 text-[#6a6a6a] text-sm">
          {t('common.loading')}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-10 text-center">
        <p className="text-white">{t('myCreations.loadFailed')}</p>
        <p className="text-sm text-[#8a8a8a] mt-1">{error}</p>
        <button onClick={() => fetchTasks()} className="mt-4 px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium">
          {t('myCreations.retry')}
        </button>
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-16 text-center">
        <div className="w-14 h-14 mx-auto rounded-2xl bg-[#141414] border border-[#1f1f1f] flex items-center justify-center text-xl">♡</div>
        <h1 className="mt-4 text-xl font-bold text-white">{t('myCreations.empty')}</h1>
        <p className="mt-1 text-sm text-[#6a6a6a]">{t('myCreations.emptyDesc')}</p>
        <button
          onClick={() => navigate('/create')}
          className="mt-6 px-6 py-2.5 bg-white text-[#0a0a0a] rounded-xl text-sm font-semibold hover:bg-[#ededed]"
        >
          {t('home.ctaPrimary')}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8">
      <h1 className="text-2xl font-black tracking-tight text-white">{t('myCreations.title')}</h1>
      <p className="text-sm text-[#8a8a8a] mt-1">{t('myCreations.subtitle')}</p>

      <div className="mt-6 grid gap-3">
        {tasks.map((task) => (
          <div
            key={task.task_id}
            className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-4 flex items-center gap-4 group"
          >
            <div className="w-10 h-10 rounded-xl bg-[#0f0f0f] border border-[#1f1f1f] flex items-center justify-center text-lg shrink-0">
              {isDone(task.state) || task.state === 'separating' ? '♪' : task.state === 'failed' ? '✕' : '◐'}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-white text-sm font-medium truncate">
                {t('myCreations.taskPrefix')} {task.task_id.substring(0, 8)}
                {isDone(task.state) && (
                  <span className="ms-2 inline-block align-middle px-1.5 py-0.5 rounded-md bg-[#ff6a10]/15 border border-[#ff6a10]/30 text-[#ff8a3d] text-[10px] font-semibold tracking-wide">
                    {t('common.aiGenerated')}
                  </span>
                )}
              </h3>
              <p className="text-xs text-[#6a6a6a]">
                {stateText(task.state)} · {formatTime(task.progress)} · {new Date(task.created_at * 1000).toLocaleDateString()}
              </p>
              {isDone(task.state) && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {task.stems_state === 'ok' && (['vocals', 'drums', 'bass', 'other'] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => handleDownload(task.task_id, s)}
                      className="px-2 py-0.5 rounded-lg bg-[#0f0f0f] border border-[#262626] text-[#b0b0b0] text-[11px] hover:text-white"
                    >
                      {t(`aiStem.${s}`)} ↓
                    </button>
                  ))}
                  {/* 分轨失败：production 无可用分轨能力，重试必然失败，故只陈述事实不提供操作 */}
                  {task.stems_state === 'failed' && (
                    <span className="px-2 py-0.5 rounded-lg bg-[#0f0f0f] border border-[#262626] text-[#8a8a8a] text-[11px]">
                      {t('aiGen.stemsFailedHint')}
                    </span>
                  )}
                </div>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              {task.audio_url && (
                <button
                  className="px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] text-white rounded-xl text-xs hover:bg-[#222222]"
                  onClick={() => handlePlay(task.audio_url)}>
                  {t('myCreations.play')}
                </button>
              )}
              <button
                className="px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] text-white rounded-xl text-xs hover:bg-[#222222]"
                onClick={() => handleDownload(task.task_id, 'full')}>
                {t('myCreations.download')}
              </button>
              {isDone(task.state) && (
                <button
                  className="px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] text-white rounded-xl text-xs hover:bg-[#222222] disabled:opacity-40"
                  disabled={sharing.has(task.task_id)}
                  onClick={() => handleShare(task.task_id)}
                >
                  {sharing.has(task.task_id) ? '...' : t('myCreations.share')}
                </button>
              )}
              <button
                className="px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] text-[#ff6b6b] rounded-xl text-xs hover:bg-[#1f1a1a] disabled:opacity-40"
                disabled={!isDone(task.state) && !deleting.has(task.task_id) && task.state !== 'separating'}
                onClick={() => handleDelete(task.task_id)}
              >
                {deleting.has(task.task_id) ? t('myCreations.deleting') : t('myCreations.delete')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
