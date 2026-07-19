/** 全局语言切换组件 v2 */
import { useState, useEffect } from 'react';
import { useTranslation } from '../i18n/useTranslation';

const LANGUAGES = [
  { code: 'zh-CN', name: '中文', flag: '🇨🇳' },
  { code: 'en', name: 'English', flag: '🇺🇸' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
  { code: 'ko', name: '한국어', flag: '🇰🇷' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'pt', name: 'Português', flag: '🇵🇹' },
  { code: 'ru', name: 'Русский', flag: '🇷🇺' },
];

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const { setLocale, locale, t } = useTranslation();
  const [currentLang, setCurrentLang] = useState('zh-CN');

  useEffect(() => {
    const saved = localStorage.getItem('locale');
    if (saved && LANGUAGES.find(l => l.code === saved)) {
      setCurrentLang(saved);
    } else {
      // 使用 useTranslation 的 locale 状态，而不是重复读取 localStorage
      setCurrentLang(locale);
    }
  }, [locale]);

  const handleSwitch = (code: string) => {
    setCurrentLang(code);
    setLocale(code);
    setIsOpen(false);
  };

  const current = LANGUAGES.find(l => l.code === currentLang) || LANGUAGES[0];

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-[#2a2a2a] hover:bg-[#333] rounded-lg text-sm text-[#e0e0e0] transition border border-[#3a3a3a]"
      >
        <span className="text-lg">{current.flag}</span>
        <span className="text-xs">{current.name}</span>
        <svg className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-48 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg shadow-lg z-50 overflow-hidden">
          {LANGUAGES.map(lang => (
            <button
              key={lang.code}
              onClick={() => handleSwitch(lang.code)}
              className={`w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[#2a2a2a] transition ${lang.code === currentLang ? 'bg-[#2a2a2a]' : ''}`}
            >
              <span className="text-lg">{lang.flag}</span>
              <span className="text-sm text-[#e0e0e0]">{lang.name}</span>
              {lang.code === currentLang && (
                <svg className="w-4 h-4 ml-auto text-orange-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}