/**
 * 性能优化工具
 * 
 * 功能:
 * - 代码分割 (lazy loading)
 * - 图片懒加载
 * - 资源预加载
 * - 性能监控
 */

import { useEffect, useRef, useState, useCallback } from 'react';

// ========== 图片懒加载 ==========

export function useLazyImage(src: string, placeholder?: string) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const img = new Image();
          img.src = src;
          img.onload = () => setLoaded(true);
          img.onerror = () => setError(true);
          observer.disconnect();
        }
      },
      { rootMargin: '200px' }
    );

    if (imgRef.current) observer.observe(imgRef.current);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  return { loaded, error, imgRef };
}

// ========== 组件可见性追踪 ==========

export function useVisibility(threshold = 0.1) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold }
    );

    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [threshold]);

  return { ref, visible };
}

// ========== 性能监控 ==========

export function usePerformanceMark(name: string) {
  useEffect(() => {
    performance.mark(`${name}-start`);
    return () => {
      performance.mark(`${name}-end`);
      performance.measure(name, `${name}-start`, `${name}-end`);
      const entries = performance.getEntriesByName(name);
      const duration = entries[entries.length - 1]?.duration;
      if (duration) {
        console.log(`[性能] ${name}: ${duration.toFixed(2)}ms`);
        if (duration > 100) {
          console.warn(`[性能] ⚠️ ${name} 耗时过长: ${duration.toFixed(2)}ms`);
        }
      }
      performance.clearMarks(`${name}-start`);
      performance.clearMarks(`${name}-end`);
      performance.clearMeasures(name);
    };
  }, [name]);
}

// ========== 防抖/节流 ==========

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

export function useThrottle<T extends (...args: any[]) => void>(
  fn: T,
  delay: number
): T {
  const lastCall = useRef(0);
  return useCallback(
    ((...args: any[]) => {
      const now = Date.now();
      if (now - lastCall.current >= delay) {
        lastCall.current = now;
        fn(...args);
      }
    }) as T,
    [fn, delay]
  );
}

// ========== 资源预加载 ==========

export function preloadImages(urls: string[]) {
  urls.forEach((url) => {
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'image';
    link.href = url;
    document.head.appendChild(link);
  });
}

export function preloadFonts(fonts: { url: string; type: string }[]) {
  fonts.forEach(({ url, type }) => {
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'font';
    link.href = url;
    link.type = type;
    link.crossOrigin = 'anonymous';
    document.head.appendChild(link);
  });
}

// ========== 首屏加载时间监控 ==========

export function reportFCP() {
  if ('performance' in window) {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name === 'first-contentful-paint') {
          console.log(`[性能] FCP: ${entry.startTime.toFixed(2)}ms`);
          // 上报到分析
          // sendMetric('fcp', entry.startTime);
        }
      }
    });
    observer.observe({ type: 'paint', buffered: true });
  }
}