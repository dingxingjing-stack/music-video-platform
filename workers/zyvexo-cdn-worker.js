// Zyvexo CDN 反向代理 Worker
// 把对自定义域名的请求转发到 Cloudflare R2 bucket
//
// 部署：
//   1. Cloudflare Dashboard → Workers & Pages → Create Worker
//   2. 名字：zyvexo-cdn
//   3. Deploy 一个空白 worker，然后 Edit Code
//   4. 把本文件全部内容粘贴进去 → Deploy
//   5. Settings → Domains & Routes → Add Custom Domain
//   6. 输入 cdn.music-video-platform.com（或你的子域名）
//   7. Render Environment 加：CDN_BASE_URL=https://cdn.music-video-platform.com
//
// 访问示例：
//   https://cdn.music-video-platform.com/audio/abc.mp3
//   → 转发到
//   https://b8743fc421303345b81bce87d3b10742.r2.cloudflarestorage.com/music-audio-storage/audio/abc.mp3

const R2_ACCOUNT_ID = "b8743fc421303345b81bce87d3b10742";
const R2_BUCKET_NAME = "music-audio-storage";
const R2_ENDPOINT = `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com`;

// 健康检查路径白名单（不转发到 R2）
const HEALTH_PATHS = new Set(["/", "/health", "/ping", "/status"]);

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // CORS 预检
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
          "Access-Control-Allow-Headers": "*",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // 健康检查端点
    if (HEALTH_PATHS.has(url.pathname)) {
      return new Response(
        JSON.stringify({
          service: "zyvexo-cdn",
          status: "ok",
          timestamp: new Date().toISOString(),
        }),
        {
          headers: {
            "content-type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    // 拼接 R2 fetch URL
    // 注意：url.pathname 以 "/" 开头（例如 "/audio/abc.mp3"），slice(1) 去掉它得到 "audio/abc.mp3"
    const objectKey = url.pathname.slice(1);
    if (!objectKey) {
      return new Response(
        JSON.stringify({ error: "missing object key" }),
        { status: 400, headers: { "content-type": "application/json" } }
      );
    }

    const r2Url = `${R2_ENDPOINT}/${R2_BUCKET_NAME}/${objectKey}`;

    // 转发请求到 R2（注意：R2 默认 bucket 必须设为 public 才能直接读；
    // 或者在 Worker 里给 R2 bucket 绑定 R2 binding 后用 env.BUCKET.get(key)。
    // 这里采用 fetch R2 public URL 的最简方案：请确保 bucket 已开启 Public Access，
    // 或者改为使用 R2 binding）
    let r2Response;
    try {
      r2Response = await fetch(r2Url, {
        method: "GET",
        // 显式只取 GET，避免把 POST/DELETE 转发过去
        headers: { "User-Agent": "zyvexo-cdn-worker/1.0" },
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "R2 fetch failed", detail: String(err) }),
        { status: 502, headers: { "content-type": "application/json" } }
      );
    }

    // 复制响应并加 CORS + 缓存头
    const headers = new Headers(r2Response.headers);
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    headers.set("Access-Control-Expose-Headers", "Content-Length, Content-Type, ETag");

    // 静态资源一年缓存（音频文件片段是 immutable 的，因为 key 是 uuid）
    if (r2Response.status === 200) {
      headers.set("Cache-Control", "public, max-age=31536000, immutable");
    }

    // 文件不存在时返回 json 而不是 R2 的 xml
    if (r2Response.status === 404) {
      return new Response(
        JSON.stringify({
          error: "object not found",
          key: objectKey,
          bucket: R2_BUCKET_NAME,
        }),
        {
          status: 404,
          headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" },
        }
      );
    }

    return new Response(r2Response.body, {
      status: r2Response.status,
      statusText: r2Response.statusText,
      headers,
    });
  },
};
