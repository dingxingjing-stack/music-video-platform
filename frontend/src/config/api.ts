// API 统一配置 — 生产环境通过 VITE_API_BASE_URL 注入，无 fallback
const API_BASE = import.meta.env.VITE_API_BASE_URL;
const WS_BASE = import.meta.env.VITE_WS_BASE;

if (!API_BASE) {
  throw new Error('[api] VITE_API_BASE_URL is not set. Configure it in .env.production or Cloudflare Pages environment variables.');
}
if (!WS_BASE) {
  throw new Error('[api] VITE_WS_BASE is not set. Configure it in .env.production or Cloudflare Pages environment variables.');
}

export const api = {
  base: API_BASE,
  ws: WS_BASE,
  /** 拼接 REST 路径 */
  url: (path: string) => `${API_BASE}${path}`,
  /** 拼接 WebSocket 路径 */
  wsUrl: (path: string) => `${WS_BASE}${path}`,
};

export default api;
