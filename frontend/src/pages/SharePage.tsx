/**
 * SharePage —— 公开分享落地页（PLG 病毒飞轮的承接点）。
 *
 * 无需登录：凭后端签发的 HMAC 令牌读取作品（GET /api/v1/share/{token}）。
 * 页面目标（K 因子的来源）：让人「听到歌 → 好奇这是 AI 做的 → 去创作/注册」。
 *
 * 关于链接卡片（重要，别只改这里）
 * --------------------------------
 * 本页是 React SPA，而 SPA 是**静态 index.html** —— 微信/X/Facebook/WhatsApp/
 * Telegram 的链接卡片由平台爬虫抓 HTML 生成、**不执行 JS**，所以它们看到的不是
 * 本页画的封面，而是服务端渲染页返回的 og:title/og:image：
 *   · 后端 og 页：backend/app/routers/share_page.py（GET /share/{token}）
 *   · 后端封面图：backend/app/services/share_card.py（GET /api/v1/share/cover.png）
 *   · nginx 按 UA 把爬虫分流到 og 页：docs/nginx/melovar-https.conf
 * 改了本页的视觉，记得同步 share_card.py 的品牌色，否则两张图会不一致。
 *
 * 产品约束：当前不做视频输出，所以分享物料是**静态封面卡**（canvas 现绘 PNG），
 * 而不是歌词卡视频。canvas 由浏览器渲染 ⇒ 有全语言字体，歌名可以放心画进去
 * （服务端那张 og:image 就不行 —— 镜像里没有 CJK 字体，见 share_card.py）。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { api, apiFetch } from '../api/http';
import { useTranslation } from '../i18n/useTranslation';

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

type PlatformId =
  | 'wechat'
  | 'weibo'
  | 'qq'
  | 'x'
  | 'facebook'
  | 'whatsapp'
  | 'telegram'
  | 'reddit'
  | 'linkedin'
  | 'pinterest';

/** 平台清单：tint 用品牌色做视觉识别（不放品牌 logo —— 直接用别人商标有合规风险）。 */
const PLATFORM_TINT: Record<PlatformId, string> = {
  wechat: '#07c160',
  weibo: '#e6162d',
  qq: '#12b7f5',
  x: '#1d9bf0',
  facebook: '#1877f2',
  whatsapp: '#25d366',
  telegram: '#229ed9',
  reddit: '#ff4500',
  linkedin: '#0a66c2',
  pinterest: '#e60023',
};

// zh 用户先看到国内平台，其余语种先看到国际平台（用户选择「两者都给、按语言排序」）
const CN_FIRST: PlatformId[] = ['wechat', 'weibo', 'qq'];
const INTL_FIRST: PlatformId[] = [
  'x',
  'whatsapp',
  'telegram',
  'facebook',
  'reddit',
  'linkedin',
  'pinterest',
];

/** 构造各平台的原生分享 URL（微信没有 web 分享协议 → 走二维码，见 onShare）。 */
function platformHref(id: PlatformId, url: string, title: string, cover: string): string {
  const u = encodeURIComponent(url);
  const t = encodeURIComponent(title);
  switch (id) {
    case 'weibo':
      return `https://service.weibo.com/share/share.php?url=${u}&title=${t}`;
    case 'qq':
      return `https://connect.qq.com/widget/shareqq/index.html?url=${u}&title=${t}`;
    case 'x':
      return `https://twitter.com/intent/tweet?url=${u}&text=${t}`;
    case 'facebook':
      return `https://www.facebook.com/sharer/sharer.php?u=${u}`;
    case 'whatsapp': {
      // wa.me 只吃 text，把标题和链接拼一起
      return `https://wa.me/?text=${encodeURIComponent(`${title} ${url}`)}`;
    }
    case 'telegram':
      return `https://t.me/share/url?url=${u}&text=${t}`;
    case 'reddit':
      return `https://www.reddit.com/submit?url=${u}&title=${t}`;
    case 'linkedin':
      return `https://www.linkedin.com/sharing/share-offsite/?url=${u}`;
    case 'pinterest':
      return `https://pinterest.com/pin/create/button/?url=${u}&media=${encodeURIComponent(cover)}&description=${t}`;
    default:
      return url;
  }
}

/** 在 canvas 上绘制静态分享封面卡（品牌渐变 + 标题 + AI 标记）。 */
function drawCover(canvas: HTMLCanvasElement, title: string, brand: string) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 背景渐变（与站点主色、以及后端 share_card.py 的 C_FROM/C_TO 保持一致）
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
  // ⚠️ 标题**可能为空**：系统里目前没有"歌名"这个概念 —— ai_tasks 无 title 列、
  //    生成流程不接收标题，MyWorks 也是用 task_id 前 8 位当名字。所以空标题是
  //    正常态，不能画 "Untitled"（那是把数据缺口当成歌曲名展示给陌生人）。
  //    为空时整段跳过，封面只留品牌 + AI 标记 + 波形，视觉依然完整。
  const text = (title || '').trim();
  if (text) {
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
  }

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
  const { t, locale } = useTranslation();

  const [work, setWork] = useState<SharedWork | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string>('');
  const [showQr, setShowQr] = useState(false);

  // 分享用的规范链接：去掉 query/hash，避免把 SPA 内部的临时参数传出去
  const shareUrl = useMemo(
    () =>
      typeof window === 'undefined'
        ? ''
        : `${window.location.origin}/share/${encodeURIComponent(token || '')}`,
    [token]
  );
  const coverUrl = useMemo(
    () =>
      typeof window === 'undefined'
        ? ''
        : `${window.location.origin}/api/v1/share/cover.png?variant=og`,
    []
  );

  const platforms = useMemo<PlatformId[]>(
    () => (locale === 'zh' ? [...CN_FIRST, ...INTL_FIRST] : [...INTL_FIRST, ...CN_FIRST]),
    [locale]
  );

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

  // ESC 关闭二维码弹层
  useEffect(() => {
    if (!showQr) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowQr(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showQr]);

  const flash = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2000);
  }, []);

  const copy = useCallback(
    async (value: string, okMsg: string) => {
      try {
        await navigator.clipboard.writeText(value);
        flash(okMsg);
        return true;
      } catch {
        // 剪贴板不可用（非 https / 权限被拒）：退回到 location.hash 方案交给用户手抄
        return false;
      }
    },
    [flash]
  );

  const downloadCover = useCallback(() => {
    const c = canvasRef.current;
    if (!c) return;
    const a = document.createElement('a');
    a.href = c.toDataURL('image/png');
    a.download = `${(work?.title || 'melovar').slice(0, 40)}-cover.png`;
    a.click();
  }, [work]);

  /** 封面卡转 File —— 用于 Web Share Level 2 把「图 + 链接」一起分享（适配发微博/小红书）。 */
  const coverFile = useCallback(async (): Promise<File | null> => {
    const c = canvasRef.current;
    if (!c) return null;
    const blob = await new Promise<Blob | null>((res) => c.toBlob((b) => res(b), 'image/png'));
    if (!blob) return null;
    return new File([blob], `${(work?.title || 'melovar').slice(0, 40)}-cover.png`, {
      type: 'image/png',
    });
  }, [work]);

  /** 系统分享（移动端最顺的一条路）：优先带封面图，退化到纯链接。 */
  const onSystemShare = useCallback(async () => {
    const title = work?.title || 'Melovar';
    const text = t('share.shareText', { title, url: shareUrl });
    try {
      const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
      const file = await coverFile();
      if (nav.share) {
        if (file) {
          const payload: ShareData = { title, text, files: [file] };
          if (nav.canShare?.(payload)) {
            await nav.share(payload);
            return;
          }
        }
        await nav.share({ title, text, url: shareUrl });
        return;
      }
    } catch {
      // 用户取消分享：静默
      return;
    }
    // 桌面浏览器普遍不支持 navigator.share → 复制链接兜底
    await copy(shareUrl, t('share.linkCopied'));
  }, [work, shareUrl, t, coverFile, copy]);

  /** 微信：没有 web 分享协议，只能给二维码让用户「扫一扫」，或复制链接去粘贴。 */
  const onWechat = useCallback(() => setShowQr(true), []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] text-[#888]">
        {t('share.loading')}
      </div>
    );
  }

  if (error || !work) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-[#0a0a0a] text-[#e0e0e0] px-6 text-center">
        <p className="text-lg">{t('share.notFound')}</p>
        <button
          onClick={() => navigate('/create')}
          className="px-5 py-2.5 rounded-xl bg-white text-[#0a0a0a] font-medium"
        >
          {t('share.goCreate')}
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

        {/* 主操作：系统分享优先（移动端可直接带封面图 + 链接） */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={onSystemShare}
            className="px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium"
          >
            {t('share.systemShare')}
          </button>
          <button
            onClick={() => copy(shareUrl, t('share.linkCopied'))}
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            {t('share.copyLink')}
          </button>
          <button
            onClick={() =>
              copy(t('share.shareText', { title: work.title || 'Melovar', url: shareUrl }), t('share.textCopied'))
            }
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            {t('share.copyText')}
          </button>
          <button
            onClick={downloadCover}
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            {t('share.downloadCover')}
          </button>
          <a
            href={work.audio_url}
            download
            className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
          >
            {t('share.downloadAudio')}
          </a>
        </div>

        {/* 平台直达 */}
        <div className="flex flex-col gap-3">
          <p className="text-sm text-[#888]">{t('share.shareTo')}</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {platforms.map((id) => {
              const label = t(`share.${id}`);
              if (id === 'wechat') {
                return (
                  <button
                    key={id}
                    onClick={onWechat}
                    className="flex items-center gap-2 px-3 py-2.5 rounded-xl border border-[#262626] bg-[#141414] hover:border-[#3a3a48] text-sm text-start"
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ background: PLATFORM_TINT[id] }}
                    />
                    {label}
                  </button>
                );
              }
              return (
                <a
                  key={id}
                  href={platformHref(id, shareUrl, work.title || 'Melovar', coverUrl)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2.5 rounded-xl border border-[#262626] bg-[#141414] hover:border-[#3a3a48] text-sm text-start"
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: PLATFORM_TINT[id] }}
                  />
                  {label}
                </a>
              );
            })}
          </div>
        </div>

        {/* 飞轮钩子：引导去创作 */}
        <div className="rounded-2xl border border-[#262626] bg-[#121212] p-5 flex flex-col gap-3">
          <p className="text-sm text-[#b0b0b0]">{t('share.hook')}</p>
          <button
            onClick={() => navigate('/create')}
            className="self-start px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-semibold"
          >
            {t('share.cta')} →
          </button>
        </div>
      </div>

      {/* 微信二维码弹层 */}
      {showQr && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center px-6"
          onClick={() => setShowQr(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-[#262626] bg-[#121212] p-6 flex flex-col items-center gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-base font-semibold">{t('share.scanQr')}</p>
            <div className="rounded-xl bg-white p-3">
              {shareUrl && <QRCodeSVG value={shareUrl} size={208} level="M" />}
            </div>
            <p className="text-xs text-[#888] text-center leading-relaxed">{t('share.wechatHint')}</p>
            <div className="flex gap-3 w-full">
              <button
                onClick={() => copy(shareUrl, t('share.linkCopied'))}
                className="flex-1 px-4 py-2 rounded-xl bg-gradient-to-r from-[#ff6a10] to-[#ee0979] text-white text-sm font-semibold"
              >
                {t('share.copyLink')}
              </button>
              <button
                onClick={() => setShowQr(false)}
                className="px-4 py-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-sm"
              >
                {t('share.close')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 轻提示（复制成功等） */}
      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl bg-white text-[#0a0a0a] text-sm font-medium shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}

export default SharePage;
