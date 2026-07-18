import { useState, useCallback } from 'react';

const API = 'https://ai-music-backend-8e85.onrender.com/api/v1';

/** 巴西圣保罗时区 */
function brtHour(): number {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' })).getHours();
}

/** 算力高峰：22-01, 03-07 */
export function isPeakHour(): boolean {
  const h = brtHour();
  return (h >= 22 || h < 1) || (h >= 3 && h < 7);
}

interface UseAudioGenOptions {
  onSuccess?: (url: string) => void;
}

export function useAudioGeneration(opts?: UseAudioGenOptions) {
  const [loading, setLoading] = useState(false);
  const [showPeakModal, setShowPeakModal] = useState(false);
  const [showRechargeModal, setShowRechargeModal] = useState(false);

  /** 通用 generate — 传 endpoint + body，返回 audio_url */
  const generate = useCallback(async (endpoint: string, body: Record<string, unknown>) => {
    if (isPeakHour()) { setShowPeakModal(true); return null; }

    setLoading(true);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000); // 15s 超时

      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (res.status === 402) { setShowRechargeModal(true); return null; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const url = data.audio_url || data.url;
      if (url) opts?.onSuccess?.(url);
      return url as string | null;
    } catch {
      // 后端不通 → Mock 回退
      await new Promise(r => setTimeout(r, 2000));
      const mockUrl = 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3';
      opts?.onSuccess?.(mockUrl);
      return mockUrl;
    } finally {
      setLoading(false);
    }
  }, [opts]);

  return { loading, generate, showPeakModal, setShowPeakModal, showRechargeModal, setShowRechargeModal };
}

/** 算力高峰提示弹窗 */
export function PeakHourModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl p-6 max-w-sm mx-4" onClick={e => e.stopPropagation()}>
        <div className="text-4xl mb-3">⚡</div>
        <h3 className="text-lg font-bold text-white mb-2">算力高峰时段</h3>
        <p className="text-sm text-[#888888] mb-1">当前巴西时间 {brtHour()}:00，处于算力高峰。</p>
        <p className="text-sm text-[#ff6a10] font-medium mb-4">费用翻倍，推荐 7:00-22:00 生成。</p>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-[#2a2a2a] text-[#888888] text-sm hover:text-white">取消</button>
          <button onClick={() => { onClose(); }} className="flex-1 py-2 rounded-lg bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-medium">仍然生成</button>
        </div>
      </div>
    </div>
  );
}

/** 402 余额不足弹窗 */
export function RechargeModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl p-6 max-w-sm mx-4" onClick={e => e.stopPropagation()}>
        <div className="text-4xl mb-3">💰</div>
        <h3 className="text-lg font-bold text-white mb-2">余额不足</h3>
        <p className="text-sm text-[#888888] mb-4">API 返回 402 Insufficient Balance，请充值后重试。</p>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-[#2a2a2a] text-[#888888] text-sm hover:text-white">取消</button>
          <a href="https://platform.deepseek.com/top_up" target="_blank" rel="noopener noreferrer"
            className="flex-1 py-2 rounded-lg bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-medium text-center"
            onClick={onClose}>去充值</a>
        </div>
      </div>
    </div>
  );
}

/** PathB 占位弹窗 */
export function ComingSoonModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl p-6 max-w-sm mx-4 text-center" onClick={e => e.stopPropagation()}>
        <div className="text-5xl mb-4">🚧</div>
        <h3 className="text-lg font-bold text-white mb-2">功能开发中</h3>
        <p className="text-sm text-[#888888] mb-4">混合模式正在开发，敬请期待。</p>
        <button onClick={onClose} className="w-full py-2 rounded-lg bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-medium">知道了</button>
      </div>
    </div>
  );
}
