"""分享链路的**服务端渲染页** —— og:title / og:description / og:image 的唯一来源。

为什么必须有这个页面（别删）
---------------------------
`/share/<token>` 正常访问时由 nginx 交给 React SPA，而 SPA 是**静态 index.html**：
所有 meta 都是站点级固定值、且原本连 og:image 都没有。微信 / X / Facebook / WhatsApp /
Telegram / Discord 的链接卡片，是平台**爬虫抓 HTML、不执行 JS** 生成的 —— 它们抓到的
就是那份静态 index.html。结果是：每条分享链接的卡片长得一模一样。

链接卡片是分享飞轮的**入口**，卡片不给力整个飞轮就不转。所以 nginx 按 UA 把爬虫分流
到这里（见 `/etc/nginx/sites-available/melovar-https` 的 `map $http_user_agent
$melovar_crawler` + `error_page 418 = @share_og`）。

本页返回：
  - og:title        真实歌名（用户可控字符串，**一律 html.escape**）
  - og:description  含时长；按 Accept-Language 出中文/英文
  - og:image        服务端生成的品牌封面（见 services/share_card.py），公开匿名可 GET
  - twitter:card    summary_large_image（X 单独用 twitter:* 而非 og:*）
  - 给人类的 JS 跳转 —— 爬虫不执行 JS，所以不影响它们读 meta

安全边界（与 share.py 同口径）：
  - 不返回任何 PII；令牌无效/任务不存在时**不报错**，直接降级为通用品牌卡片 ——
    对爬虫报错会让卡片整个消失，而降级不会泄露"该任务是否存在"。
  - SHARE_LINK_SECRET 未配置时同样降级（不在公网页面暴露配置状态）。
"""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.share import parse_token, share_configured
from app.services import task_store

logger = logging.getLogger(__name__)

# 独立前缀：/share/{token}（**不带 /api/v1**）—— 与 SPA 的路由同路径，
# 由 nginx 按 UA 分流，人走 SPA、爬虫走这里。
router = APIRouter(tags=["share-page"])

BRAND = "Melovar"

# og:type 用 website 而非 music.song —— Facebook 对 music.song 要求伴随
# music:duration / music:album / music:musician，缺项会导致卡片直接不渲染。
OG_TYPE = "website"

_DESC_ZH = "AI 作曲 + AI 演唱，一句话生成一首完整的歌。"
_DESC_EN = "AI-composed, AI-sung. One sentence in, a full song out."

_META_DESC = "一句话生成你的专属 AI 音乐 · Melovar"

# 通用卡片（令牌无效/未配置时降级用）
_GENERIC_TITLE = "Melovar — 一键生成你的专属 AI 音乐"
_GENERIC_DESC_ZH = "输入一句话，生成一首完整的歌。AI 作曲 + AI 演唱。"
_GENERIC_DESC_EN = "Type one sentence, get a full song. AI composed and sung."


def _site_base() -> str:
    """站点对外的规范基址（og:url / og:image 必须是绝对 URL）。"""
    return (os.getenv("PUBLIC_SITE_BASE") or "https://melovar.com").rstrip("/")


def _cover_url(variant: str = "og") -> str:
    """og:image 指向公开的品牌封面端点（services/share_card.py 渲染、带长缓存）。"""
    return f"{_site_base()}/api/v1/share/cover.png?variant={variant}"


def _wants_zh(request: Request) -> bool:
    """按 Accept-Language 决定描述语种；爬虫不送该头时回落英文。"""
    al = (request.headers.get("accept-language") or "").lower()
    return al.startswith("zh") or ",zh" in al or "zh-cn" in al or "zh-hans" in al


def _fmt_duration(seconds: object) -> str:
    """秒 → m:ss；无法解析返回空串（宁可少一段文案，不显示 0:00）。"""
    try:
        total = int(float(seconds))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    return f"{total // 60}:{total % 60:02d}"


def _esc(value: str) -> str:
    """所有进入 HTML 的用户可控内容都必须过这里（歌名是用户输入）。"""
    return html.escape(value or "", quote=True)


def _task_title(token: str) -> Optional[str]:
    """解出歌名；令牌无效 / 未配置 / 任务不存在一律返回 None（降级，不抛错）。"""
    if not share_configured():
        logger.warning("share_page: SHARE_LINK_SECRET 未配置，分享卡片降级为通用卡片")
        return None
    task_id = parse_token(token)
    if not task_id:
        return None
    task = task_store.get(task_id)
    if not task:
        return None
    if task.get("state") not in ("completed", "completed_with_stems_failed"):
        return None
    return (task.get("title") or "").strip() or None


def _render(request: Request, token: str) -> str:
    zh = _wants_zh(request)
    title = _task_title(token)
    duration = ""

    if title:
        # 拿一次时长只为文案；拿不到就算了
        task_id = parse_token(token)
        task = task_store.get(task_id) if task_id else None
        duration = _fmt_duration((task or {}).get("duration"))

        desc = _DESC_ZH if zh else _DESC_EN
        if duration:
            desc = f"{duration} · {desc}"
    else:
        title = _GENERIC_TITLE
        desc = _GENERIC_DESC_ZH if zh else _GENERIC_DESC_EN

    canonical = f"{_site_base()}/share/{_esc(token)}"
    cover = _cover_url("og")
    lang = "zh-CN" if zh else "en"

    # 人类兜底：爬虫不执行 JS 因而读到的仍是上面的 meta；真人被送回 SPA。
    # （把 host 写死在 canonical，避免直连后端 IP 时跳到错误来源。）
    redirect_js = json.dumps(canonical)

    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(_META_DESC)}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        "\n"
        "<!-- Open Graph -->\n"
        f'<meta property="og:site_name" content="{BRAND}">\n'
        f'<meta property="og:type" content="{OG_TYPE}">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:title" content="{_esc(title)}">\n'
        f'<meta property="og:description" content="{_esc(desc)}">\n'
        f'<meta property="og:image" content="{cover}">\n'
        f'<meta property="og:image:secure_url" content="{cover}">\n'
        '<meta property="og:image:type" content="image/png">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        f'<meta property="og:image:alt" content="{BRAND} — AI generated music">\n'
        f'<meta property="og:locale" content="{"zh_CN" if zh else "en_US"}">\n'
        "\n"
        "<!-- Twitter / X -->\n"
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:title" content="{_esc(title)}">\n'
        f'<meta name="twitter:description" content="{_esc(desc)}">\n'
        f'<meta name="twitter:image" content="{cover}">\n'
        "\n"
        "<style>"
        "html,body{margin:0;height:100%;background:#0d0d0f;color:#fff;"
        "font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif}"
        ".w{height:100%;display:flex;align-items:center;justify-content:center;text-align:center}"
        "a{color:#ff6a10;text-decoration:none;font-weight:600}"
        "p{opacity:.65;font-size:14px}"
        "</style>\n"
        "</head>\n<body>\n"
        '<div class="w"><div>\n'
        f"<h1>{_esc(title)}</h1>\n"
        f"<p>{_esc(desc)}</p>\n"
        f'<p><a href="{canonical}">在 Melovar 播放 →</a></p>\n'
        "</div></div>\n"
        f"<script>location.replace({redirect_js});</script>\n"
        "</body>\n</html>\n"
    )


@router.get("/share/{token}", response_class=HTMLResponse)
async def share_og_page(token: str, request: Request) -> HTMLResponse:
    """分享链接的服务端渲染页（供爬虫生成链接卡片；真人由 nginx 直接送 SPA）。"""
    body = _render(request, token)
    return HTMLResponse(
        content=body,
        # 短缓存：歌名发布后即不变，但令牌错误时需要尽快恢复
        headers={"Cache-Control": "public, max-age=300"},
    )
