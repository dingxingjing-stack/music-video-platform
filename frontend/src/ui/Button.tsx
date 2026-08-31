import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: React.ReactNode;
  loading?: boolean;
  block?: boolean;
}

const base =
  'inline-flex items-center justify-center gap-2 font-medium rounded-[10px] ' +
  'transition-all duration-150 ease-out focus:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-[rgba(232,93,46,0.4)] disabled:opacity-45 disabled:cursor-not-allowed select-none';

const variants: Record<Variant, string> = {
  primary:
    'bg-[#e85d2e] text-white hover:bg-[#ee6d3f] active:bg-[#d14f22] shadow-[0_1px_2px_rgba(0,0,0,0.3)]',
  secondary:
    'bg-[#1a1e24] text-[#e8eaed] border border-[#23272e] hover:bg-[#20252c] hover:border-[#2d333b]',
  ghost:
    'bg-transparent text-[#a3abb5] hover:bg-[#1a1e24] hover:text-[#e8eaed]',
  outline:
    'bg-transparent text-[#e8eaed] border border-[#2d333b] hover:border-[#4f6272] hover:bg-[#14171b]',
  danger:
    'bg-[#e25c5c] text-white hover:bg-[#d94b4b]',
};

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px]',
  md: 'h-10 px-4 text-[14px]',
  lg: 'h-11 px-6 text-[15px]',
};

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading,
  block,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`${base} ${variants[variant]} ${sizes[size]} ${block ? 'w-full' : ''} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <Spinner size={14} />
      ) : icon ? (
        <span className="inline-flex shrink-0 text-[1em] leading-none">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}

export function Spinner({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      className={`animate-spin inline-block shrink-0 ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}