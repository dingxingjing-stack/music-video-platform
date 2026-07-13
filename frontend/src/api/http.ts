// 简易 fetch 包装，提供 get、post 方法
// 采用 ES2020+（tsconfig 已配置 lib: ['ES2020', 'DOM'])

export interface RequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
}

const defaultHeaders = {
  'Content-Type': 'application/json',
};

export async function request<T>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', headers = {}, body } = opts;
  const init: RequestInit = {
    method,
    headers: { ...defaultHeaders, ...headers },
    credentials: 'same-origin', // 发送 cookie，保持会话
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${txt}`);
  }
  // 204 No Content 返回空对象
  if (resp.status === 204) return {} as T;
  return (await resp.json()) as T;
}

export const get = <T>(url: string) => request<T>(url, { method: 'GET' });
export const post = <T>(url: string, data: any) => request<T>(url, { method: 'POST', body: data });

// 兼容默认导入的写法（常见于老代码）
const http = { get, post };
export default http;
