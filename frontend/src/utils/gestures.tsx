/**
 * 触控手势优化
 * 
 * 功能:
 * - 双指缩放 (pinch)
 * - 滑动切换 (swipe)
 * - 长按菜单 (long press)
 * - 防误触处理
 */

import { useEffect, useRef, useCallback, useState } from 'react';

// ========== 手势类型 ==========

export type GestureType = 
  | 'tap'      // 单击
  | 'doubletap' // 双击
  | 'swipe'    // 滑动
  | 'pinch'    // 捏合
  | 'longpress'; // 长按

export interface GestureEvent {
  type: GestureType;
  x: number;
  y: number;
  direction?: 'left' | 'right' | 'up' | 'down';
  scale?: number;
  duration?: number;
}

// ========== 手势 Hook ==========

export function useGestures(
  elementRef: React.RefObject<HTMLElement>,
  callbacks: {
    onTap?: (e: GestureEvent) => void;
    onDoubleTap?: (e: GestureEvent) => void;
    onSwipe?: (e: GestureEvent) => void;
    onPinch?: (e: GestureEvent) => void;
    onLongPress?: (e: GestureEvent) => void;
  }
) {
  const touchState = useRef<{
    startX: number;
    startY: number;
    lastTouchDistance: number | null;
    tapCount: number;
    tapTimer: number | null;
    longPressTimer: number | null;
  }>({
    startX: 0,
    startY: 0,
    lastTouchDistance: null,
    tapCount: 0,
    tapTimer: null,
    longPressTimer: null,
  });

  const getTouchDistance = (e: TouchEvent) => {
    if (e.touches.length < 2) return null;
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const getDirection = (dx: number, dy: number): GestureEvent['direction'] => {
    if (Math.abs(dx) > Math.abs(dy)) {
      return dx > 0 ? 'right' : 'left';
    }
    return dy > 0 ? 'down' : 'up';
  };

  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;

    const handleTouchStart = (e: TouchEvent) => {
      const touch = e.touches[0];
      touchState.current.startX = touch.clientX;
      touchState.current.startY = touch.clientY;
      touchState.current.lastTouchDistance = getTouchDistance(e);
      touchState.current.tapCount = 0;

      // 长按检测 (500ms)
      touchState.current.longPressTimer = window.setTimeout(() => {
        if (callbacks.onLongPress) {
          callbacks.onLongPress({
            type: 'longpress',
            x: touchState.current.startX,
            y: touchState.current.startY,
            duration: 500,
          });
        }
        touchState.current.longPressTimer = null;
      }, 500);
    };

    const handleTouchMove = (e: TouchEvent) => {
      // 取消长按
      if (touchState.current.longPressTimer) {
        clearTimeout(touchState.current.longPressTimer);
        touchState.current.longPressTimer = null;
      }

      const distance = getTouchDistance(e);
      if (distance !== null && touchState.current.lastTouchDistance !== null) {
        // 捏合手势
        const scale = distance / touchState.current.lastTouchDistance;
        touchState.current.lastTouchDistance = distance;

        if (callbacks.onPinch && Math.abs(scale - 1) > 0.1) {
          callbacks.onPinch({
            type: 'pinch',
            x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
            y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
            scale,
          });
        }
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      // 取消长按
      if (touchState.current.longPressTimer) {
        clearTimeout(touchState.current.longPressTimer);
        touchState.current.longPressTimer = null;
      }

      const touch = e.changedTouches[0];
      const dx = touch.clientX - touchState.current.startX;
      const dy = touch.clientY - touchState.current.startY;
      const distance = Math.sqrt(dx * dx + dy * dy);

      // 滑动检测 (>30px)
      if (distance > 30) {
        if (callbacks.onSwipe) {
          callbacks.onSwipe({
            type: 'swipe',
            x: touch.clientX,
            y: touch.clientY,
            direction: getDirection(dx, dy),
          });
        }
        return;
      }

      // 点击/双击检测
      touchState.current.tapCount++;
      if (touchState.current.tapCount === 1) {
        // 单击 - 延迟 250ms 确认
        touchState.current.tapTimer = window.setTimeout(() => {
          if (callbacks.onTap) {
            callbacks.onTap({
              type: 'tap',
              x: touch.clientX,
              y: touch.clientY,
            });
          }
          touchState.current.tapCount = 0;
          touchState.current.tapTimer = null;
        }, 250);
      } else {
        // 双击
        if (touchState.current.tapTimer) {
          clearTimeout(touchState.current.tapTimer);
          touchState.current.tapTimer = null;
        }
        if (callbacks.onDoubleTap) {
          callbacks.onDoubleTap({
            type: 'doubletap',
            x: touch.clientX,
            y: touch.clientY,
          });
        }
        touchState.current.tapCount = 0;
      }
    };

    el.addEventListener('touchstart', handleTouchStart, { passive: true });
    el.addEventListener('touchmove', handleTouchMove, { passive: true });
    el.addEventListener('touchend', handleTouchEnd, { passive: true });

    return () => {
      el.removeEventListener('touchstart', handleTouchStart);
      el.removeEventListener('touchmove', handleTouchMove);
      el.removeEventListener('touchend', handleTouchEnd);
      if (touchState.current.longPressTimer) clearTimeout(touchState.current.longPressTimer);
      if (touchState.current.tapTimer) clearTimeout(touchState.current.tapTimer);
    };
  }, [elementRef, callbacks]);
}

// ========== 防误触 Wrap 组件 ==========

export function TouchSafeWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="touch:none select-none"
      style={{
        touchAction: 'manipulation',
        WebkitUserSelect: 'none',
        userSelect: 'none',
      }}
    >
      {children}
    </div>
  );
}

// ========== 手势反馈 ==========

export function useTouchFeedback() {
  const [touching, setTouching] = useState(false);

  const handlers = {
    onTouchStart: () => setTouching(true),
    onTouchEnd: () => setTouching(false),
    onTouchCancel: () => setTouching(false),
  };

  return { touching, ...handlers };
}