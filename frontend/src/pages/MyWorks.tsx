import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../config/api';

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
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  // 获取当前用户 ID
  const getUserId = (): string | undefined => {
    if (!user?.id) return undefined;
    return user.id;
  };

  // 获取当前用户的任务列表
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
      if (!res.ok) throw new Error('获取任务列表失败');
      const data: any = await res.json();
      setTasks(data.tasks || []);
    } catch (e: any) {
      setError(e?.message || '获取任务列表失败');
      setTasks([]);
    } finally {
      setLoading(false);
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const filtered = tasks.length > 0 ? tasks : [];

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const handleDownload = (taskId: string, file: string, fmt = 'mp3') => {
    window.open(`/api/v1/ai/task/${taskId}/download?file=${file}&fmt=${fmt}`, '_blank');
  };

  const handlePlay = (audioUrl: string | null) => {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audio.play();
  };

  const handleDelete = async (taskId: string) => {
    if (deleting.has(taskId)) return;
    
    if (!confirm('确定要删除这首作品吗？此操作将删除数据库记录和 R2 存储的音频文件。')) {
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
        // 删除成功：从列表中移除
        setTasks(prev => prev.filter(t => t.task_id !== taskId));
      } else {
        // 删除失败：显示错误
        setError(data.detail || '删除失败，请重试');
      }
    } catch (e: any) {
      setError(e?.message || '删除过程中发生错误');
    } finally {
      setDeleting(prev => {
        const newSet = new Set(prev);
        newSet.delete(taskId);
        return newSet;
      });
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-6 text-center">
        <div className="animate-pulse flex items-center justify-center h-16 text-muted">
          <svg className="w-6 h-6 mr-2" viewBox="0 0 24 24">
            <path
              d="M12 1v2m0 16v-2m7-3a9 9 0 11-18 0 9 9 0 0118 0m-7 3a9 9 0 10-18 0 9 9 0 0118 0"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>加载作品</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-6 text-center">
        <svg
          className="w-6 h-6 mx-auto mb-2"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <circle cx="12" cy="12" r="10" />
          <path
            d="M12 6v6l4 4"
            strokeWidth="1.5"
          />
        </svg>
        <p className="mt-4 text-lg">加载作品列表时出错</p>
        <p className="text-sm">{error}</p>
        <button onClick={() => fetchTasks()} className="mt-2 btn-base text-primary">
          重试
        </button>
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-6 text-center">
        <svg
          className="w-8 h-8 mx-auto mb-4 text-muted"
          viewBox="0 0 24 24"
        >
          <path
            d="M9 5H7a2 2 0 01-2-2V3a2 2 0 012-2h4a2 2 0 012-2v2m2 4H7a2 2 0 01-2-2V5a2 2 0 012-2h4a2 2 0 012 2v2m2 4h2a2 2 0 012 2v2a2 2 0 01-2 2h-4v-2zm10-5a2 2 0 11-4 0 2 2 0 014 0m-4 7a2 2 0 100 4 2 2 0 000-4m0 7a2 2 0 100 4 2 2 0 000-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
        <p className="text-secondary mb-2">还没有作品</p>
        <p className="text-sm text-muted">
          去创作页面生成你的第一个作品吧
        </p>
        <button
          onClick={() => navigate('/path-a')}
          className="mt-3 btn-base px-6 py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg font-medium"
        >
          🎵 开始创作
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold gradient-text mb-1">💿 我的作品</h1>
      <p className="text-sm text-muted mb-6">
        统一管理你创作的所有音频与分轨
      </p>

      <div className="flex gap-2 mb-6">
        {['all', 'audio', 'midi'].map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t as 'all' | 'audio' | 'midi')}
            className={
              `px-4 py-2 rounded-lg text-sm font-medium transition ${
                filter === t
                  ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                  : 'bg-elevated text-secondary hover:text-white'
              }`
            }
          >
            {t === 'all'
              ? '全部'
              : t === 'audio'
                ? '🎵 音频'
                : '🎹 MIDI'}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-20 card-solid">
          <div className="text-5xl mb-4">🎶</div>
          <p className="text-secondary mb-2">还没有作品</p>
          <p className="text-sm text-muted">
            去创作页面生成你的第一个作品吧
          </p>
          <button
            onClick={() => navigate('/path-a')}
            className="btn-base px-6 py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg font-medium"
          >
            🎵 开始创作
          </button>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((task) => (
            <div
              key={task.task_id}
              className="card-solid p-4 flex items-center gap-4 group"
            >
              <div
                className="w-10 h-10 rounded-lg bg-gradient-to-br from-orange-500/20 to-pink-500/20 flex items-center justify-center text-lg"
              >
                {task.state === 'completed' ? '🎵' : task.state === 'generating' ? '⏳' : '❌'}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-medium truncate">
                  任务 {task.task_id.substring(0, 8)}
                </h3>
                <p className="text-xs text-muted">
                  {task.state}
                  · {formatTime(task.progress)}
                  · {new Date(task.created_at * 1000).toLocaleDateString()}
                </p>
              </div>
              <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition">
                {task.audio_url && (
                  <button
                    className="btn-base px-3 py-1.5 bg-elevated text-secondary hover:text-white rounded-lg text-xs"
                    onClick={() => handlePlay(task.audio_url)}>
                  ▶️ 播放
                </button>
                )}
                <button
                  className="btn-base px-3 py-1.5 bg-elevated text-secondary hover:text-white rounded-lg text-xs"
                  onClick={() => handleDownload(task.task_id, 'full')}>
                  ⬇️ 下载
                </button>
                <button
                  className="btn-base px-3 py-1.5 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg text-xs"
                  disabled={task.state !== 'completed'}
                  onClick={() => handleDelete(task.task_id)}
                >
                  📋 删除
                  {deleting.has(task.task_id) && (
                    <span className="text-xs text-gray-500 ml-1">删除中...</span>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
}
}
