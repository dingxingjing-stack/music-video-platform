// 全局音效管理 — 按需创建 Audio，首屏零加载，静音持久化
//  音源: Pixabay 免费音效 CDN（64kbps ogg/mp3 轻量化）
//  用法: playSound('click')  ← 一行调用

const SOUND_URLS: Record<string, string> = {
  click:        'https://cdn.pixabay.com/download/audio/2022/03/10/audio_c6c8f3c7b4.mp3',
  toggle:       'https://cdn.pixabay.com/download/audio/2022/03/10/audio_7c5c5f5b6f.mp3',
  success:      'https://cdn.pixabay.com/download/audio/2022/03/15/audio_3def0b681a.mp3',
  error:        'https://cdn.pixabay.com/download/audio/2022/03/10/audio_2f9e4e7b8a.mp3',
  favorite:     'https://cdn.pixabay.com/download/audio/2022/03/15/audio_bb630cc16c.mp3',
  notification: 'https://cdn.pixabay.com/download/audio/2022/03/10/audio_a44b0e6e28.mp3',
  complete:     'https://cdn.pixabay.com/download/audio/2022/03/15/audio_3def0b681a.mp3',
};

const VOLUME = 0.3;                       // 默认音量 0.3
const cache = new Map<string, HTMLAudioElement>();
let globalMuted = localStorage.getItem('zyvexo-sound-muted') === 'true';

export function isMuted(): boolean { return globalMuted; }

export function setMuted(v: boolean): void {
  globalMuted = v;
  localStorage.setItem('zyvexo-sound-muted', String(v));
}

export function toggleMuted(): boolean {
  setMuted(!globalMuted);
  return globalMuted;
}

/** 播放音效 — 一行调用，自动懒加载，静音时直接拦截 */
export function playSound(type: keyof typeof SOUND_URLS): void {
  if (globalMuted) return;                // 静音 → 零开销拦截
  const url = SOUND_URLS[type];
  if (!url) return;

  let audio = cache.get(type);
  if (!audio) {                            // 按需创建，首屏不加载
    audio = new Audio(url);
    audio.volume = VOLUME;
    audio.preload = 'none';                // 非自动预加载
    cache.set(type, audio);
  }

  audio.currentTime = 0;                  // 重置播放头
  audio.play().catch(() => {});            // 自动播放策略可能拦截，静默失败
}

/** 预热（用户首次交互后调用，不阻塞首屏） */
export function preloadSounds(): void {
  Object.keys(SOUND_URLS).forEach(k => {
    if (!cache.has(k)) {
      const a = new Audio(SOUND_URLS[k]);
      a.preload = 'auto';
      a.volume = 0;
      cache.set(k, a);
    }
  });
}
