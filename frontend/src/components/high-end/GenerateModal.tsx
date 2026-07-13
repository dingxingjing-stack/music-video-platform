import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '../../i18n';

interface GenerateModalProps {
  isOpen: boolean;
  progress: number;
  status: string;
  message: string;
  elapsedSeconds: number;
  previewUrl?: string;
  onCancel: () => void;
  onRegenerate: () => void;
  onClose: () => void;
}

export function GenerateModal({
  isOpen,
  progress,
  status,
  message,
  elapsedSeconds,
  previewUrl,
  onCancel,
  onRegenerate,
  onClose,
}: GenerateModalProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visualizerBars, setVisualizerBars] = useState<number[]>(
    Array.from({ length: 32 }, () => Math.random() * 0.5 + 0.2)
  );

  // 模拟音频可视化条跳动
  useEffect(() => {
    if (!isOpen || status !== 'running') return;
    const interval = setInterval(() => {
      setVisualizerBars(
        Array.from({ length: 32 }, () => Math.random() * 0.7 + 0.1)
      );
    }, 150);
    return () => clearInterval(interval);
  }, [isOpen, status]);

  // Canvas 可视化绘制
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !isOpen) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const barWidth = (w / visualizerBars.length) * 0.8;
      const gap = (w / visualizerBars.length) * 0.2;

      visualizerBars.forEach((val, i) => {
        const barHeight = val * h;
        const x = i * (barWidth + gap) + gap / 2;
        const gradient = ctx.createLinearGradient(x, h, x, h - barHeight);
        gradient.addColorStop(0, 'rgba(99, 102, 241, 0.8)');
        gradient.addColorStop(0.5, 'rgba(168, 85, 247, 0.6)');
        gradient.addColorStop(1, 'rgba(236, 72, 153, 0.4)');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, h - barHeight, barWidth, barHeight, [4]);
        ctx.fill();
      });

      requestAnimationFrame(draw);
    };
    const rafId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafId);
  }, [isOpen, visualizerBars]);

  if (!isOpen) return null;

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center"
      >
        {/* 银河系渐变背景 */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-indigo-950/90 to-purple-950/90 backdrop-blur-xl" />

        {/* 主模态卡片 */}
        <motion.div
          initial={{ scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="relative z-10 w-full max-w-lg mx-4 bg-black/50 backdrop-blur-2xl rounded-2xl border border-[#2a2a38] shadow-2xl shadow-indigo-500/20 p-6"
        >
          {/* 标题 */}
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-[#e0e0e0]">
              {t('ui.generate')}
            </h2>
            <span className="text-sm text-[#b0b0b0]">
              {formatTime(elapsedSeconds)}
            </span>
          </div>

          {/* 进度条 - 发光效果 */}
          <div className="mb-6">
            <div className="flex justify-between text-xs text-[#b0b0b0] mb-1.5">
              <span>{message}</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="relative h-3 bg-[#262626]/60 rounded-full overflow-hidden">
              {/* 发光进度 */}
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
                className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500"
              />
              {/* 光晕 */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: progress > 0 ? 0.6 : 0 }}
                className="absolute inset-0 rounded-full bg-gradient-to-r from-indigo-400/30 via-purple-400/30 to-pink-400/30 blur-md"
                style={{ width: `${Math.min(progress + 10, 100)}%` }}
              />
            </div>
          </div>

          {/* 3D 音频可视化 */}
          <div className="mb-6">
            <p className="text-xs text-[#777777] mb-2 uppercase tracking-wider">
              {t('ui.waveformVisualization') || 'Waveform'}
            </p>
            <canvas
              ref={canvasRef}
              width={400}
              height={80}
              className="w-full h-20 rounded-xl bg-black/40 border border-white/5"
            />
          </div>

          {/* 预览播放器 */}
          {previewUrl && (
            <div className="mb-6 p-3 rounded-xl bg-white/5 border border-white/5">
              <p className="text-xs text-[#b0b0b0] mb-2">{t('common.preview') || 'Preview'}</p>
              <audio controls src={previewUrl} className="w-full h-8" />
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex gap-3">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => { onCancel(); onClose(); }}
              className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-[#2a2a38] text-[#e0e0e0] text-sm font-medium hover:bg-white/10 transition-colors"
            >
              {t('common.cancel')}
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onRegenerate}
              disabled={status === 'running'}
              className="flex-1 px-4 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-[#e0e0e0] text-sm font-medium shadow-lg shadow-indigo-500/25 hover:from-indigo-500 hover:to-purple-500 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {status === 'completed' ? t('ui.generate') : t('ui.generate')}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}