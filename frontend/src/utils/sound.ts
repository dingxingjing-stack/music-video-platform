// 音效类型 → 免费音源映射（懒加载）
// 来源: https://freesound.org / https://pixabay.com/sound-effects
const SOUND_URLS: Record<string, string> = {
  click:      'https://cdn.pixabay.com/download/audio/2022/03/10/audio_c6c8f3c7b4.mp3',
  toggle:     'https://cdn.pixabay.com/download/audio/2022/03/10/audio_7c5c5f5b6f.mp3',
  success:    'https://cdn.pixabay.com/download/audio/2022/03/15/audio_3def0b681a.mp3',
  error:      'https://cdn.pixabay.com/download/audio/2022/03/10/audio_2f9e4e7b8a.mp3',
  favorite:   'https://cdn.pixabay.com/download/audio/2022/03/15/audio_bb630cc16c.mp3',
  notification: 'https://cdn.pixabay.com/download/audio/2022/03/10/audio_a44b0e6e28.mp3',
  complete:   'https://cdn.pixabay.com/download/audio/2022/03/15/audio_3def0b681a.mp3',
};

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

/** 播放音效 — 一行调用，自动懒加载 */
export function playSound(type: keyof typeof SOUND_URLS): void {
  if (globalMuted) return;
  const url = SOUND_URLS[type];
  if (!url) return;

  let audio = cache.get(type);
  if (!audio) {
    audio = new Audio(url);
    audio.volume = 0.25;
    audio.preload = 'auto';
    cache.set(type, audio);
  }

  audio.currentTime = 0;
  audio.play().catch(() => {}); // 浏览器自动播放策略可能拦截，静默失败
}

/** 预热常用音效（在用户首次交互后调用） */
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
