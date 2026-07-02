export const locales = ['zh', 'en', 'ja', 'ko', 'es', 'fr', 'pt', 'ru', 'de'] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = 'zh';

export const localeNames: Record<Locale, string> = {
  zh: '中文',
  en: 'English',
  ja: '日本語',
  ko: '한국어',
  es: 'Español',
  fr: 'Français',
  pt: 'Português',
  ru: 'Русский',
  de: 'Deutsch'
};

export function getDefaultLocale(): Locale {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('locale') as Locale | null;
    if (saved && locales.includes(saved)) {
      return saved;
    }
    const browserLang = navigator.language.split('-')[0] as Locale;
    if (locales.includes(browserLang)) {
      return browserLang;
    }
  }
  return defaultLocale;
}