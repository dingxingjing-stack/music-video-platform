import React from 'react';
import { Button } from './Button';

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  compact,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${
        compact ? 'py-8' : 'py-16'
      } px-6 bg-[#14171b] border border-dashed border-[#23272e] rounded-[14px]`}
    >
      {icon && (
        <div className={`mb-4 text-[#6b7480] ${compact ? 'text-3xl' : 'text-5xl'} leading-none`}>
          {icon}
        </div>
      )}
      <h3 className="text-[15px] font-semibold text-[#e8eaed]">{title}</h3>
      {description && (
        <p className="mt-1.5 text-[13px] text-[#6b7480] max-w-sm">{description}</p>
      )}
      {actionLabel && onAction && (
        <div className="mt-5">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      )}
    </div>
  );
}

export function Skeleton({ width = '100%', height = 16, className = '' }: { width?: number | string; height?: number; className?: string }) {
  return (
    <div
      className={`bg-[#1a1e24] rounded-[6px] animate-pulse ${className}`}
      style={{ width, height }}
    />
  );
}

export function LoadingBlock({ label = '加载中…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="py-6 space-y-3" role="status">
      <p className="text-[13px] text-[#6b7480]">{label}</p>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={i === rows - 1 ? 20 : 64} />
      ))}
    </div>
  );
}