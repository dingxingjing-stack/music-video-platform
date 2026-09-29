"""分享封面图（服务端生成）—— og:image 的唯一来源。

为什么必须在服务端生成
----------------------
微信 / X / Facebook / WhatsApp / Telegram / Discord 的链接卡片，是平台**爬虫抓 HTML**
后生成的，而爬虫**不执行 JS**。所以前端 canvas 画的封面卡它们永远看不到。
og:image 必须是一个「公开、匿名可 GET 的图片 URL」—— 这就是本模块存在的理由。

为什么图里不画歌名（重要，别"优化"掉）
--------------------------------------
镜像基于 `python:3.11-slim`（Debian），**不含任何 TTF 字体文件**。Pillow 的
`ImageFont.load_default(size=)` 只覆盖**拉丁字形**，且不区分字重。歌名可能是
中文 / 日文 / 韩文 / 印地文 / 阿拉伯文 —— 画进图里会变成**豆腐块**，比不画更糟。

补充两点使这个取舍成立：
  1. 平台卡片**本身就会单独展示 `og:title` 文字**（微信是左图右文、X 是图上+图下、
     Facebook 是图下），图里再画一遍是重复信息；
  2. 需要"把歌名烧进图里"的场景（用户发抖音/小红书）走**浏览器 canvas** ——
     浏览器有全语言字体。见 `frontend/src/pages/SharePage.tsx`。

所以本图只画**恒定可渲染的品牌视觉**（全拉丁字形），歌名交给 og:title。

副作用（好的那种）：因为图里没有任何 per-song 数据，**所有歌曲共用同一张图**，
于是可以整块缓存字节、给长 Cache-Control，端点几乎零成本。
"""

from __future__ import annotations

import io
import math
from functools import lru_cache
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

BRAND = "MELOVAR"
TAGLINE = "AI GENERATED MUSIC"
SITE = "melovar.com"

# 与前端 SharePage 的 canvas 用同一组色（品牌渐变）
C_FROM = (255, 106, 16)   # #ff6a10
C_TO = (238, 9, 121)      # #ee0979

# og: 1200x630 是 X / Facebook / LinkedIn / Slack / Discord 的通用大图比例
# square: 1080x1080 给需要方图的场景（也便于未来复用）
_VARIANTS: dict[str, Tuple[int, int]] = {"og": (1200, 630), "square": (1080, 1080)}

DEFAULT_VARIANT = "og"


def _font(size: int) -> ImageFont.FreeTypeFont:
    """可缩放的默认字体（Aileron，仅拉丁字形）。

    只用它渲染品牌等**恒定拉丁**文案。不要用它渲染歌名 —— 见模块 docstring。
    """
    return ImageFont.load_default(size=max(8, int(size)))  # type: ignore[return-value]


def _gradient(w: int, h: int) -> Image.Image:
    """横向线性渐变（品牌色 → 品牌色）。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    span = max(1, w - 1)
    for x in range(w):
        t = x / span
        d.line(
            [(x, 0), (x, h)],
            fill=(
                round(C_FROM[0] + (C_TO[0] - C_FROM[0]) * t),
                round(C_FROM[1] + (C_TO[1] - C_FROM[1]) * t),
                round(C_FROM[2] + (C_TO[2] - C_FROM[2]) * t),
            ),
        )
    return img


def _centered(d: ImageDraw.ImageDraw, y: int, text: str, font, fill) -> None:
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    d.text(((d.im.size[0] - (right - left)) / 2 - left, y - top), text, font=font, fill=fill)


def _build(variant: str) -> bytes:
    w, h = _VARIANTS[variant]
    # 以短边为基准做等比缩放，使方图与横图的文字/元素视觉重量一致
    s = min(w, h) / 630.0
    margin = round(0.055 * min(w, h))

    img = _gradient(w, h).convert("RGBA")

    # 暗色蒙层：让白字在任何渐变位置都有足够对比度
    veil = Image.new("RGBA", (w, h), (10, 10, 10, 150))
    img = Image.alpha_composite(img, veil)

    # 叠加层（圆角/半透明元素都在这里画，最后一次性合成）
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # ---- 品牌字标 ----
    brand_font = _font(round(58 * s))
    d.text(
        (margin, margin),
        BRAND,
        font=brand_font,
        fill=(255, 255, 255, 255),
        # 默认字体无粗体，用描边模拟字重
        stroke_width=max(1, round(2 * s)),
        stroke_fill=(255, 255, 255, 255),
    )

    # ---- 副标 + AI 徽标 ----
    tag_font = _font(round(26 * s))
    tag_y = margin + round(78 * s)
    d.text((margin, tag_y), TAGLINE, font=tag_font, fill=(255, 255, 255, 235))

    badge = "100% AI"
    bw = d.textbbox((0, 0), badge, font=tag_font)[2]
    bx = margin + d.textbbox((0, 0), TAGLINE, font=tag_font)[2] + round(18 * s)
    d.rounded_rectangle(
        [bx, tag_y - round(6 * s), bx + bw + round(26 * s), tag_y + round(34 * s)],
        radius=round(10 * s),
        fill=(255, 255, 255, 40),
        outline=(255, 255, 255, 120),
        width=max(1, round(1.5 * s)),
    )
    d.text((bx + round(13 * s), tag_y), badge, font=tag_font, fill=(255, 255, 255, 255))

    # ---- 中央播放按钮（提升点击欲）----
    cx, cy = w / 2, h * 0.47
    r = round(74 * s)
    d.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(255, 255, 255, 235),
    )
    # 播放三角（略向右偏，视觉居中）
    tr = r * 0.46
    d.polygon(
        [
            (cx - tr * 0.62 + r * 0.10, cy - tr),
            (cx - tr * 0.62 + r * 0.10, cy + tr),
            (cx + tr * 0.92 + r * 0.10, cy),
        ],
        fill=(15, 15, 15, 255),
    )

    # ---- 波形装饰 ----
    bars = 46 if variant == "og" else 38
    bar_w = round(6 * s)
    gap = round(14 * s)
    total = bars * gap
    x0 = (w - total) / 2 + gap / 2
    wy = h - round(0.26 * h)
    for i in range(bars):
        # 确定性包络（不用随机，保证每次渲染一致、可缓存）
        env = abs(math.sin(i * 0.55)) * 0.65 + abs(math.sin(i * 0.17)) * 0.35
        half = round((0.10 + 0.90 * env) * 0.075 * h)
        x = x0 + i * gap
        d.rounded_rectangle(
            [x, wy - half, x + bar_w, wy + half],
            radius=bar_w / 2,
            fill=(255, 255, 255, 190),
        )

    # ---- 站点域名（卡片上的"去哪听"提示）----
    site_font = _font(round(28 * s))
    sw = d.textbbox((0, 0), SITE, font=site_font)[2]
    d.text(
        (w - margin - sw, h - margin - round(40 * s)),
        SITE,
        font=site_font,
        fill=(255, 255, 255, 220),
    )

    img = Image.alpha_composite(img, layer).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@lru_cache(maxsize=len(_VARIANTS))
def _cached(variant: str) -> bytes:
    return _build(variant)


def render_cover(variant: Optional[str] = None) -> bytes:
    """返回指定规格的封面 PNG 字节。

    variant: "og"(1200x630) | "square"(1080x1080)。未知值回落 og。
    结果按 variant 缓存 —— 图内无 per-song 数据，缓存整块字节是正确且高效的。
    """
    key = variant if variant in _VARIANTS else DEFAULT_VARIANT
    return _cached(key)
