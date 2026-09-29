/**
 * SharePage —— 公开分享落地页（PLG 病毒飞轮的承接点）。
 *
 * 无需登录：凭后端签发的 HMAC 令牌读取作品（GET /api/v1/share/{token}）。
 * 页面目标（K 因子的来源）：让人「听到歌 → 好奇这是 AI 做的 → 去创作/注册」。
 *
 * 产品约束：当前不做视频输出，所以分享物料是**静态封面卡**（canvas 现绘 PNG），
 * 而不是歌词卡视频；用户若要发短视频，自行下载封面卡 + 音频去配。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, apiFetch } from '../api/http';

interface SharedWork {
  task_id: string;
  title: string;
  duration: number | null;
  audio_url: string;
  expires_in: number;
  brand: string;
}

const W = 1080;
const H = 1080;

/** 在 canvas 上绘制静态分享封面卡（品牌渐变 + 标题 + AI 标记）。 */
function drawCover(canvas: HTMLCanvasElement, title: string, brand: string) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 背景渐变（与站点主色一致）
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, '#ff6a10');
  g.addColorStop(1, '#ee0979');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  // 暗色蒙层，提升文字可读性
  ctx.fillStyle = 'rgba(10,10,10,0.55)';
  ctx.fillRect(0, 0, W, H);

  // 品牌名
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 64px Inter, system-ui, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(brand, 80, 130);

  // AI 标记
  ctx.font = '600 34px Inter, system-ui, sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.fillText('✦ AI Generated Music', 80, 190);

  // 标题（自动换行，最多 3 行）
  const text = (title || 'Untitled').trim();
  ctx.font = 'bold 84px Inter, system-ui, sans-serif';
  ctx.fillStyle = '#ffffff';
  const maxWidth = W - 160;
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && cur) {
      lines.push(cur);
      cur = w;
      if (lines.length === 3) break;
    } else {
      cur = test;
    }
  }
  if (cur && lines.length < 3) lines.push(cur);
  lines.forEach((ln, i) => {
    ctx.fillText(ln, 80, 420 + i * 110);
  });

  // 底部引导：让人知道这是 AI 做的、可以自己做
  ctx.font = '600 40px Inter, system-ui, sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.85)';
  ctx.fillText('Made with AI · Create your own →', 80, H - 110);

  // 简易波形装饰
  ctx.strokeStyle = 'rgba(255,255,255,0.5)';
  ctx.lineWidth = 6;
  ctx.beginPath();
  for (let x = 80; x < W - 80; x += 12) {
    const amp = 40 * Math.abs(Math.sin((x - 80) / 90));
    ctx.moveTo(x, H - 240 - amp);
    ctx.lineTo(x, H - 240 + amp);
  }
  ctx.stroke();
}

export function SharePage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [work, setWork] = useState<SharedWork | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await apiFetch<SharedWork>(
          api.url(`/api/v1/share/${encodeURIComponent(token || '')}`)
        );
        if (alive) setWork(data);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  // 作品加载后绘制封面卡
  useEffect(() => {
    if (!work || !canvasRef.current) return;
    drawCover(canvasRef.current, work.title, work.brand || 'Melovar');
  }, [work]);

  const downloadCover = useCallback(() => {
    const c = canvasRef.current;
    if (!c) return;
    const a = document.createElement('a');
    a.href = c.toDataURL('image/png');
    a.download = `${(work?.title || 'melovar').slice(0, 40)}-cover.png`;
    a.click();
  }, [work]);

  const shareLink = useCallback(async () => {
    const url = window.location.href;
    const title = work?.title || 'Melovar';
    try {
      if (navigator.share) {
        await navigator.share({ title, text: `${title} — AI 生成`, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 用户取消分享或剪贴板不可用：静默忽略
    }
  }, [work]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] text-[#888]">
        Loading...
      </div>
    );
  }

  if (error || !work) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-[#0a0a0a] text-[#e0e0e0] px-6 text-center">
        <p className="text-lg">这个分享链接无效或已失效</p>
        <button
          onClick={() => navigate('/create')}
          className="px-5 py-2.5 rounded-xl bg-white text-[#0a0a0a] font-medium"
        >
          去做一首自己的歌
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] px-4 py-8">
      <div className="max-w-3xl mx-auto flex flex-col gap-6">
        {/* 封面卡（静态图，替代歌词卡视频） */}
        <canvas
          ref={canvasRef}
          width={W}
          height={H}
          className="w-full rounded-2xl border border-[#262626]"
        />

        {/* 播放器 */}
        <audio controls src={work.audio_url} className="w-full" />

        <div className="flex flex-wrap gap-3">
          <button
            onClick={shareLink}
            className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium"
          >
            {copied ? '链接已复制' : '分享'}
          </button>
          <button
            onClick={downloadCover}
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            下载封面卡
          </button>
          <a
            href={work.audio_url}
            download
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            下载音频
          </a>
        </div>

        {/* 飞轮钩子：引导去创作 */}
        <div className="rounded-2xl border border-[#262626] bg-[#121212] p-5 flex flex-col gap-3">
          <p className="text-sm text-[#b0b0b0]">
            这首歌由 AI 生成。输入一句话，你也能做出自己的歌。
          </p>
          <button
            onClick={() => navigate('/create')}
            className="self-start px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-semibold"
          >
            免费做一首同款 →
          </button>
        </div>
      </div>
    </div>
  );
}

export default SharePage;
