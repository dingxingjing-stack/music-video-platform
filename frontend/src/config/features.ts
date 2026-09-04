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
  mureka_generate:   { key: 'mureka_generate',   name: 'features.murekaGenerate.name',   level: 'open',  description: 'features.murekaGenerate.desc', icon: '🎵' },
  lyrics_generate:   { key: 'lyrics_generate',   name: 'features.lyricsGenerate.name',   level: 'open',  description: 'features.lyricsGenerate.desc', icon: '✍️' },
  midi_basic:         { key: 'midi_basic',         name: 'features.midiBasic.name',       level: 'open',  description: 'features.midiBasic.desc', icon: '🎹' },
  tts:                { key: 'tts',                name: 'features.tts.name',             level: 'open',  description: 'features.tts.desc', icon: '🎤' },
  daw_edit:           { key: 'daw_edit',           name: 'features.dawEdit.name',         level: 'open',  description: 'features.dawEdit.desc', icon: '🎛️' },
  watermark:          { key: 'watermark',          name: 'features.watermark.name',       level: 'open',  description: 'features.watermark.desc', icon: '💧' },
  like_favorite:      { key: 'like_favorite',      name: 'features.likeFavorite.name',    level: 'open',  description: 'features.likeFavorite.desc', icon: '❤️' },
  basic_copyright:    { key: 'basic_copyright',    name: 'features.basicCopyright.name',  level: 'open',  description: 'features.basicCopyright.desc', icon: '🔒' },

  // ===== 灰度锁定（仅资深测试用户）=====
  voice_clone:        { key: 'voice_clone',        name: 'features.voiceClone.name',      level: 'open',  description: 'features.voiceClone.desc', icon: '🎙️' },
  ws_collab:          { key: 'ws_collab',          name: 'features.wsCollab.name',        level: 'gray',  description: 'features.wsCollab.desc', icon: '🤝' },
  hf_models:          { key: 'hf_models',          name: 'features.hfModels.name',        level: 'gray',  description: 'features.hfModels.desc', icon: '🧠' },
  subtitle:           { key: 'subtitle',           name: 'features.subtitle.name',        level: 'gray',  description: 'features.subtitle.desc', icon: '📝' },
  oneclick_publish:   { key: 'oneclick_publish',   name: 'features.oneclickPublish.name', level: 'gray',  description: 'features.oneclickPublish.desc', icon: '📢' },

  // ===== 完全关闭（隐藏入口）=====
  // mv_generate 已移除，改为声音克隆；保留兼容键但关闭
  mv_generate:        { key: 'mv_generate',        name: 'features.mvGenerate.name',      level: 'closed', description: 'features.mvGenerate.desc', icon: '🎬' },
  asset_store:        { key: 'asset_store',        name: 'features.assetStore.name',      level: 'closed', description: 'features.assetStore.desc', icon: '🛒' },
  paid_subscription:  { key: 'paid_subscription',  name: 'features.paidSubscription.name',level: 'closed', description: 'features.paidSubscription.desc', icon: '💳' },
  messaging:          { key: 'messaging',          name: 'features.messaging.name',       level: 'closed', description: 'features.messaging.desc', icon: '💬' },
  ugc_earnings:       { key: 'ugc_earnings',       name: 'features.ugcEarnings.name',     level: 'closed', description: 'features.ugcEarnings.desc', icon: '💰' },
  deep_copyright_db: { key: 'deep_copyright_db',  name: 'features.deepCopyrightDb.name',  level: 'closed', description: 'features.deepCopyrightDb.desc', icon: '📚' },
};

/** 全开放功能列表（导航用）*/
export const OPEN_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'open');

/** 灰度功能列表（导航用）*/
export const GRAY_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'gray');

/** 完全关闭功能列表（用于过滤路由）*/
export const CLOSED_FEATURES = Object.values(FEATURE_CONFIG).filter(f => f.level === 'closed');
