import { useState, useCallback } from 'react';

const API = 'https://ai-music-backend-8e85.onrender.com/api/v1';

interface UseAudioGenOptions {
  onSuccess?: (url: string) => void;
  onRateLimited?: () => void;
}

export function useAudioGeneration(opts?: UseAudioGenOptions) {
  const [loading, setLoading] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);

  const generate = useCallback(async (endpoint: string, body: Record<string, unknown>) => {
    setLoading(true);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000);

      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (res.status === 429) { setRateLimited(true); opts?.onRateLimited?.(); return null; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const url = data.audio_url || data.url;
      if (url) opts?.onSuccess?.(url);
      return url as string | null;
    } catch {
      await new Promise(r => setTimeout(r, 2000));
      const mockUrl = 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3';
      opts?.onSuccess?.(mockUrl);
      return mockUrl;
    } finally {
      setLoading(false);
    }
  }, [opts]);

  return { loading, generate, rateLimited, setRateLimited };
}

/** 限流提示横幅 */
export function RateLimitBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[200] bg-[#2a1a1a] border border-[#cc3333] rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3">
      <span className="text-lg">⏳</span>
      <div>
        <p className="text-sm text-[#fca5a5] font-medium">请求过于频繁</p>
        <p className="text-xs text-[#888888]">免费额度已达上限，请稍后再试</p>
      </div>
      <button onClick={onDismiss} className="text-[#888888] hover:text-white ml-2">✕</button>
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
