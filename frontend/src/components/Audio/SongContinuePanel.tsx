import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { WaveformEditor } from './Audio/WaveformEditor';

interface SongContinuePanelProps {
  /** 当前播放的音频 URL */
  audioUrl: string | null;
  /** 当前任务 ID（用于续写） */
  taskId: string | null;
  /** 当前歌曲时长（秒） */
  currentDuration: number;
  /** 回调：请求续写 */
  onContinue: (request: ContinueRequest) => Promise<void>;
  /** 回调：取消续写面板 */
  onClose?: () => void;
  /** 是否显示面板 */
  isOpen: boolean;
  /** 用户 ID（用于 API 调用） */
  userId: string;
}

interface ContinueRequest {
  source_task_id: string;
  mode: 'auto' | 'keep_style' | 'new_style' | 'variation' | 'bridge' | 'outro_extend';
  style?: string;
  duration?: number;
  prompt: string;
  lyrics: string;
}

interface TaskStatus {
  task_id: string;
  status: string;
  progress: {
    stage: string;
    message: string;
    percent: number;
    current_step?: number;
    total_steps?: number;
    current_segment?: number;
    total_segments?: number;
    segment_name?: string;
  };
  result?: {
    success: boolean;
    audio_url: string;
    duration: number;
    manifest?: any;
  };
  error?: string;
}

const DURATION_OPTIONS = [
  { value: 'auto', label: 'continue.durAuto' },
  { value: 10, label: 'continue.dur10' },
  { value: 20, label: 'continue.dur20' },
  { value: 30, label: 'continue.dur30' },
  { value: 40, label: 'continue.dur40' },
  { value: 60, label: 'continue.dur60' },
  { value: 80, label: 'continue.dur80' },
  { value: 100, label: 'continue.dur100' },
  { value: 120, label: 'continue.dur120' },
];

const MODE_OPTIONS = [
  { value: 'auto', label: 'continue.modeAuto', description: 'continue.modeAutoDesc' },
  { value: 'keep_style', label: 'continue.modeKeep', description: 'continue.modeKeepDesc' },
  { value: 'new_style', label: 'continue.modeNew', description: 'continue.modeNewDesc' },
  { value: 'variation', label: 'continue.modeVariation', description: 'continue.modeVariationDesc' },
  { value: 'bridge', label: 'continue.modeBridge', description: 'continue.modeBridgeDesc' },
  { value: 'outro_extend', label: 'continue.modeOutro', description: 'continue.modeOutroDesc' },
];

const STYLE_OPTIONS = [
  { value: 'pop', label: 'continue.style.pop' },
  { value: 'rock', label: 'continue.style.rock' },
  { value: 'electronic', label: 'continue.style.electronic' },
  { value: 'hip-hop', label: 'continue.style.hiphop' },
  { value: 'r&b', label: 'continue.style.rnb' },
  { value: 'jazz', label: 'continue.style.jazz' },
  { value: 'classical', label: 'continue.style.classical' },
  { value: 'ambient', label: 'continue.style.ambient' },
  { value: 'cinematic', label: 'continue.style.cinematic' },
  { value: 'lo-fi', label: 'continue.style.lofi' },
  { value: 'country', label: 'continue.style.country' },
  { value: 'folk', label: 'continue.style.folk' },
  { value: 'reggae', label: 'continue.style.reggae' },
  { value: 'blues', label: 'continue.style.blues' },
  { value: 'funk', label: 'continue.style.funk' },
  { value: 'disco', label: 'continue.style.disco' },
  { value: 'house', label: 'continue.style.house' },
  { value: 'techno', label: 'continue.style.techno' },
  { value: 'trance', label: 'continue.style.trance' },
  { value: 'dubstep', label: 'continue.style.dubstep' },
  { value: 'drum-and-bass', label: 'continue.style.drumBass' },
];

export function SongContinuePanel({
  audioUrl,
  taskId,
  currentDuration,
  onContinue,
  onClose,
  isOpen,
  userId,
}: SongContinuePanelProps) {
  const { t } = useTranslation();
  
  const [mode, setMode] = useState<'auto' | 'keep_style' | 'new_style' | 'variation' | 'bridge' | 'outro_extend'>('auto');
  const [style, setStyle] = useState<string>('pop');
  const [duration, setDuration] = useState<string | number>('auto');
  const [prompt, setPrompt] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [continuationTaskId, setContinuationTaskId] = useState<string | null>(null);
  const [continuationStatus, setContinuationStatus] = useState<TaskStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const maxDuration = 330; // 5:30
  const remainingTime = maxDuration - currentDuration;
  const canContinue = remainingTime >= 10 && taskId && audioUrl;

  // 计算建议的续写时长
  const suggestedDuration = useCallback(() => {
    if (currentDuration < 60) return 60;
    if (currentDuration < 120) return 60;
    if (currentDuration < 180) return 60;
    if (currentDuration < 240) return 45;
    if (currentDuration < 300) return 30;
    return Math.max(10, remainingTime);
  }, [currentDuration, remainingTime]);

  // 轮询续写任务状态
  useEffect(() => {
    if (!polling || !continuationTaskId) return;

    const poll = async () => {
      try {
        const res = await fetch(`/api/v1/ai/task/${continuationTaskId}`, {
          headers: { 'X-User-ID': userId },
        });
        if (res.ok) {
          const data = await res.json();
          setContinuationStatus(data);
          
          if (data.status === 'completed' && data.result?.audio_url) {
            setPolling(false);
            // 续写完成，可以在这里触发回调通知父组件更新音频
            // 父组件会通过轮询原任务或其他方式获取新音频
          } else if (data.status === 'failed') {
            setPolling(false);
            setError(data.error || '续写失败');
            setLoading(false);
          }
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    };

    const interval = setInterval(poll, 2000);
    poll(); // 立即执行一次
    return () => clearInterval(interval);
  }, [polling, continuationTaskId, userId]);

  const handleContinue = async () => {
    if (!taskId || !canContinue) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const request: ContinueRequest = {
        source_task_id: taskId,
        mode,
        style: mode === 'new_style' ? style : undefined,
        duration: duration === 'auto' ? undefined : Number(duration),
        prompt,
        lyrics,
      };
      
      await onContinue(request);
      
      // 续写任务已提交，开始轮询
      // 注意：onContinue 应该返回新的任务 ID
      // 这里简化处理，实际需要从 onContinue 返回值获取
    } catch (e: any) {
      setError(e.message || '续写请求失败');
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 背景遮罩 */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* 面板 */}
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] shadow-2xl animate-slide-up">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-display font-semibold">🎵 {t('continue.songContinue') || '歌曲续写'}</h2>
          <button
            onClick={onClose}
            disabled={loading || polling}
            className="p-2 rounded-lg hover:bg-[var(--bg-elevated)] text-[var(--text-secondary)] transition disabled:opacity-40"
          >
            ✕
          </button>
        </div>

        {/* 内容 */}
        <div className="p-4 space-y-4">
          {/* 当前歌曲信息 */}
          <div className="rounded-xl bg-[var(--bg-elevated)] p-3 border border-[var(--border)]">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">{t('continue.currentDuration') || '当前时长'}</span>
              <span className="font-mono font-semibold">
                {Math.floor(currentDuration / 60)}:{String(Math.floor(currentDuration % 60)).padStart(2, '0')}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-[var(--text-secondary)]">{t('continue.remainingTime') || '剩余可续写'}</span>
              <span className="font-mono font-semibold text-[var(--accent-gradient-start)]">
                {Math.floor(remainingTime / 60)}:{String(Math.floor(remainingTime % 60)).padStart(2, '0')}
                {' '}
                <span className="text-xs text-[var(--text-muted)]">({remainingTime}s)</span>
              </span>
            </div>
            <div className="h-2 bg-[var(--bg-card)] rounded-full overflow-hidden mt-2">
              <div 
                className="h-full bg-gradient-to-r from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] transition-all duration-300"
                style={{ width: `${(currentDuration / maxDuration) * 100}%` }}
              />
            </div>
            {!canContinue && (
              <p className="text-xs text-[var(--text-muted)] mt-2">
                {remainingTime < 10 
                  ? (t('continue.maxDurationReached') || '已达到最大时长 5:30，无法继续')
                  : (t('continue.noAudio') || '请先生成歌曲')}
              </p>
            )}
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-red-400 text-sm flex items-center gap-2">
              ⚠️ {error}
            </div>
          )}

          {/* 续写模式选择 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">
              {t('continue.mode') || '续写模式'}
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {MODE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setMode(opt.value as any)}
                  disabled={loading || polling}
                  className={`relative p-3 rounded-lg border-2 text-sm text-left transition ${
                    mode === opt.value
                      ? 'border-[var(--accent-gradient-start)] bg-[var(--accent-gradient-start)]/10'
                      : 'border-[var(--border)] hover:border-[var(--accent-gradient-start)]/50'
                  } disabled:opacity-40`}
                >
                  <div className="font-medium">{t(opt.label)}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">{t(opt.description)}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 风格选择（new_style 模式时显示） */}
          {(mode === 'new_style') && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--text-secondary)]">
                {t('continue.newStyle') || '新风格'}
              </label>
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                disabled={loading || polling}
                className="w-full rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm focus:outline-none focus:border-[var(--accent-gradient-start)]"
              >
                {STYLE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{t(s.label)}</option>
                ))}
              </select>
            </div>
          )}

          {/* 时长选择 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">
              {t('continue.duration') || '续写时长'}
            </label>
            <div className="flex flex-wrap gap-2">
              {DURATION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDuration(opt.value)}
                  disabled={loading || polling || (typeof opt.value === 'number' && opt.value > remainingTime)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition ${
                    duration === opt.value
                      ? 'bg-[var(--accent-gradient-start)] text-white border-[var(--accent-gradient-start)]'
                      : 'bg-[var(--bg-elevated)] border-[var(--border)] hover:border-[var(--accent-gradient-start)]/50'
                  } ${typeof opt.value === 'number' && opt.value > remainingTime ? 'opacity-40 cursor-not-allowed' : ''}`}
                >
                  {t(opt.label)}
                </button>
              ))}
            </div>
            {duration === 'auto' && (
              <p className="text-xs text-[var(--text-muted)]">
                {t('continue.aiWillDecide') || `AI 将根据歌曲结构自动决定（建议约 ${suggestedDuration()} 秒）`}
              </p>
            )}
          </div>

          {/* 高级选项 */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm text-[var(--accent-gradient-start)] hover:underline flex items-center gap-1"
          >
            {showAdvanced ? '▼' : '▶'} {t('continue.advancedOptions') || '高级选项'}
          </button>

          {showAdvanced && (
            <div className="space-y-3 border-t border-[var(--border)] pt-4 animate-fade-in">
              <div>
                <label className="text-sm font-medium text-[var(--text-secondary)] block mb-1">
                  {t('continue.additionalPrompt') || '额外提示词'}
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder={t('continue.promptPlaceholder') || '例如：增加弦乐编排，情感更加饱满...'}
                  className="w-full h-20 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
                />
              </div>
              
              <div>
                <label className="text-sm font-medium text-[var(--text-secondary)] block mb-1">
                  {t('continue.customLyrics') || '自定义续写歌词（可选）'}
                </label>
                <textarea
                  value={lyrics}
                  onChange={(e) => setLyrics(e.target.value)}
                  placeholder={t('continue.lyricsPlaceholder') || '[Bridge]\n[Chorus]\n[Outro]'}
                  className="w-full h-24 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)] font-mono"
                />
              </div>
            </div>
          )}

          {/* 进度显示（续写进行中） */}
          {polling && continuationStatus && (
            <div className="space-y-2 border-t border-[var(--border)] pt-4 animate-fade-in">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{continuationStatus.progress.message}</span>
                <span className="text-[var(--text-muted)]">{Math.round(continuationStatus.progress.percent)}%</span>
              </div>
              <div className="h-2 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] transition-all duration-300"
                  style={{ width: `${continuationStatus.progress.percent}%` }}
                />
              </div>
              {continuationStatus.progress.segment_name && (
                <p className="text-xs text-[var(--text-muted)]">
                  {t('continue.generatingSegment') || '正在生成'}: {continuationStatus.progress.segment_name}
                  ({continuationStatus.progress.current_segment}/{continuationStatus.progress.total_segments})
                </p>
              )}
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex gap-3 pt-2 border-t border-[var(--border)]">
            <button
              onClick={onClose}
              disabled={loading || polling}
              className="flex-1 btn-secondary disabled:opacity-40"
            >
              {t('common.cancel') || '取消'}
            </button>
            <button
              onClick={handleContinue}
              disabled={loading || polling || !canContinue}
              className="flex-1 btn-primary disabled:opacity-40 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                  {t('continue.submitting') || '提交中...'}
                </>
              ) : polling ? (
                <>
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                  {t('continue.generating') || '生成中...'}
                </>
              ) : (
                t('continue.startContinue') || '开始续写'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}