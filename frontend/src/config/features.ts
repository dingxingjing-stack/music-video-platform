/**
 * 公测功能权限配置
 * 三级分类：全开放 / 灰度锁定 / 完全关闭
 */

export type FeatureLevel = 'open' | 'gray' | 'closed';

export interface FeatureConfig {
  key: string;
  name: string;
  level: FeatureLevel;
  description: string;
  icon: string;
}

export const FEATURE_CONFIG: Record<string, FeatureConfig> = {
  // ===== 全开放（公测无限制）=====
  mureka_generate:   { key: 'mureka_generate',   name: 'AI 作曲生成',   level: 'open',  description: 'Mureka API 一键生成歌曲', icon: '🎵' },
  lyrics_generate:   { key: 'lyrics_generate',   name: 'AI 歌词创作',   level: 'open',  description: 'AI 生成/续写歌词',         icon: '✍️' },
  midi_basic:         { key: 'midi_basic',         name: '基础 MIDI 编曲',level: 'open',  description: '钢琴卷帘编辑、基础编曲',   icon: '🎹' },
  tts:                { key: 'tts',                name: 'TTS 人声合成',  level: 'open',  description: '文字转语音人声合成',       icon: '🎤' },
  daw_edit:           { key: 'daw_edit',           name: 'DAW 剪辑',      level: 'open',  description: '多轨编辑、音频剪辑',       icon: '🎛️' },
  watermark:          { key: 'watermark',          name: '音频水印',      level: 'open',  description: '作品水印嵌入与提取',       icon: '💧' },
  like_favorite:      { key: 'like_favorite',      name: '点赞收藏',      level: 'open',  description: '社区点赞与收藏作品',       icon: '❤️' },
  basic_copyright:    { key: 'basic_copyright',    name: '基础版权检测',  level: 'open',  description: '基础音频指纹比对',         icon: '🔒' },

  // ===== 灰度锁定（仅资深测试用户）=====
  mv_generate:        { key: 'mv_generate',        name: 'MV 生成',       level: 'gray',  description: 'AI 音乐视频自动生成',     icon: '🎬' },
  ws_collab:          { key: 'ws_collab',          name: '实时协作编辑',  level: 'gray',  description: 'WebSocket 多人协作',     icon: '🤝' },
  hf_models:          { key: 'hf_models',          name: 'HF 第三方模型', level: 'gray',  description: 'HuggingFace 高级模型',   icon: '🧠' },
  subtitle:           { key: 'subtitle',           name: '字幕识别',      level: 'gray',  description: '自动语音识别字幕',         icon: '📝' },
  oneclick_publish:   { key: 'oneclick_publish',   name: '一键多平台发布',level: 'gray',  description: '多平台同步发布',           icon: '📢' },

  // ===== 完全关闭（隐藏入口）=====
  voice_clone:        { key: 'voice_clone',        name: '声音克隆',      level: 'closed',description: 'V1.1 之后开放',           icon: '🗣️' },
  asset_store:        { key: 'asset_store',        name: '素材商城',      level: 'closed',description: '公测暂不开放',           icon: '🛒' },
  paid_subscription:  { key: 'paid_subscription',  name: '付费订阅',      level: 'closed',description: '公测暂不开放',           icon: '💳' },
  messaging:          { key: 'messaging',          name: '私信聊天',      level: 'closed',description: '公测暂不开放',           icon: '💬' },
  ugc_earnings:       { key: 'ugc_earnings',       name: 'UGC 收益提现',  level: 'closed',description: '公测暂不开放',           icon: '💰' },
  deep_copyright_db: { key: 'deep_copyright_db',  name: '深度版权比对库',level: 'closed',description: '公测暂不开放',           icon: '📚' },
};

/** 全开放功能列表（导航用）*/
export const OPEN_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'open');

/** 灰度功能列表（导航用）*/
export const GRAY_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'gray');

/** 完全关闭功能列表（用于过滤路由）*/
export const CLOSED_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'closed');
