// API 统一配置 — 生产环境用 Render 后端，本地开发用 localhost
const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://ai-music-backend-8e85.onrender.com';

const WS_BASE =
  import.meta.env.VITE_WS_BASE ||
  'wss://ai-music-backend-8e85.onrender.com';

export const api = {
  base: API_BASE,
  ws: WS_BASE,
  /** 拼接 REST 路径 */
  url: (path: string) => `${API_BASE}${path}`,
  /** 拼接 WebSocket 路径 */
  wsUrl: (path: string) => `${WS_BASE}${path}`,
};

export default api;
