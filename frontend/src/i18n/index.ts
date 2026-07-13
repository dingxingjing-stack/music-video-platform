/**
 * 国际化 (i18n) 工具
 * 
 * 使用方式:
 * import { t, setLanguage, useTranslation } from '@/i18n';
 * 
 * t('common.appName') // 获取翻译
 * setLanguage('ja-JP') // 切换语言
 * useTranslation() // React Hook
 */

import { useState, useEffect, useCallback } from 'react';
import type { Language, Translation } from './types';
import translations from './translations';

let currentLanguage: Language = 'zh-CN';

/**
 * 设置当前语言
 */
export function setLanguage(lang: Language): void {
  currentLanguage = lang;
  localStorage.setItem('preferred-language', lang);
  document.documentElement.lang = lang;
}

/**
 * 获取当前语言
 */
export function getLanguage(): Language {
  return currentLanguage;
}

/**
 * 初始化语言 (从 localStorage 或浏览器设置)
 */
export function initLanguage(): void {
  const saved = localStorage.getItem('preferred-language') as Language;
  if (saved && translations[saved]) {
    currentLanguage = saved;
  } else {
    // 自动检测浏览器语言
    const browserLang = navigator.language;
    if (browserLang.startsWith('ja')) {
      currentLanguage = 'ja-JP';
    } else if (browserLang.startsWith('ko')) {
      currentLanguage = 'ko-KR';
    } else if (browserLang.startsWith('es')) {
      currentLanguage = 'es-ES';
    } else if (browserLang.startsWith('fr')) {
      currentLanguage = 'fr-FR';
    } else if (browserLang.startsWith('en')) {
      currentLanguage = 'en-US';
    } else {
      currentLanguage = 'zh-CN';
    }
  }
  document.documentElement.lang = currentLanguage;
}

/**
 * 获取翻译文本
 * 
 * @param key 翻译键，如 'common.appName'
 * @param params 可选的参数替换
 * @returns 翻译后的文本
 */
export function t(key: string, params?: Record<string, string>): string {
  const keys = key.split('.');
  let value: any = translations[currentLanguage];
  
  for (const k of keys) {
    if (value && typeof value === 'object' && k in value) {
      value = value[k];
    } else {
      // 找不到翻译，返回 key 本身或英文备用
      console.warn(`Translation not found: ${key}`);
      return key;
    }
  }
  
  if (typeof value === 'string') {
    // 参数替换 {name} -> value
    if (params) {
      Object.keys(params).forEach(paramKey => {
        value = value.replace(`{${paramKey}}`, params[paramKey]);
      });
    }
    return value;
  }
  
  return key;
}

/**
 * 获取所有支持的语言
 */
export function getSupportedLanguages(): Array<{code: Language; name: string; flag: string}> {
  return [
    { code: 'zh-CN', name: '简体中文', flag: '🇨🇳' },
    { code: 'ja-JP', name: '日本語', flag: '🇯🇵' },
    { code: 'ko-KR', name: '한국어', flag: '🇰🇷' },
    { code: 'es-ES', name: 'Español', flag: '🇪🇸' },
    { code: 'fr-FR', name: 'Français', flag: '🇫🇷' },
    { code: 'en-US', name: 'English', flag: '🇺🇸' },
  ];
}

/**
 * 语言切换组件 (React)
 */
export function LanguageSwitcher() {
  // 这个函数需要在 React 组件中使用
  // 示例：
  // import { LanguageSwitcher } from '@/i18n';
  // <LanguageSwitcher />
  return null;
}

/**
 * React Hook for using translations
 * 
 * @returns {t: (key: string, params?: Record<string, string>) => string, language: Language, setLanguage: (lang: Language) => void}
 * 
 * @example
 * const { t, language, setLanguage } = useTranslation();
 * <h1>{t('common.appName')}</h1>
 * <button onClick={() => setLanguage('en-US')}>English</button>
 */
export function useTranslation() {
  const [language, setLanguageState] = useState<Language>(currentLanguage);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    setLanguage(lang);
  }, []);

  return {
    t,
    language,
    setLanguage,
  };
}

export default {
  t,
  setLanguage,
  getLanguage,
  initLanguage,
  getSupportedLanguages,
  useTranslation,
};