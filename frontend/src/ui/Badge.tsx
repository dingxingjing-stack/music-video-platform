import React from 'react';

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

const toneMap: Record<Tone, string> = {
  neutral: 'bg-[#1a1e24] text-[#a3abb5] border-[#23272e]',
  accent: 'bg-[rgba(232,93,46,0.12)] text-[#ff7a45] border-[rgba(232,93,46,0.3)]',
  success: 'bg-[rgba(63,182,139,0.12)] text-[#4fce9f] border-[rgba(63,182,139,0.3)]',
  warning: 'bg-[rgba(229,162,62,0.12)] text-[#e5a23e] border-[rgba(229,162,62,0.3)]',
  danger: 'bg-[rgba(226,92,92,0.12)] text-[#e26c6c] border-[rgba(226,92,92,0.3)]',
  info: 'bg-[rgba(91,155,213,0.12)] text-[#6fb0e0] border-[rgba(91,155,213,0.3)]',
};

export function Badge({
  tone = 'neutral',
  children,
  dot,
  className = '',
}: {
  tone?: Tone;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] text-[12px] font-medium border ${toneMap[tone]} ${className}`}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}