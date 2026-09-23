/**
 * 法务页面的正文内容模型。
 *
 * 为什么不走 t()：条款正文是「章节 + 段落 + 列表」的文档结构，而不是零散 UI 文案；
 * 塞进 9 个 locale JSON 会把 30KB 文档复制 9 份。这里只在 zh / en 两份之间选择，
 * 与 useTranslation 的「当前语言 → 英文 fallback」行为一致：除中文外的所有语言读英文。
 */
import type { Locale } from '../config';

export type LegalBlock =
  | { k: 'p'; t: string; b?: string }
  | { k: 'ul'; items: Array<string | { b: string; t: string }> }
  /** 独立成段的联系邮箱，由渲染器用 t('legal.privacy.contactEmail') 取值 */
  | { k: 'email' }
  /** 指向官方参考页面的外链（如 Paddle 买家支持与消费者条款） */
  | { k: 'links'; items: Array<{ label: string; url: string }> };

export type LegalSection = {
  title: string;
  blocks: LegalBlock[];
};

export type LegalDoc = {
  intro?: string;
  sections: LegalSection[];
  closing?: string;
};

export type LegalDocPair = { zh: LegalDoc; en: LegalDoc };

export function pickLegalDoc(doc: LegalDocPair, locale: Locale): LegalDoc {
  return locale === 'zh' ? doc.zh : doc.en;
}
