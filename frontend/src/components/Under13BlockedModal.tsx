import React, { useEffect, useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';

const UNDER_13_COOKIE = 'user_age_consent';
const CONSENT_VALUE = 'verified';

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string, days = 365) {
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  const expires = 'expires=' + d.toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)};${expires};path=/`;
}

export const Under13BlockedModal: React.FC = () => {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!getCookie(UNDER_13_COOKIE)) {
      setVisible(true);
    }
  }, []);

  const accept = () => {
    setCookie(UNDER_13_COOKIE, CONSENT_VALUE);
    setVisible(false);
  };

  if (visible) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div className="bg-white rounded-xl p-8 max-w-md w-full box-shadow-lg">
          <h2 className="text-xl font-bold text-gray-900 mb-4">{t('ageVerify.title')}</h2>
          <p className="text-gray-600 mb-6">
            {t('ageVerify.body')}
          </p>
          <button
            onClick={accept}
            className="w-full py-3 px-4 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            {t('ageVerify.continue')}
          </button>
          <button
            onClick={accept}
            className="w-full py-3 px-4 mt-4 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            {t('ageVerify.exit')}
          </button>
        </div>
      </div>
    );
  }

  return null;
};