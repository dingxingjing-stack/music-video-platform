// 统一请求层：apiFetch（普通，可匿名）+ authFetch（要求 JWT 身份）
// authFetch 每次从 Supabase Auth getSession() 取最新 access_token，不缓存旧 token。
import { supabase } from '../lib/supabase';

export interface RequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
}

/** 无 session 时抛出的明确未认证错误（UI 可据此打开 LoginModal）。 */
export class AuthenticationError extends Error {
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'AuthenticationError';
  }
}

const defaultHeaders = {
  'Content-Type': 'application/json',
};

async function rawFetch(url: string, opts: RequestOptions = {}): Promise<Response> {
  const { method = 'GET', headers = {}, body } = opts;
  const init: RequestInit = {
    method,
    headers: { ...defaultHeaders, ...headers },
    credentials: 'same-origin',
  };
  if (body !== undefined) {
    init.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  return fetch(url, init);
}

/** 普通请求（可匿名）：直接 fetch，无身份注入。 */
export async function apiFetch<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const resp = await rawFetch(url, opts);
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}: ${txt}`);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/** 受保护请求：自动附加 Authorization: Bearer <最新 access_token>；无 session 则抛 AuthenticationError。 */
export async function authFetch<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  if (!token) {
    // 不发送 X-User-ID、不伪造 user_id、不回退 localStorage —— 直接声明未登录
    throw new AuthenticationError();
  }
  const headers = { ...(opts.headers || {}), Authorization: `Bearer ${token}` };
  return apiFetch<T>(url, { ...opts, headers });
}

/** 可选登录请求：有 session 就附加 Bearer，无 session 则以匿名身份请求（不抛错）。 */
export async function authFetchOptional<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  const headers = token ? { ...(opts.headers || {}), Authorization: `Bearer ${token}` } : { ...(opts.headers || {}) };
  return apiFetch<T>(url, { ...opts, headers });
}

export const api = {
  get: <T = unknown>(url: string) => apiFetch<T>(url, { method: 'GET' }),
  post: <T = unknown>(url: string, data?: any) => apiFetch<T>(url, { method: 'POST', body: data }),
  auth: {
    get: <T = unknown>(url: string) => authFetch<T>(url, { method: 'GET' }),
    post: <T = unknown>(url: string, data?: any) => authFetch<T>(url, { method: 'POST', body: data }),
  },
};

export default api;