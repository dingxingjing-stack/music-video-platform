/**
 * PWA Service Worker 注册 (P3-6)
 * 精简版：KISS
 */

export function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
      try {
        const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
        console.log('✅ SW 注册成功:', reg.scope);

        reg.addEventListener('updatefound', () => {
          const worker = reg.installing;
          if (!worker) return;

          worker.addEventListener('statechange', () => {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) {
              if (confirm('🎉 新版本已就绪！立即刷新？')) {
                window.location.reload();
              }
            }
          });
        });

        console.log('📬 推送通知支持就绪');
      } catch (error) {
        console.error('❌ SW 注册失败:', error);
      }
    });
  } else {
    console.warn('⚠️ 浏览器不支持 Service Worker');
  }
}

export async function requestNotificationPermission() {
  if (!('Notification' in window)) return false;
  return (await Notification.requestPermission()) === 'granted';
}

export async function subscribeToPush(publicKey: string) {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });

  await fetch('/api/v1/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(sub),
  });

  return sub;
}

export async function unsubscribeFromPush() {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  await sub?.unsubscribe();
}

function urlBase64ToUint8Array(base64: string) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const base64Full = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64Full);
  return Uint8Array.from(rawData, c => c.charCodeAt(0));
}

export const isOffline = () => !navigator.onLine;

export const onOnlineStatusChange = (cb: (online: boolean) => void) => {
  window.addEventListener('online', () => cb(true));
  window.addEventListener('offline', () => cb(false));
  cb(navigator.onLine);
};

export async function checkPWAInstallability() {
  let deferredPrompt: any;
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    deferredPrompt = e;
  });

  return {
    canInstall: !!deferredPrompt,
    install: async () => {
      if (!deferredPrompt) return false;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      return outcome === 'accepted';
    },
  };
}

// 自动注册
if (typeof window !== 'undefined') {
  registerServiceWorker();
}