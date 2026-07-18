// 带内存缓存的 fetch 请求工具
// 高频接口缓存 5 分钟，降低 Render 后端重复请求，缓解冷启动压力

interface CacheEntry {
  data: any;
  expiry: number;
}

const cache = new Map<string, CacheEntry>();
const DEFAULT_TTL = 5 * 60 * 1000; // 5 分钟

/** 清除过期缓存 */
function cleanExpired() {
  const now = Date.now();
  for (const [key, entry] of cache) {
    if (entry.expiry < now) cache.delete(key);
  }
}

/**
 * 带内存缓存的 fetch
 * @param url 请求地址
 * @param ttl 缓存有效期（ms），默认 5 分钟
 * @param options fetch options
 */
export async function cachedFetch<T = any>(
  url: string,
  ttl: number = DEFAULT_TTL,
  options?: RequestInit
): Promise<T> {
  cleanExpired();

  const cacheKey = url + JSON.stringify(options || {});

  // 命中缓存直接返回
  const cached = cache.get(cacheKey);
  if (cached && cached.expiry > Date.now()) {
    return cached.data as T;
  }

  // 未命中 → 发请求
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  cache.set(cacheKey, { data, expiry: Date.now() + ttl });
  return data as T;
}

/** 清除指定 URL 的缓存 */
export function invalidateCache(url: string) {
  for (const key of cache.keys()) {
    if (key.startsWith(url)) cache.delete(key);
  }
}

/** 清除全部缓存 */
export function clearAllCache() {
  cache.clear();
}
