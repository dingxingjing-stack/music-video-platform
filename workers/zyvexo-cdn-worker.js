// Zyvexo CDN 反向代理 Worker
// 把对自定义域名的请求通过 R2 binding 读取对象并返回
//
// 部署：
//   1. wrangler deploy --config workers/wrangler.cdn.toml
//   2. （可选）Settings → Domains & Routes → Add Custom Domain
//   3. Render Environment 加：CDN_BASE_URL=https://zyvexo-cdn.<account>.workers.dev
//      （或绑了自定义域名后改成 https://cdn.music-video-platform.com）
//
// wrangler.cdn.toml 必须配 R2 binding：
//   [[r2_buckets]]
//   binding = "BUCKET"
//   bucket_name = "music-audio-storage"
//
// 访问示例：
//   https://zyvexo-cdn.<account>.workers.dev/audio/abc.mp3
//   → env.BUCKET.get("audio/abc.mp3")

const R2_BUCKET_NAME = "music-audio-storage";

// 健康检查路径白名单（不转发到 R2）
const HEALTH_PATHS = new Set(["/", "/health", "/ping", "/status"]);

export default {
  async fetch(request, env) {
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
          bucket: R2_BUCKET_NAME,
          binding: env.BUCKET ? "ok" : "missing",
        }),
        {
          headers: {
            "content-type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    if (!env.BUCKET) {
      return new Response(
        JSON.stringify({ error: "R2 binding missing", hint: "请在 wrangler.cdn.toml 里配 [[r2_buckets]] binding=BUCKET" }),
        { status: 500, headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } }
      );
    }

    // 拼接对象 key
    const objectKey = url.pathname.slice(1);
    if (!objectKey) {
      return new Response(
        JSON.stringify({ error: "missing object key" }),
        { status: 400, headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } }
      );
    }

    // HEAD 用 head()，GET 用 get()
    let object;
    try {
      if (request.method === "HEAD") {
        object = await env.BUCKET.head(objectKey);
      } else if (request.method === "GET") {
        object = await env.BUCKET.get(objectKey, { range: request.headers.get("range") || undefined });
      } else {
        return new Response(
          JSON.stringify({ error: "method not allowed", method: request.method }),
          { status: 405, headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } }
        );
      }
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "R2 read failed", detail: String(err) }),
        { status: 502, headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } }
      );
    }

    if (!object) {
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

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    headers.set("Access-Control-Expose-Headers", "Content-Length, Content-Type, ETag, Content-Range, Accept-Ranges");

    if (object.httpEtag) headers.set("ETag", object.httpEtag);
    if (object.size != null) headers.set("Content-Length", String(object.size));
    if (object.range) {
      headers.set("Content-Range", `bytes ${object.range.offset}-${object.range.offset + object.range.length - 1}/${object.range.length}`);
      headers.set("Accept-Ranges", "bytes");
    }
    if (request.method === "HEAD" || !object.body) {
      headers.set("Content-Type", object.httpMetadata?.contentType || "application/octet-stream");
      return new Response(null, { status: 200, headers });
    }

    // 静态资源一年缓存（音频文件片段是 immutable 的，因为 key 是 uuid）
    headers.set("Cache-Control", "public, max-age=31536000, immutable");

    return new Response(object.body, { status: 200, headers });
  },
};
