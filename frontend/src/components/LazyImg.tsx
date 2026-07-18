// 通用图片懒加载组件 — IntersectionObserver + 占位骨架
import { useEffect, useRef, useState, type ImgHTMLAttributes } from 'react';

interface Props extends ImgHTMLAttributes<HTMLImageElement> {
  src: string;
  alt: string;
  /** 占位背景色 */
  placeholder?: string;
  /** 根 margin，默认提前 100px 加载 */
  rootMargin?: string;
}

export function LazyImg({ src, alt, placeholder = '#1a1a1a', rootMargin = '100px', className = '', ...rest }: Props) {
  const ref = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) { setInView(true); io.disconnect(); }
      },
      { rootMargin }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);

  return (
    <div ref={ref} className={`relative overflow-hidden ${className}`} style={{ background: placeholder }}>
      {inView ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          className={`transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'} ${className}`}
          {...rest}
        />
      ) : (
        <div className="absolute inset-0 animate-pulse" style={{ background: placeholder }} />
      )}
    </div>
  );
}
