import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../i18n/useTranslation';
import { pickLegalDoc } from '../../i18n/legal/types';
import { AUP_DOC } from '../../i18n/legal/aup';
import { LegalSections } from './LegalSections';

export function AcceptableUsePolicy() {
  const navigate = useNavigate();
  const { t, locale } = useTranslation();
  const doc = pickLegalDoc(AUP_DOC, locale);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-[#666666] hover:text-white transition mb-4 inline-block"
        >
          ← {t('common.back')}
        </button>
        <h1 className="text-3xl font-bold text-white mb-2">{t('legal.titleAup')}</h1>
        <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <LegalSections sections={doc.sections} />

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">{doc.closing}</p>
        </div>
      </div>
    </div>
  );
}
