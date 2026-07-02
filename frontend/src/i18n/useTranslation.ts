'use client';

import { useState, useEffect } from 'react';
import { locales, defaultLocale, localeNames, type Locale } from './config';

export function useTranslation() {
  const [locale, setLocale] = useState<Locale>(defaultLocale);
  const [t, setT] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = localStorage.getItem('locale') as Locale | null;
    if (saved && locales.includes(saved)) {
      setLocale(saved);
    } else {
      const browserLang = navigator.language.split('-')[0] as Locale;
      if (locales.includes(browserLang)) {
        setLocale(browserLang);
        localStorage.setItem('locale', browserLang);
      }
    }
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

  const changeLocale = (newLocale: Locale) => {
    localStorage.setItem('locale', newLocale);
    setLocale(newLocale);
  };

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