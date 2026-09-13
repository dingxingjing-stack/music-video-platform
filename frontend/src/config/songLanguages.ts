/**
 * 歌曲语言配置 —— 独立于 UI i18n locale。
 *
 * 目的：把「网站界面语言」与「歌曲生成语言」彻底分离。
 * - UI locale 只有 9 个（见 i18n/config.ts），负责菜单/按钮/设置/提示等界面文案。
 * - Song Language 负责告诉音乐生成 API：生成的歌曲/歌词应该用什么语言。
 * - 二者可任意组合（如：UI=中文 + Song Language=Spanish）。
 *
 * 语言列表来源（不自行猜测）：
 *   天谱乐 TemPolor 官方文档明确列出支持的语言：
 *   中文、粤语、英、日、韩、俄、西、德、法、意、葡（官方原文“35+ 语言，包含…”）。
 *   官方未逐一列出“更多”语种，故此处只收录官方明确列出的 11 种；
 *   后续若 Provider 官方明确新增其他语种，再在此追加，绝不上探到 30+ 个 UI locale。
 *
 * code 为稳定内部标识，供 song_language 字段透传；
 * 各 Provider 在自身层做 code -> 该 Provider 实际要求的映射（见各 *_provider.py），
 * 不污染前端 i18n。
 */

export interface SongLanguage {
  /** 稳定内部代码（如 'es'） */
  code: string;
  /** 英文名称 */
  name: string;
  /** 本地名称 */
  nativeName: string;
}

export const SONG_LANGUAGES: SongLanguage[] = [
  { code: 'zh', name: 'Chinese', nativeName: '中文' },
  { code: 'yue', name: 'Cantonese', nativeName: '粤语' },
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語' },
  { code: 'ko', name: 'Korean', nativeName: '한국어' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
];

/** 根据 code 取语言对象；未知 code 返回 undefined（调用方决定回退）。 */
export function getSongLanguage(code: string | null | undefined): SongLanguage | undefined {
  if (!code) return undefined;
  return SONG_LANGUAGES.find((l) => l.code === code);
}

/** 把歌曲语言 code 映射为该语言在 prompt 中的英文指令名（供 TemPolor 等无 language 参数的 Provider 拼接）。 */
export function songLanguagePromptName(code: string | null | undefined): string | undefined {
  return getSongLanguage(code)?.name;
}

export default SONG_LANGUAGES;