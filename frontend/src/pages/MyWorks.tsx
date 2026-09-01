import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../config/api';
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

export default function MyWorks() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  const getUserId = (): string | undefined => user?.id || undefined;

  const fetchTasks = async () => {
    const uid = getUserId();
    if (!uid) {
      setLoading(false);
      setTasks([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(api.url('/api/v1/ai/tasks'), {
        headers: {
          'Content-Type': 'application/json',
          'X-User-ID': uid,
        },
      });
      if (!res.ok) throw new Error(t('myCreations.loadFailed'));
      const data: any = await res.json();
      setTasks(data.tasks || []);
    } catch (e: any) {
      setError(e?.message || t('myCreations.loadFailed'));
      setTasks([]);
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

  const handleDownload = (taskId: string, file: string, fmt = 'mp3') => {
    window.open(api.url(`/api/v1/ai/task/${taskId}/download?file=${file}&fmt=${fmt}`), '_blank');
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
      const res = await fetch(api.url(`/api/v1/ai/task/${taskId}/delete`), {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-User-ID': getUserId() || '',
        },
      });
      const data = await res.json();
      if (res.ok) {
        setTasks(prev => prev.filter(tt => tt.task_id !== taskId));
      } else {
        setError(data.detail || t('myCreations.deleteFailed'));
      }
    } catch (e: any) {
      setError(e?.message || t('myCreations.deleteError'));
    } finally {
      setDeleting(prev => {
        const ns = new Set(prev);
        ns.delete(taskId);
        return ns;
      });
    }
  };

  if (loading) {
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
              {task.state === 'completed' ? '♪' : task.state === 'generating' ? '◐' : '✕'}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-white text-sm font-medium truncate">
                {t('myCreations.taskPrefix')} {task.task_id.substring(0, 8)}
              </h3>
              <p className="text-xs text-[#6a6a6a]">
                {task.state} · {formatTime(task.progress)} · {new Date(task.created_at * 1000).toLocaleDateString()}
              </p>
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
              <button
                className="px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] text-[#ff6b6b] rounded-xl text-xs hover:bg-[#1f1a1a] disabled:opacity-40"
                disabled={task.state !== 'completed' && !deleting.has(task.task_id)}
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
