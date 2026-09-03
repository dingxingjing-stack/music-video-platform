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
  const [enT, setEnT] = useState<Record<string, any>>({});
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
        // 同时加载当前语言与英文，作为缺失 key 的 fallback
        const [locMod, enMod] = await Promise.all([
          import(`./locales/${locale}.json`),
          import('./locales/en.json'),
        ]);
        setT(locMod.default || locMod);
        setEnT(enMod.default || enMod);
      } catch {
        const fallback = await import('./locales/en.json');
        setT(fallback.default || fallback);
        setEnT(fallback.default || fallback);
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

  const lookup = (obj: Record<string, any>, key: string): string | undefined => {
    const keys = key.split('.');
    let value: any = obj;
    for (const k of keys) {
      value = value?.[k];
      if (value === undefined) break;
    }
    if (typeof value !== 'string') return undefined;
    return value;
  };

  const translate = (key: string, params?: Record<string, string | number>): string => {
    // 当前语言 → 英文 fallback → 返回 key
    let value = lookup(t, key);
    if (value === undefined && enT !== t) value = lookup(enT, key);
    if (value === undefined) return key;
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