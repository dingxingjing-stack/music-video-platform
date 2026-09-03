import React, { useEffect } from 'react';
import { Button } from './Button';
import { useTranslation } from '../i18n/useTranslation';

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  closeOnBackdrop = true,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnBackdrop?: boolean;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  const sizes = {
    sm: 'max-w-sm',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(10,12,15,0.72)] backdrop-blur-sm"
      onMouseDown={(e) => {
        if (closeOnBackdrop && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`w-full ${sizes[size]} max-h-[90vh] flex flex-col bg-[#14171b] border border-[#23272e] rounded-[14px] shadow-[0_12px_32px_rgba(0,0,0,0.45)]`}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between px-6 py-4 border-b border-[#23272e]">
          <div>
            <h2 className="text-[17px] font-semibold text-[#e8eaed]">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[13px] text-[#6b7480]">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label={t('ui.close')}
            className="ml-4 text-[#6b7480] hover:text-[#e8eaed] transition-colors p-1 rounded-[6px] hover:bg-[#1a1e24]"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5 overflow-y-auto flex-1">{children}</div>
        {footer && (
          <div className="px-6 py-4 border-t border-[#23272e] bg-[#14171b]">{footer}</div>
        )}
      </div>
    </div>
  );
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel,
  cancelLabel,
  tone = 'danger',
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'primary' | 'danger';
}) {
  const { t } = useTranslation();
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{cancelLabel || t('ui.cancel')}</Button>
          <Button variant={tone} onClick={onConfirm}>{confirmLabel || t('ui.confirm')}</Button>
        </div>
      }
    >
      <p className="text-[14px] text-[#a3abb5] leading-relaxed">{message}</p>
    </Modal>
  );
}