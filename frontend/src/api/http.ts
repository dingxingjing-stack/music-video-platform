// 统一请求层：apiFetch（普通，可匿名）+ authFetch（要求 JWT 身份）
// authFetch 每次从 Supabase Auth getSession() 取最新 access_token，不缓存旧 token。
import { supabase } from '../lib/supabase';

export interface RequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
  /** 单次请求的最长等待时间；超时抛 TimeoutError 而不是永远挂着。 */
  timeoutMs?: number;
}

/** 无 session 时抛出的明确未认证错误（UI 可据此打开 LoginModal）。 */
export class AuthenticationError extends Error {
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'AuthenticationError';
  }
}

/** 请求或取会话超时：让 UI 能给出"重试"，而不是永久停在加载态/把目录判为不可用。 */
export class TimeoutError extends Error {
  constructor(message = 'Request timed out') {
    super(message);
    this.name = 'TimeoutError';
  }
}

/**
 * 取会话失败（≠ 未登录）。
 * 之前两种情形被压成同一个 undefined，于是"存储不可用 / refresh 卡住"也会被 authFetch
 * 报成 AuthenticationError，UI 就显示"请先登录"——用户明明刚用 Google 登录过。
 */
export class SessionUnavailableError extends Error {
  constructor(message = '登录状态异常，请重新登录后再试。') {
    super(message);
    this.name = 'SessionUnavailableError';
  }
}

const DEFAULT_TIMEOUT_MS = 20000;
const SESSION_TIMEOUT_MS = 8000;

/**
 * 取会话的三种结果。必须是三态而不是 string | undefined：
 * "确实没有 session"和"读不到 session"要走不同的分支，也只有分开才能在
 * 生产日志里判断 Google 登录后到底断在哪一步。
 */
type SessionOutcome =
  | { kind: 'available'; token: string }
  | { kind: 'no_session' }
  | { kind: 'error'; reason: 'throw' | 'reject' | 'timeout' | 'invalid_session' };

const defaultHeaders = {
  'Content-Type': 'application/json',
};

async function rawFetch(url: string, opts: RequestOptions = {}): Promise<Response> {
  const { method = 'GET', headers = {}, body, timeoutMs = DEFAULT_TIMEOUT_MS } = opts;
  const init: RequestInit = {
    method,
    headers: { ...defaultHeaders, ...headers },
    credentials: 'same-origin',
  };
  if (body !== undefined) {
    init.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  // 没有超时的 fetch 会让调用方的 finally 永远到不了：定价目录判成 null → 套餐退化成
  // "即将上线"、补充包整块消失；"我的作品"则永久停在"加载中"。这里统一兜住。
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') {
      throw new TimeoutError(`请求超过 ${Math.round(timeoutMs / 1000)} 秒未响应`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 取会话结果 → 诊断记录。只允许记录情形标识（session_available / no_session /
 * session_error + 原因码）：token、Authorization 头、Supabase 错误对象一律不落记录。
 *
 * 为什么不只是 console.log：生产构建用 terser 且 drop_console=true，console.* 会被
 * 整条删掉（实测新包里搜不到 session_available），所以生产上必须靠这个内存缓冲读数 ——
 * DevTools 里执行 window.__melovarAuthDiag 即可看到最近 50 次的判定结果。
 * console 输出保留给本地 dev（不删 console）。
 */
export interface AuthDiagEntry {
  /** 毫秒时间戳，用于和他点击订阅的时刻对齐。 */
  t: number;
  kind: SessionOutcome['kind'];
  reason?: SessionOutcome['reason'];
}

const authDiag: AuthDiagEntry[] = [];

if (typeof window !== 'undefined') {
  (window as any).__melovarAuthDiag = authDiag;
}

function recordSessionOutcome(outcome: SessionOutcome) {
  authDiag.push({
    t: Date.now(),
    kind: outcome.kind,
    ...(outcome.kind === 'error' ? { reason: outcome.reason } : {}),
  });
  if (authDiag.length > 50) authDiag.shift();

  if (outcome.kind === 'available') {
    console.info('[auth] session_available');
  } else if (outcome.kind === 'no_session') {
    console.warn('[auth] no_session');
  } else {
    console.warn(`[auth] session_error reason=${outcome.reason}`);
  }
}

async function readSessionOutcome(): Promise<SessionOutcome> {
  let pending: Promise<SessionOutcome>;
  try {
    // getSession 在客户端未就绪/存储不可用时会同步 throw，必须一起兜住：
    // 只 .catch() promise 会让它把异常直接抛给调用方，于是所有请求发不出去。
    // 这里用 then(onFulfilled, onRejected) 而不是 catch：避免把 fulfilled 分支里
    // 自己抛的错也误判成 reject。
    pending = supabase.auth.getSession().then(
      ({ data }) => {
        const session = data?.session;
        if (!session) return { kind: 'no_session' } as SessionOutcome;
        const token = session.access_token;
        if (typeof token !== 'string' || !token) {
          return { kind: 'error', reason: 'invalid_session' } as SessionOutcome;
        }
        return { kind: 'available', token } as SessionOutcome;
      },
      () => ({ kind: 'error', reason: 'reject' } as SessionOutcome),
    );
  } catch {
    return { kind: 'error', reason: 'throw' };
  }
  // supabase-js 在 token 过期时会先做一次 refresh 往返，网络不通常会让这个 await
  // 挂住 —— 挂住不能等于"永久无响应"，超时后单独报成 session_error(timeout)。
  return Promise.race([
    pending,
    new Promise<SessionOutcome>((resolve) =>
      setTimeout(() => resolve({ kind: 'error', reason: 'timeout' }), SESSION_TIMEOUT_MS),
    ),
  ]);
}

async function getSessionOutcome(): Promise<SessionOutcome> {
  let outcome: SessionOutcome;
  try {
    outcome = await readSessionOutcome();
  } catch {
    outcome = { kind: 'error', reason: 'throw' };
  }
  recordSessionOutcome(outcome);
  return outcome;
}

/**
 * 失败响应 → 可安全展示的 Error。
 * 401 归一为 AuthenticationError（后端只认 JWT，未登录/令牌过期都应走登录态分支）；
 * 其余只保留状态码 + 后端 detail —— 直接把整段响应体塞进 message 会把网关的 HTML
 * 错误页原样渲染到页面上，用户看到的就是一屏乱码。
 */
async function toHttpError(resp: Response): Promise<Error> {
  if (resp.status === 401) return new AuthenticationError();
  const txt = await resp.text().catch(() => '');
  let detail = '';
  try {
    const parsed = JSON.parse(txt) as { detail?: unknown };
    if (typeof parsed?.detail === 'string') detail = parsed.detail.slice(0, 200);
  } catch {
    // 非 JSON 响应体：不外泄内容，只报状态码
  }
  return new Error(detail ? `HTTP ${resp.status}: ${detail}` : `HTTP ${resp.status}`);
}

/** 普通请求（可匿名）：直接 fetch，无身份注入。 */
export async function apiFetch<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const resp = await rawFetch(url, opts);
  if (!resp.ok) {
    throw await toHttpError(resp);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/**
 * 受保护请求：自动附加 Authorization: Bearer <最新 access_token>。
 * 无 session → AuthenticationError（UI 该打开登录框）；
 * 取会话失败/超时 → SessionUnavailableError（UI 该提示"登录状态异常"，而不是"请先登录"）。
 */
export async function authFetch<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const outcome = await getSessionOutcome();
  if (outcome.kind === 'error') throw new SessionUnavailableError();
  if (outcome.kind === 'no_session') {
    // 不发送 X-User-ID、不伪造 user_id、不回退 localStorage —— 直接声明未登录
    throw new AuthenticationError();
  }
  const headers = { ...(opts.headers || {}), Authorization: `Bearer ${outcome.token}` };
  return apiFetch<T>(url, { ...opts, headers });
}

/**
 * 可选登录请求：有 session 就附加 Bearer，其余一律以匿名身份请求（不抛错）。
 * 匿名降级必须保留：/credits/plans、/credits/packs 是未登录也要能看的目录接口，
 * 取会话出问题就让它们报错的话，用户看到的是"整页没有付款按钮"。
 */
export async function authFetchOptional<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const outcome = await getSessionOutcome();
  const headers =
    outcome.kind === 'available'
      ? { ...(opts.headers || {}), Authorization: `Bearer ${outcome.token}` }
      : { ...(opts.headers || {}) };
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