/**
 * 国际化和多语言配置
 * 
 * P1-3: 支持 6 种语言
 * - zh-CN: 简体中文
 * - ja-JP: 日语
 * - ko-KR: 韩语
 * - es-ES: 西班牙语
 * - fr-FR: 法语
 * - en-US: 英语 (备用)
 */

export type Language = 
  | 'zh-CN'  // 简体中文
  | 'en-US'  // 英语
  | 'ja-JP'  // 日语
  | 'ko-KR'  // 韩语
  | 'es-ES'  // 西班牙语
  | 'fr-FR'  // 法语
  | 'de-DE'  // 德语 (P3-3 新增)
  | 'it-IT'  // 意大利语 (P3-3 新增)
  | 'pt-BR'  // 葡萄牙语 (P3-3 新增)
  | 'ru-RU'  // 俄语 (P3-3 新增)
  | 'hi-IN'  // 印地语 (P3-3 新增)
  | 'th-TH'  // 泰语 (P3-3 新增)
  | 'vi-VN'  // 越南语 (P3-3 新增)
  | 'id-ID'  // 印尼语 (P3-3 新增)
  ;

export interface Translation {
  common: {
    appName: string;
    generate: string;
    upload: string;
    download: string;
    save: string;
    delete: string;
    edit: string;
    cancel: string;
    confirm: string;
    submit: string;
    preview: string;
    loading: string;
    success: string;
    error: string;
    warning: string;
  };
  
  aiMusic: {
    generateTitle: string;
    styleLabel: string;
    moodLabel: string;
    vocalTypeLabel: string;
    durationLabel: string;
    lyricsLabel: string;
    generateButton: string;
    generating: string;
    downloadAudio: string;
    regenerate: string;
  };
  
  mvGeneration: {
    templateTitle: string;
    selectTemplate: string;
    uploadVideo: string;
    generateMV: string;
    generating: string;
    downloadVideo: string;
  };
  
  studio: {
    multiTrack: string;
    trackStudio: string;
    midiEditor: string;
    mixConsole: string;
    effects: string;
    export: string;
  };
  
  community: {
    discover: string;
    profile: string;
    notifications: string;
    messages: string;
  };
  
  errors: {
    apiError: string;
    networkError: string;
    invalidInput: string;
    fileTooLarge: string;
    unsupportedFormat: string;
    insufficientCredits: string;
  };
  
  // 音乐风格翻译
  musicStyles: Record<string, string>;
  
  // 情绪标签翻译
  moods: Record<string, string>;
  
  // 乐器翻译
  instruments: Record<string, string>;
}