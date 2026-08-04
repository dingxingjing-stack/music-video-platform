/** 全局语言切换组件 v2 */
import { useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';

const LANGUAGES = [
  { code: 'zh', name: '中文', flag: '🇨🇳' },
  { code: 'en', name: 'English', flag: '🇺🇸' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
  { code: 'ko', name: '한국어', flag: '🇰🇷' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'pt', name: 'Português', flag: '🇵🇹' },
  { code: 'ru', name: 'Русский', flag: '🇷🇺' },
] as const;

// 防御性兜底：旧 i18n/index 误用同名 useTranslation 会导致 changeLocale 为 undefined，
// 这里提前校验并抛明显错误，便于排查。
import { locales } from '../i18n/config';

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const tr = useTranslation();
  const changeLocale = tr.changeLocale;
  const currentLang = tr.locale;

  if (typeof changeLocale !== 'function') {
    // 排错直报·不渲染，避免静默吞错
    console.error('[LanguageSwitcher] useTranslation.changeLocale 未定义，请检查 i18n/useTranslation 是否被 i18n/index 同名导出覆盖');
    return null;
  }

  const handleSwitch = (code: string) => {
    if (!locales.includes(code as any)) return;
    changeLocale(code as any);
    setIsOpen(false);
  };

  const current = LANGUAGES.find(l => l.code === currentLang) || LANGUAGES[0];

  return (
    <div className={`relative inline-block ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-[#2a2a2a] hover:bg-[#333] rounded-lg text-sm text-[#e0e0e0] transition border border-[#3a3a3a] w-full"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="text-lg">{current.flag}</span>
        <span className="text-xs flex-1 text-left">{current.name}</span>
        <svg className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          {/* 点击外部关闭 */}
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-hidden
            onClick={() => setIsOpen(false)}
          />
          <div
            role="listbox"
            className="absolute bottom-full left-0 mb-2 w-56 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg shadow-2xl z-[60] overflow-hidden max-h-[60vh] overflow-y-auto"
          >
            {LANGUAGES.map(lang => (
              <button
                key={lang.code}
                type="button"
                onClick={() => handleSwitch(lang.code)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[#2a2a2a] transition ${lang.code === currentLang ? 'bg-[#2a2a2a]' : ''}`}
              >
                <span className="text-lg">{lang.flag}</span>
                <span className="text-sm text-[#e0e0e0] flex-1">{lang.name}</span>
                {lang.code === currentLang && (
                  <svg className="w-4 h-4 ml-auto text-orange-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}