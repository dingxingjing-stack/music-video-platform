/**
 * Design System tokens — 统一的色板/间距/圆角/字体/动效
 * 深色、克制、专业 AI SaaS 风。避免花哨渐变堆砌。
 */
export const tokens = {
  // ── 色板 ─────────────────────────────
  bg: {
    base: '#0d0f12',      // 页面主背景（极深，偏冷灰）
    surface: '#14171b',   // 卡片/容器
    raised: '#1a1e24',    // 悬浮/次级容器
    hover: '#20252c',     // hover
    overlay: 'rgba(10,12,15,0.72)',
  },
  border: {
    default: '#23272e',
    strong: '#2d333b',
    focus: '#4f6272',
  },
  text: {
    primary: '#e8eaed',
    secondary: '#a3abb5',
    muted: '#6b7480',
    inverse: '#0d0f12',
  },
  accent: {
    DEFAULT: '#e85d2e',   // 主强调（克制暖橙，不刺眼）
    strong: '#ff7a45',
    soft: 'rgba(232,93,46,0.12)',
    ring: 'rgba(232,93,46,0.4)',
  },
  status: {
    success: '#3fb68b',
    warning: '#e5a23e',
    danger: '#e25c5c',
    info: '#5b9bd5',
  },
  // ── 间距 (px) ────────────────────────
  space: { xs: 4, sm: 8, md: 16, lg: 24, xl: 40, '2xl': 64 },
  // ── 圆角 ─────────────────────────────
  radius: { sm: 6, md: 10, lg: 14, xl: 20, full: 999 },
  // ── 字号 ─────────────────────────────
  font: {
    display: '1.875rem',  // 30
    h1: '1.5rem',         // 24
    h2: '1.25rem',        // 20
    h3: '1.0625rem',      // 17
    body: '0.875rem',     // 14
    small: '0.8125rem',   // 13
    caption: '0.75rem',   // 12
    micro: '0.6875rem',   // 11
  },
  // ── 阴影 ─────────────────────────────
  shadow: {
    sm: '0 1px 2px rgba(0,0,0,0.3)',
    md: '0 4px 12px rgba(0,0,0,0.35)',
    lg: '0 12px 32px rgba(0,0,0,0.45)',
  },
} as const;