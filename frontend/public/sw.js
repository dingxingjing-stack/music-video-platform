/**
 * PWA Service Worker 配置 (P3-6 离线模式)
 * 
 * 功能:
 * - 离线缓存核心资源
 * - 后台同步
 * - 推送通知
 * - 添加到主屏幕
 * 
 * 缓存策略:
 * - 核心 HTML/CSS/JS: Cache First
 * - 音频文件：Stale While Revalidate
 * - API 请求：Network First, fallback to Cache
 */

const CACHE_NAME = 'hermes-audio-v1';
const ASSETS_CACHE = 'hermes-assets-v1';
const AUDIO_CACHE = 'hermes-audio-cache-v1';

// 核心资源预缓存
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/offline.html',
];

// 核心 JS/CSS 缓存
const CORE_JS_CSS = [
  '/assets/main.js',
  '/assets/vendor.js',
  '/assets/main.css',
];

// 安装事件 - 预缓存核心资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)),
      caches.open(ASSETS_CACHE).then((cache) => cache.addAll(CORE_JS_CSS)),
    ])
  );
  self.skipWaiting();
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME && name !== ASSETS_CACHE && name !== AUDIO_CACHE)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// 请求拦截 - 智能缓存策略
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 静态资源：Cache First
  if (request.destination === 'style' || request.destination === 'script') {
    event.respondWith(
      caches.match(request).then((cached) => {
        return cached || fetch(request).then((response) => {
          const clone = response.clone();
          caches.open(ASSETS_CACHE).then((cache) => cache.put(request, clone));
          return response;
        });
      })
    );
    return;
  }

  // HTML 页面：Cache First
  if (request.destination === 'document') {
    event.respondWith(
      caches.match(request).then((cached) => {
        return cached || fetch(request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        }).catch(() => caches.match('/offline.html'));
      })
    );
    return;
  }

  // 音频文件：Stale While Revalidate
  if (url.pathname.startsWith('/api/audio') || url.pathname.endsWith('.mp3') || url.pathname.endsWith('.wav')) {
    event.respondWith(
      caches.open(AUDIO_CACHE).then((cache) => {
        return cache.match(request).then((cached) => {
          const fetchPromise = fetch(request).then((response) => {
            if (response.ok) {
              cache.put(request, response.clone());
            }
            return response;
          });
          return cached || fetchPromise;
        });
      })
    );
    return;
  }

  // API 请求：Network First, fallback to Cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // 默认：Network First
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});

// 后台同步
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-audio-upload') {
    event.waitUntil(
      // 同步未完成的音频上传
      syncPendingUploads()
    );
  }
});

// 推送通知
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'Hermes 音乐平台', {
      body: data.body || '您有新的通知',
      icon: '/icon-192.png',
      badge: '/badge-192.png',
      data: data.url || '/',
    })
  );
});

// 通知点击处理
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === event.notification.data && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data);
      }
    })
  );
});

// 辅助函数：同步待上传音频
async function syncPendingUploads() {
  // 从 IndexedDB 读取待上传列表
  // 逐个上传
  // 成功后移除
}

// 消息处理 (与主线程通信)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});