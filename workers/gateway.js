/**
 * Cloudflare Workers API Gateway + R2 存储
 * 功能：鉴权、IP 限流、CORS、请求转发、R2 上传/下载
 */

const RATE_LIMIT = 100;
const CORS_ORIGIN = '*';

// IP 限流
const ipCounts = new Map();
const ipTimers = new Map();

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const clientIP = request.headers.get('CF-Connecting-IP') || '127.0.0.1';

    // CORS 预检
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': CORS_ORIGIN,
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key',
          'Access-Control-Max-Age': '86400',
        }
      });
    }

    // IP 限流
    if (!ipTimers.has(clientIP)) {
      ipCounts.set(clientIP, 0);
      ipTimers.set(clientIP, setTimeout(() => {
        ipCounts.delete(clientIP);
        ipTimers.delete(clientIP);
      }, 60000));
    }

    const count = ipCounts.get(clientIP);
    if (count >= RATE_LIMIT) {
      return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    ipCounts.set(clientIP, count + 1);

    // R2 路由：上传
    if (url.pathname.startsWith('/api/v1/r2/upload') && request.method === 'PUT') {
      return await handleR2Upload(request, env.BUCKET);
    }

    // R2 路由：下载（预签名 URL）
    if (url.pathname.startsWith('/api/v1/r2/download/')) {
      const key = url.pathname.split('/').pop();
      return await handleR2Download(request, env.BUCKET, key);
    }

    // 转发到其他后端 API
    const API_BASE_URL = env.API_BASE_URL || 'http://localhost:8002';
    const targetUrl = API_BASE_URL + url.pathname + url.search;
    
    const forwardRequest = new Request(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    try {
      const response = await fetch(forwardRequest);
      const corsHeaders = {
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Access-Control-Allow-Credentials': 'true',
      };
      
      const newHeaders = new Headers(response.headers);
      Object.keys(corsHeaders).forEach(key => newHeaders.set(key, corsHeaders[key]));

      return new Response(response.body, {
        status: response.status,
        headers: newHeaders
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: 'Backend error', message: err.message }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
};

/**
 * R2 上传处理
 * PUT /api/v1/r2/upload?key=filename.mp3
 */
async function handleR2Upload(request, bucket) {
  const url = new URL(request.url);
  const key = url.searchParams.get('key');
  
  if (!key) {
    return new Response(JSON.stringify({ error: 'Missing key parameter' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    // 上传到 R2
    await bucket.put(key, request.body);
    
    // 生成公开访问 URL
    const publicUrl = `https://music-audio-storage.${request.headers.get('host')}/r2/${key}`;
    
    return new Response(JSON.stringify({
      success: true,
      key: key,
      url: publicUrl
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: 'Upload failed', message: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * R2 下载处理（预签名 URL）
 * GET /api/v1/r2/download/:key
 */
async function handleR2Download(request, bucket, key) {
  try {
    const object = await bucket.get(key);
    
    if (!object) {
      return new Response(JSON.stringify({ error: 'File not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 获取文件类型
    const contentType = object.httpMetadata?.contentType || 'application/octet-stream';
    
    return new Response(object.body, {
      headers: {
        'Content-Type': contentType,
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Cache-Control': 'public, max-age=31536000', // 1 年缓存
      }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: 'Download failed', message: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}