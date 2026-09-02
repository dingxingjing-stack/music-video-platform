import React from 'react';

const fieldBase =
  'w-full bg-[#14171b] border border-[#23272e] rounded-[10px] px-3.5 text-[14px] text-[#e8eaed] ' +
  'placeholder:text-[#6b7480] transition-colors duration-150 ' +
  'focus:outline-none focus:border-[#4f6272] focus:ring-2 focus:ring-[rgba(232,93,46,0.12)] ' +
  'disabled:opacity-45 disabled:cursor-not-allowed';

export function Input({
  label,
  hint,
  error,
  containerClassName,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: string;
  containerClassName?: string;
}) {
  return (
    <label className={`block ${containerClassName || ''}`}>
      {label && <span className="block mb-1.5 text-[13px] font-medium text-[#a3abb5]">{label}</span>}
      <input className={`${fieldBase} h-10 ${error ? 'border-[#e25c5c]' : ''}`} {...rest} />
      {error ? (
        <span className="mt-1 block text-[12px] text-[#e26c6c]">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-[12px] text-[#6b7480]">{hint}</span>
      ) : null}
    </label>
  );
}

export function TextArea({
  label,
  hint,
  error,
  containerClassName,
  ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: string;
  containerClassName?: string;
}) {
  return (
    <label className={`block ${containerClassName || ''}`}>
      {label && <span className="block mb-1.5 text-[13px] font-medium text-[#a3abb5]">{label}</span>}
      <textarea className={`${fieldBase} py-2.5 min-h-[80px] resize-y ${error ? 'border-[#e25c5c]' : ''}`} {...rest} />
      {error ? (
        <span className="mt-1 block text-[12px] text-[#e26c6c]">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-[12px] text-[#6b7480]">{hint}</span>
      ) : null}
    </label>
  );
}

export function Select({
  label,
  hint,
  containerClassName,
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  containerClassName?: string;
}) {
  return (
    <label className={`block ${containerClassName || ''}`}>
      {label && <span className="block mb-1.5 text-[13px] font-medium text-[#a3abb5]">{label}</span>}
      <select className={`${fieldBase} h-10 appearance-none pr-9 bg-no-repeat bg-[right_12px_center] bg-[url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='none' stroke='%236b7480' stroke-width='2' viewBox='0 0 24 24'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")]`} {...rest}>
        {children}
      </select>
      {hint && <span className="mt-1 block text-[12px] text-[#6b7480]">{hint}</span>}
    </label>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div>
      <span className="block mb-1.5 text-[13px] font-medium text-[#a3abb5]">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-[#6b7480]">{hint}</span>}
    </div>
  );
}