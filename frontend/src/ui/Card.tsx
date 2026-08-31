import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg';
  elevated?: boolean;
}

const padMap = {
  none: 'p-0',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

export function Card({ padding = 'md', elevated, className = '', children, ...rest }: CardProps) {
  return (
    <div
      className={`bg-[#14171b] border border-[#23272e] rounded-[14px] ${padMap[padding]} ${
        elevated ? 'shadow-[0_4px_12px_rgba(0,0,0,0.35)]' : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 pb-4 mb-4 border-b border-[#23272e]">
      <div>
        <h3 className="text-[17px] font-semibold text-[#e8eaed] leading-tight">{title}</h3>
        {subtitle && <p className="mt-1 text-[13px] text-[#6b7480]">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}