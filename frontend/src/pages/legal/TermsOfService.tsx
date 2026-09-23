import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../i18n/useTranslation';
import { pickLegalDoc } from '../../i18n/legal/types';
import { TERMS_DOC } from '../../i18n/legal/terms';
import { LegalSections } from './LegalSections';

export function TermsOfService() {
  const navigate = useNavigate();
  const { t, locale } = useTranslation();
  const doc = pickLegalDoc(TERMS_DOC, locale);

  return (
    <div className="min-h-screen bg-[#121212] text-[#e0e0e0] px-6 py-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <button
            onClick={() => navigate(-1)}
            className="text-sm text-[#888888] hover:text-white transition mb-4 inline-block border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-1 rounded"
          >
            ← {t('common.back')}
          </button>
          <h1 className="text-3xl font-black text-white mb-2">{t('legal.titleTerms')}</h1>
          <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
          <p className="text-sm text-[#888888]">{t('legal.effective')}</p>
          <p className="text-sm text-[#888888]">{t('legal.version')}</p>
        </div>

        <div className="bg-[#1e1e1e] border border-[#2a2a2a] rounded-lg p-6 mb-6">
          <p className="text-[15px] leading-relaxed text-[#e0e0e0]">{doc.intro}</p>
        </div>

        <div className="space-y-0">
          <LegalSections sections={doc.sections} />
        </div>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">{doc.closing}</p>
          <p className="text-xs text-[#666666] text-center mt-2">{t('legal.rights')}</p>
        </div>
      </div>
    </div>
  );
}

export default TermsOfService;
