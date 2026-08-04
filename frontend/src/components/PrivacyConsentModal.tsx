import React, { useEffect, useState } from 'react';

const CONSENT_COOKIE = 'consentVersion';
const CONSENT_VALUE = 'v2024-07';

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

export const PrivacyConsentModal: React.FC = () => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!getCookie(CONSENT_COOKIE)) {
      setVisible(true);
    }
  }, []);

  const accept = () => {
    setCookie(CONSENT_COOKIE, CONSENT_VALUE);
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/70 z-50 backdrop-blur-sm">
      <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f] p-6 max-w-md w-full shadow-2xl">
        <h2 className="text-lg font-semibold text-[#e0e0e0] mb-3" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          Privacy Policy
        </h2>
        <p className="text-sm text-[#b0b0b0] mb-5 leading-relaxed">
          We use cookies to record your consent to our privacy policy. Click "Accept" to indicate you have read and agreed to our privacy policy.
        </p>
        <button
          onClick={accept}
          className="w-full px-4 py-2.5 bg-[#ff6a10] text-white text-sm font-semibold rounded-lg
                     hover:bg-[#ff6a10] transition-colors"
          style={{ fontFamily: "'Space Grotesk', sans-serif" }}
        >
          Accept
        </button>
      </div>
    </div>
  );
};
