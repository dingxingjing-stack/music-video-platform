import { useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useTranslation } from '../../i18n/useTranslation';

type SectionProps = {
  n: number;
  title: string;
  children: ReactNode;
  last?: boolean;
};

function Section({ n, title, children, last }: SectionProps) {
  return (
    <section className={`py-6 ${last ? '' : 'border-b border-[#2a2a2a]'}`}>
      <h2 className="text-xl font-semibold text-white mb-3">{n}. {title}</h2>
      {children}
    </section>
  );
}

const P = (k: string) => `legal.privacy.${k}`;

export function PrivacyPolicy() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const email = t(P('contactEmail'));

  const lead = (k: string) => (
    <p className="text-sm leading-relaxed text-[#b0b0b0]">{t(P(k))}</p>
  );
  const body = (k: string) => (
    <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">{t(P(k))}</p>
  );
  const list = (keys: string[]) => (
    <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
      {keys.map((k) => <li key={k}>{t(P(k))}</li>)}
    </ul>
  );

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-[#666666] hover:text-white transition mb-4 inline-block"
        >
          ← {t('common.back')}
        </button>
        <h1 className="text-3xl font-bold text-white mb-2">{t('legal.titlePrivacy')}</h1>
        <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <Section n={1} title={t(P('sec1Title'))}>{lead('sec1Body')}</Section>

        <Section n={2} title={t(P('sec2Title'))}>
          {lead('sec2Lead')}
          {list(['sec2i1', 'sec2i2', 'sec2i3'])}
          {body('sec2negLead')}
          {list(['sec2neg1'])}
        </Section>

        <Section n={3} title={t(P('sec3Title'))}>
          {lead('sec3Lead')}
          {list(['sec3i1', 'sec3i2', 'sec3i3', 'sec3i4'])}
        </Section>

        <Section n={4} title={t(P('sec4Title'))}>
          {lead('sec4Body')}
          {list(['sec4i1', 'sec4i2', 'sec4i3'])}
        </Section>

        <Section n={5} title={t(P('sec5Title'))}>
          {lead('sec5Lead')}
          {list(['sec5i1', 'sec5i2', 'sec5i3'])}
        </Section>

        <Section n={6} title={t(P('sec6Title'))}>
          {lead('sec6Lead')}
          {list(['sec6i1', 'sec6i2', 'sec6i3', 'sec6i4'])}
        </Section>

        <Section n={7} title={t(P('sec7Title'))}>{lead('sec7Body')}</Section>

        <Section n={8} title={t(P('sec8Title'))}>{lead('sec8Body')}</Section>

        <Section n={9} title={t(P('sec9Title'))} last>
          {lead('sec9Body')}
          <a
            href={`mailto:${email}`}
            className="inline-block mt-2 text-sm text-[#ff6a10] hover:underline"
          >
            {email}
          </a>
        </Section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">{t(P('footerNote'))}</p>
        </div>
      </div>
    </div>
  );
}
