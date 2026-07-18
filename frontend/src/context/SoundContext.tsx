import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { isMuted, toggleMuted, playSound, preloadSounds } from '../utils/sound';

interface SoundCtx {
  muted: boolean;
  toggle: () => void;
  play: (s: Parameters<typeof playSound>[0]) => void;
}

const Ctx = createContext<SoundCtx>({ muted: false, toggle: () => {}, play: () => {} });

export function SoundProvider({ children }: { children: ReactNode }) {
  const [muted, setMutedState] = useState(isMuted());

  useEffect(() => {
    // 首次交互预热音效（不阻塞首屏）
    const handler = () => preloadSounds();
    document.addEventListener('click', handler, { once: true });
    document.addEventListener('keydown', handler, { once: true });
    return () => {
      document.removeEventListener('click', handler);
      document.removeEventListener('keydown', handler);
    };
  }, []);

  const toggle = () => setMutedState(toggleMuted());
  const play = (s: Parameters<typeof playSound>[0]) => playSound(s);

  return <Ctx.Provider value={{ muted, toggle, play }}>{children}</Ctx.Provider>;
}

export function useSound() { return useContext(Ctx); }
