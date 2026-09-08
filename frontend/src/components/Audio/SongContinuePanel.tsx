import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '../../i18n/useTranslation';
import { authFetch } from '../../api/http';
import { WaveformEditor } from './WaveformEditor';

interface SongContinuePanelProps {
  /** 褰撳墠鎾斁鐨勯煶棰?URL */
  audioUrl: string | null;
  /** 褰撳墠浠诲姟 ID锛堢敤浜庣画鍐欙級 */
  taskId: string | null;
  /** 褰撳墠姝屾洸鏃堕暱锛堢锛?*/
  currentDuration: number;
  /** 鍥炶皟锛氳姹傜画鍐?*/
  onContinue: (request: ContinueRequest) => Promise<void>;
  /** 鍥炶皟锛氬彇娑堢画鍐欓潰鏉?*/
  onClose?: () => void;
  /** 鏄惁鏄剧ず闈㈡澘 */
  isOpen: boolean;
  /** 鐢ㄦ埛 ID锛堢敤浜?API 璋冪敤锛?*/
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

  // 璁＄畻寤鸿鐨勭画鍐欐椂闀?
  const suggestedDuration = useCallback(() => {
    if (currentDuration < 60) return 60;
    if (currentDuration < 120) return 60;
    if (currentDuration < 180) return 60;
    if (currentDuration < 240) return 45;
    if (currentDuration < 300) return 30;
    return Math.max(10, remainingTime);
  }, [currentDuration, remainingTime]);

  // 杞缁啓浠诲姟鐘舵€?
  useEffect(() => {
    if (!polling || !continuationTaskId) return;

    const poll = async () => {
      try {
        const data = await authFetch<any>(`/api/v1/ai/task/${continuationTaskId}`);
        setContinuationStatus(data);

        if (data.status === 'completed' && data.result?.audio_url) {
          setPolling(false);
          // 缁啓瀹屾垚锛屽彲浠ュ湪杩欓噷瑙﹀彂鍥炶皟閫氱煡鐖剁粍浠舵洿鏂伴煶棰?
          // 鐖剁粍浠朵細閫氳繃杞鍘熶换鍔℃垨鍏朵粬鏂瑰紡鑾峰彇鏂伴煶棰?
        } else if (data.status === 'failed') {
          setPolling(false);
          setError(data.error || t('continue.continueFailed'));
          setLoading(false);
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    };

    const interval = setInterval(poll, 2000);
    poll(); // 绔嬪嵆鎵ц涓€娆?
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

      // 缁啓浠诲姟宸叉彁浜わ紝寮€濮嬭疆璇?
      // 娉ㄦ剰锛歰nContinue 搴旇杩斿洖鏂扮殑浠诲姟 ID
      // 杩欓噷绠€鍖栧鐞嗭紝瀹為檯闇€瑕佷粠 onContinue 杩斿洖鍊艰幏鍙?
    } catch (e: any) {
      setError(e.message || t('continue.requestFailed'));
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 鑳屾櫙閬僵 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 闈㈡澘 */}
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] shadow-2xl animate-slide-up">
        {/* 澶撮儴 */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-display font-semibold">馃幍 {t('continue.songContinue') || '姝屾洸缁啓'}</h2>
          <button
            onClick={onClose}
            disabled={loading || polling}
            className="p-2 rounded-lg hover:bg-[var(--bg-elevated)] text-[var(--text-secondary)] transition disabled:opacity-40"
          >
            鉁?
          </button>
        </div>

        {/* 鍐呭 */}
        <div className="p-4 space-y-4">
          {/* 褰撳墠姝屾洸淇℃伅 */}
          <div className="rounded-xl bg-[var(--bg-elevated)] p-3 border border-[var(--border)]">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">{t('continue.currentDuration') || '褰撳墠鏃堕暱'}</span>
              <span className="font-mono font-semibold">
                {Math.floor(currentDuration / 60)}:{String(Math.floor(currentDuration % 60)).padStart(2, '0')}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-[var(--text-secondary)]">{t('continue.remainingTime') || '鍓╀綑鍙画鍐?}</span>
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
                  ? (t('continue.maxDurationReached') || '宸茶揪鍒版渶澶ф椂闀?5:30锛屾棤娉曠户缁?)
                  : (t('continue.noAudio') || '璇峰厛鐢熸垚姝屾洸')}
              </p>
            )}
          </div>

          {/* 閿欒鎻愮ず */}
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-red-400 text-sm flex items-center gap-2">
              鈿狅笍 {error}
            </div>
          )}

          {/* 缁啓妯″紡閫夋嫨 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">
              {t('continue.mode') || '缁啓妯″紡'}
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

          {/* 椋庢牸閫夋嫨锛坣ew_style 妯″紡鏃舵樉绀猴級 */}
          {(mode === 'new_style') && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--text-secondary)]">
                {t('continue.newStyle') || '鏂伴鏍?}
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

          {/* 鏃堕暱閫夋嫨 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">
              {t('continue.duration') || '缁啓鏃堕暱'}
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
                {t('continue.aiWillDecide') || `AI 灏嗘牴鎹瓕鏇茬粨鏋勮嚜鍔ㄥ喅瀹氾紙寤鸿绾?${suggestedDuration()} 绉掞級`}
              </p>
            )}
          </div>

          {/* 楂樼骇閫夐」 */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm text-[var(--accent-gradient-start)] hover:underline flex items-center gap-1"
          >
            {showAdvanced ? '鈻? : '鈻?} {t('continue.advancedOptions') || '楂樼骇閫夐」'}
          </button>

          {showAdvanced && (
            <div className="space-y-3 border-t border-[var(--border)] pt-4 animate-fade-in">
              <div>
                <label className="text-sm font-medium text-[var(--text-secondary)] block mb-1">
                  {t('continue.additionalPrompt') || '棰濆鎻愮ず璇?}
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder={t('continue.promptPlaceholder') || '渚嬪锛氬鍔犲鸡涔愮紪鎺掞紝鎯呮劅鏇村姞楗辨弧...'}
                  className="w-full h-20 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] p-3 text-sm resize-none focus:outline-none focus:border-[var(--accent-gradient-start)]"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-[var(--text-secondary)] block mb-1">
                  {t('continue.customLyrics') || '鑷畾涔夌画鍐欐瓕璇嶏紙鍙€夛級'}
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

          {/* 杩涘害鏄剧ず锛堢画鍐欒繘琛屼腑锛?*/}
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
                  {t('continue.generatingSegment') || '姝ｅ湪鐢熸垚'}: {continuationStatus.progress.segment_name}
                  ({continuationStatus.progress.current_segment}/{continuationStatus.progress.total_segments})
                </p>
              )}
            </div>
          )}

          {/* 鎿嶄綔鎸夐挳 */}
          <div className="flex gap-3 pt-2 border-t border-[var(--border)]">
            <button
              onClick={onClose}
              disabled={loading || polling}
              className="flex-1 btn-secondary disabled:opacity-40"
            >
              {t('common.cancel') || '鍙栨秷'}
            </button>
            <button
              onClick={handleContinue}
              disabled={loading || polling || !canContinue}
              className="flex-1 btn-primary disabled:opacity-40 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                  {t('continue.submitting') || '鎻愪氦涓?..'}
                </>
              ) : polling ? (
                <>
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                  {t('continue.generating') || '鐢熸垚涓?..'}
                </>
              ) : (
                t('continue.startContinue') || '寮€濮嬬画鍐?
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}