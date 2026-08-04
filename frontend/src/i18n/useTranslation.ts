'use client';

import { useState, useEffect, useCallback } from 'react';
import { locales, defaultLocale, localeNames, type Locale } from './config';

const LOCALE_EVENT = 'app:locale-change';

function readStoredLocale(): Locale {
  const saved = localStorage.getItem('locale') as Locale | null;
  if (saved && locales.includes(saved)) return saved;
  const browserLang = navigator.language.split('-')[0] as Locale;
  if (locales.includes(browserLang)) {
    localStorage.setItem('locale', browserLang);
    return browserLang;
  }
  return defaultLocale;
}

export function useTranslation() {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);
  const [t, setT] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  // 全局监听语言切换事件（其他组件触发时同步本组件）
  useEffect(() => {
    const onLocaleChange = (e: Event) => {
      const newLocale = (e as CustomEvent<Locale>).detail;
      if (newLocale && locales.includes(newLocale)) {
        setLocaleState(newLocale);
      }
    };
    window.addEventListener(LOCALE_EVENT, onLocaleChange as EventListener);
    return () => window.removeEventListener(LOCALE_EVENT, onLocaleChange as EventListener);
  }, []);

  useEffect(() => {
    async function loadTranslations() {
      setLoading(true);
      try {
        const mod = await import(`./locales/${locale}.json`);
        setT(mod.default || mod);
      } catch {
        const fallback = await import('./locales/en.json');
        setT(fallback.default || fallback);
      }
      setLoading(false);
    }
    loadTranslations();
  }, [locale]);

  const changeLocale = useCallback((newLocale: Locale) => {
    localStorage.setItem('locale', newLocale);
    setLocaleState(newLocale);
    // 广播给所有 useTranslation 实例 — 实现全局实时切换
    window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: newLocale }));
  }, []);

  const translate = (key: string, params?: Record<string, string | number>): string => {
    const keys = key.split('.');
    let value: any = t;
    for (const k of keys) {
      value = value?.[k];
      if (value === undefined) break;
    }
    if (value === undefined) return key;
    if (typeof value !== 'string') return key;
    if (params) {
      return value.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? ''));
    }
    return value;
  };

  return {
    locale,
    locales,
    localeNames,
    t: translate,
    changeLocale,
    loading
  };
}