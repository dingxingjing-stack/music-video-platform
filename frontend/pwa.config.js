/**
 * PWA 配置 (P3-6 离线模式)
 * 
 * 使用 next-pwa 或 workbox 进行配置
 */

module.exports = {
  // PWA 配置
  pwa: {
    dest: 'public',
    cacheOnFrontEndNav: true,
    aggressiveFrontEndNavCaching: true,
    reloadOnOnline: true,
    sw: 'sw.js',
    disable: process.env.NODE_ENV === 'development',
  },

  // manifest.json 配置
  manifest: {
    name: 'Hermes 音乐视频平台',
    short_name: 'Hermes Music',
    description: 'AI+DAW+MV 一体化音乐创作平台',
    theme_color: '#121212',
    background_color: '#121212',
    display: 'standalone',
    orientation: 'portrait',
    scope: '/',
    start_url: '/',
    icons: [
      {
        src: '/icon-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
      },
      {
        src: '/icon-maskable.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  },

  // 离线功能
  offline: {
    enabled: true,
    offlinePage: '/offline.html',
    fallbacks: {
      document: '/offline.html',
    },
  },

  // 推送通知
  push: {
    enabled: true,
    vapidPublicKey: process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY,
  },
};