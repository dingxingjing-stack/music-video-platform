import type { LegalBlock, LegalSection } from '../../i18n/legal/types';
import { useTranslation } from '../../i18n/useTranslation';

function Block({ block, first }: { block: LegalBlock; first: boolean }) {
  const { t } = useTranslation();
  const gap = first ? '' : 'mt-2';
  if (block.k === 'email') {
    const email = t('legal.privacy.contactEmail');
    return (
      <a
        href={`mailto:${email}`}
        className={`inline-block text-sm text-[#ff6a10] hover:underline ${gap}`}
      >
        {email}
      </a>
    );
  }
  if (block.k === 'links') {
    return (
      <p className={`text-sm leading-relaxed text-[#b0b0b0] ${gap}`}>
        {block.items.map((item, i) => (
          <a
            key={item.url}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`text-[#ff6a10] hover:underline break-words ${i > 0 ? 'ml-4' : ''}`}
          >
            {item.label}
          </a>
        ))}
      </p>
    );
  }
  if (block.k === 'ul') {
    return (
      <ul className={`list-disc list-inside space-y-1 text-sm text-[#b0b0b0] ${gap}`}>
        {block.items.map((item, i) => (
          <li key={i}>
            {typeof item === 'string'
              ? item
              : (<><strong className="text-white">{item.b}</strong>{item.t}</>)}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className={`text-sm leading-relaxed text-[#b0b0b0] ${gap}`}>
      {block.b && <strong className="text-white">{block.b}</strong>}
      {block.t}
    </p>
  );
}

/** 章节渲染：沿用各法务页原有的 class 与间距，最后一节不带下边框。 */
export function LegalSections({ sections }: { sections: LegalSection[] }) {
  return (
    <>
      {sections.map((section, i) => (
        <section
          key={i}
          className={`py-6 ${i === sections.length - 1 ? '' : 'border-b border-[#2a2a2a]'}`}
        >
          <h2 className="text-xl font-semibold text-white mb-3">{section.title}</h2>
          {section.blocks.map((block, j) => (
            <Block key={j} block={block} first={j === 0} />
          ))}
        </section>
      ))}
    </>
  );
}
