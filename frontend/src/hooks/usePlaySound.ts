// usePlaySound — 通用音效 Hook，一行调用
// 用法: const play = usePlaySound(); play('click');
import { useCallback } from 'react';
import { playSound, type playSound as PlaySoundType } from '../utils/sound';

export function usePlaySound() {
  return useCallback((type: Parameters<typeof PlaySoundType>[0]) => {
    playSound(type);
  }, []);
}
