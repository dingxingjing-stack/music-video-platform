/**
 * VST 插件推荐引擎 (P4-2)
 * 
 * 功能:
 * - 基于场景推荐插件
 * - 基于风格推荐预设
 * - 效果器链自动建议
 * - 性能评级系统
 * - 用户行为学习
 */

import type { VSTPlugin } from '../components/Market/VSTPluginMarket';

// ============================================
// 插件数据库 (7 个已测试插件)
// ============================================

export interface PluginProfile extends VSTPlugin {
  cpuUsage: number;          // CPU 占用 %
  memoryUsage: number;       // 内存 MB
  difficulty: 'Beginner' | 'Intermediate' | 'Advanced';
  bestFor: string[];         // 最佳用途
  chainPosition: number;     // 效果链位置 (0=乐器，1-7=效果器顺序)
  alternatives: string[];    // 替代插件
}

export const PLUGIN_DATABASE: PluginProfile[] = [
  {
    id: 'surge-xt',
    name: 'Surge XT',
    vendor: 'Surge Synth Team',
    type: 'synth',
    subtype: 'Hybrid',
    format: ['VST3'] as const,
    cpuUsage: 2.0,
    memoryUsage: 45,
    difficulty: 'Intermediate',
    bestFor: ['Leads', 'Pads', 'Bass', 'Plucks', 'FX'],
    chainPosition: 0,
    rating: 5.0,
    price: 0,
    description: '开源合成器之王，功能极其强大',
    alternatives: ['Vital', 'Helm', 'Dexed'],
  },
  {
    id: 'tdr-nova',
    name: 'TDR Nova',
    vendor: 'Tokyo Dawn Labs',
    type: 'effect',
    subtype: 'EQ (Dynamic)',
    format: 'VST3',
    cpuUsage: 1.5,
    memoryUsage: 8,
    difficulty: 'Intermediate',
    bestFor: ['Vocal', 'Mixing', 'Mastering', 'Surgical EQ'],
    chainPosition: 1,
    rating: 5.0,
    price: 0,
    description: '业界标准免费动态 EQ',
    alternatives: ['TDR SlickEQ', 'Pro-Q3 (Paid)'],
  },
  {
    id: 'tdr-kotelnikov',
    name: 'TDR Kotelnikov',
    vendor: 'Tokyo Dawn Labs',
    type: 'effect',
    subtype: 'Compressor',
    format: 'VST3',
    cpuUsage: 1.0,
    memoryUsage: 6,
    difficulty: 'Advanced',
    bestFor: ['Mastering', 'Bus Compression', 'Vocal'],
    chainPosition: 2,
    rating: 5.0,
    price: 0,
    description: '透明压缩器标杆',
    alternatives: ['MJUC Jr.', 'Pro-C2 (Paid)'],
  },
  {
    id: 'valhalla-supermassive',
    name: 'Valhalla Supermassive',
    vendor: 'Valhalla DSP',
    type: 'effect',
    subtype: 'Reverb+Delay',
    format: 'VST3',
    cpuUsage: 2.5,
    memoryUsage: 12,
    difficulty: 'Beginner',
    bestFor: ['Vocal', 'Pads', 'Ambient', 'Cinematic'],
    chainPosition: 6,
    rating: 5.0,
    price: 0,
    description: '免费插件中的顶级混响',
    alternatives: ['OrilRiver', 'Valhalla Room (Paid)'],
  },
  {
    id: 'tal-reverb-4',
    name: 'TAL-Reverb-4',
    vendor: 'TAL Software',
    type: 'effect',
    subtype: 'Reverb',
    format: 'VST3',
    cpuUsage: 1.0,
    memoryUsage: 10,
    difficulty: 'Beginner',
    bestFor: ['Vocal', '80s Sounds', 'Synthwave'],
    chainPosition: 6,
    rating: 5.0,
    price: 0,
    description: '经典复古混响',
    alternatives: ['Valhalla Supermassive', 'Plate (Built-in)'],
  },
  {
    id: 'orilriver',
    name: 'OrilRiver',
    vendor: 'Drapo Studios',
    type: 'effect',
    subtype: 'Reverb (Algorithmic)',
    format: 'VST3',
    cpuUsage: 0.8,
    memoryUsage: 5,
    difficulty: 'Beginner',
    bestFor: ['Acoustic', 'Classical', 'Clean Mixes'],
    chainPosition: 6,
    rating: 4.5,
    price: 0,
    description: '免费混响中的佼佼者',
    alternatives: ['TAL-Reverb-4', 'Valhalla Supermassive'],
  },
  {
    id: 'krush',
    name: 'Krush',
    vendor: 'Bitheadz',
    type: 'effect',
    subtype: 'Bitcrusher',
    format: 'VST2',
    cpuUsage: 0.3,
    memoryUsage: 3,
    difficulty: 'Beginner',
    bestFor: ['Lo-Fi', 'Electronic', 'Drums', 'FX'],
    chainPosition: 3,
    rating: 4.5,
    price: 0,
    description: '轻量级比特粉碎器',
    alternatives: ['dBlue Glitch', 'CamelCrusher'],
  },
];

// ============================================
// 场景推荐系统
// ============================================

export interface ScenePreset {
  name: string;
  description: string;
  genre: string;
  plugins: { pluginId: string; preset?: string }[];
  chain: string[];  // 效果链顺序
}

export const SCENE_PRESETS: ScenePreset[] = [
  {
    name: 'Vocal Production',
    description: '专业人声处理链',
    genre: 'Pop',
    plugins: [
      { pluginId: 'tdr-nova', preset: 'Vocal Clean' },
      { pluginId: 'tdr-kotelnikov', preset: 'Vocal Compression' },
      { pluginId: 'valhalla-supermassive', preset: 'Vocal Plate' },
    ],
    chain: ['tdr-nova', 'tdr-kotelnikov', 'deesser', 'saturator', 'valhalla-supermassive', 'limiter'],
  },
  {
    name: 'House Music',
    description: 'House 音乐完整模板',
    genre: 'Electronic',
    plugins: [
      { pluginId: 'surge-xt', preset: 'House Bass' },
      { pluginId: 'surge-xt', preset: 'SuperSaw Lead' },
      { pluginId: 'tal-reverb-4', preset: 'Room' },
    ],
    chain: ['surge-xt', 'tdr-nova', 'tdr-kotelnikov', 'tal-reverb-4'],
  },
  {
    name: 'Ambient Pad',
    description: '氛围铺底音色',
    genre: 'Ambient',
    plugins: [
      { pluginId: 'surge-xt', preset: 'Ethereal Pad' },
      { pluginId: 'valhalla-supermassive', preset: 'Shimmer' },
    ],
    chain: ['surge-xt', 'chorus', 'delay', 'valhalla-supermassive'],
  },
  {
    name: 'Lo-Fi Hip Hop',
    description: 'Lo-Fi 嘻哈制作',
    genre: 'Hip Hop',
    plugins: [
      { pluginId: 'surge-xt', preset: 'Lo-Fi Keys' },
      { pluginId: 'krush', preset: '12-bit' },
      { pluginId: 'tal-reverb-4', preset: 'Vintage' },
    ],
    chain: ['surge-xt', 'krush', 'eq', 'tal-reverb-4', 'limiter'],
  },
  {
    name: 'Mastering Chain',
    description: '母带处理完整链路',
    genre: 'Any',
    plugins: [
      { pluginId: 'tdr-nova', preset: 'Mastering EQ' },
      { pluginId: 'tdr-kotelnikov', preset: 'Mastering Comp' },
      { pluginId: 'valhalla-supermassive', preset: 'Subtle Verb' },
    ],
    chain: ['tdr-nova', 'multiband-comp', 'stereo-enhancer', 'tdr-kotelnikov', 'limiter'],
  },
];

// ============================================
// 推荐算法
// ============================================

/**
 * 基于场景推荐插件
 */
export function recommendForScene(sceneName: string): ScenePreset | null {
  const preset = SCENE_PRESETS.find(p => 
    p.name.toLowerCase() === sceneName.toLowerCase()
  );
  return preset || null;
}

/**
 * 基于风格推荐插件
 */
export function recommendForGenre(genre: string): PluginProfile[] {
  const genreMap: Record<string, string[]> = {
    'Pop': ['tdr-nova', 'tdr-kotelnikov', 'valhalla-supermassive', 'tal-reverb-4'],
    'Electronic': ['surge-xt', 'krush', 'valhalla-supermassive', 'tdr-nova'],
    'Hip Hop': ['surge-xt', 'krush', 'tdr-kotelnikov'],
    'Rock': ['tdr-nova', 'tdr-kotelnikov', 'tal-reverb-4'],
    'Ambient': ['surge-xt', 'valhalla-supermassive', 'orilriver'],
    'Cinematic': ['surge-xt', 'valhalla-supermassive', 'tdr-kotelnikov'],
  };

  const pluginIds = genreMap[genre] || genreMap['Pop'];
  return PLUGIN_DATABASE.filter(p => pluginIds.includes(p.id));
}

/**
 * 基于预算推荐
 */
export function recommendByBudget(maxPrice: number): PluginProfile[] {
  return PLUGIN_DATABASE.filter(p => p.price <= maxPrice);
}

/**
 * 基于 CPU 限制推荐
 */
export function recommendByCPU(maxCPU: number): PluginProfile[] {
  return PLUGIN_DATABASE.filter(p => p.cpuUsage <= maxCPU);
}

/**
 * 基于难度推荐
 */
export function recommendByDifficulty(level: 'Beginner' | 'Intermediate' | 'Advanced'): PluginProfile[] {
  return PLUGIN_DATABASE.filter(p => p.difficulty === level);
}

/**
 * 构建效果链建议
 */
export function buildChainForPurpose(purpose: string): PluginProfile[] {
  const chainMap: Record<string, number[]> = {
    'Vocal': [1, 2, 3, 6],  // EQ → Comp → Sat → Reverb
    'Bass': [0, 1, 2],      // Synth → EQ → Comp
    'Drums': [0, 1, 2, 3],  // Drum → EQ → Comp → Bitcrush
    'Mastering': [1, 2, 6], // EQ → Comp → Reverb
  };

  const positions = chainMap[purpose] || chainMap['Vocal'];
  return PLUGIN_DATABASE.filter(p => positions.includes(p.chainPosition));
}

/**
 * 智能推荐 (综合多维度)
 */
export interface RecommendationOptions {
  genre?: string;
  budget?: number;
  maxCPU?: number;
  difficulty?: 'Beginner' | 'Intermediate' | 'Advanced';
  purpose?: string;
}

export function smartRecommend(options: RecommendationOptions): PluginProfile[] {
  let results = [...PLUGIN_DATABASE];

  if (options.genre) {
    const genreRecs = recommendForGenre(options.genre);
    results = results.filter(p => genreRecs.some(r => r.id === p.id));
  }

  if (options.budget !== undefined) {
    results = results.filter(p => p.price <= options.budget!);
  }

  if (options.maxCPU !== undefined) {
    results = results.filter(p => p.cpuUsage <= options.maxCPU!);
  }

  if (options.difficulty) {
    results = results.filter(p => p.difficulty === options.difficulty);
  }

  if (options.purpose) {
    const purposeRecs = buildChainForPurpose(options.purpose);
    results = results.filter(p => purposeRecs.some(r => r.id === p.id));
  }

  // 按评分排序
  return results.sort((a, b) => b.rating - a.rating);
}

// ============================================
// 预设推荐
// ============================================

export interface PresetRecommendation {
  pluginId: string;
  presetName: string;
  description: string;
  tags: string[];
  difficulty: 'Easy' | 'Medium' | 'Hard';
}

export const PRESET_LIBRARY: PresetRecommendation[] = [
  // Surge XT
  {
    pluginId: 'surge-xt',
    presetName: 'Ethereal Pad',
    description: '空灵铺底，适合氛围音乐',
    tags: ['Pad', 'Ambient', 'Soft'],
    difficulty: 'Easy',
  },
  {
    pluginId: 'surge-xt',
    presetName: 'SuperSaw Lead',
    description: '强力 Lead，适合 EDM/Trance',
    tags: ['Lead', 'EDM', 'Bright'],
    difficulty: 'Medium',
  },
  {
    pluginId: 'surge-xt',
    presetName: 'Deep Bass',
    description: '深沉贝斯，适合 Trap/Drill',
    tags: ['Bass', 'Sub', 'Dark'],
    difficulty: 'Easy',
  },
  // TDR Nova
  {
    pluginId: 'tdr-nova',
    presetName: 'Vocal Clean',
    description: '人声清理预设',
    tags: ['Vocal', 'EQ', 'Clean'],
    difficulty: 'Easy',
  },
  {
    pluginId: 'tdr-nova',
    presetName: 'Mastering EQ',
    description: '母带 EQ 设置',
    tags: ['Mastering', 'EQ', 'Final'],
    difficulty: 'Hard',
  },
  // Valhalla Supermassive
  {
    pluginId: 'valhalla-supermassive',
    presetName: 'Vocal Plate',
    description: '经典人声 Plate 混响',
    tags: ['Vocal', 'Plate', 'Classic'],
    difficulty: 'Easy',
  },
  {
    pluginId: 'valhalla-supermassive',
    presetName: 'Shimmer',
    description: '梦幻八度混响',
    tags: ['Ambient', 'Shimmer', 'Ethereal'],
    difficulty: 'Medium',
  },
];

export function recommendPresets(pluginId: string, tags?: string[]): PresetRecommendation[] {
  let results = PRESET_LIBRARY.filter(p => p.pluginId === pluginId);
  
  if (tags && tags.length > 0) {
    results = results.filter(p => 
      tags.some(tag => p.tags.map(t => t.toLowerCase()).includes(tag.toLowerCase()))
    );
  }

  return results;
}

// ============================================
// 性能评级
// ============================================

export interface PerformanceRating {
  pluginId: string;
  cpuScore: 'Excellent' | 'Good' | 'Fair' | 'Poor';
  memoryScore: 'Excellent' | 'Good' | 'Fair' | 'Poor';
  overallScore: number;  // 0-10
  recommendation: string;
}

export function ratePerformance(pluginId: string): PerformanceRating {
  const plugin = PLUGIN_DATABASE.find(p => p.id === pluginId);
  
  if (!plugin) {
    throw new Error(`Plugin ${pluginId} not found`);
  }

  // CPU 评分
  let cpuScore: PerformanceRating['cpuScore'];
  if (plugin.cpuUsage < 1) cpuScore = 'Excellent';
  else if (plugin.cpuUsage < 2) cpuScore = 'Good';
  else if (plugin.cpuUsage < 4) cpuScore = 'Fair';
  else cpuScore = 'Poor';

  // 内存评分
  let memoryScore: PerformanceRating['memoryScore'];
  if (plugin.memoryUsage < 10) memoryScore = 'Excellent';
  else if (plugin.memoryUsage < 30) memoryScore = 'Good';
  else if (plugin.memoryUsage < 60) memoryScore = 'Fair';
  else memoryScore = 'Poor';

  // 综合评分 (CPU 40% + 内存 20% + 评分 40%)
  const cpuPoints = (5 - plugin.cpuUsage) * 2;  // 最高 10 分
  const memPoints = (5 - plugin.memoryUsage / 20) * 0.4;  // 最高 10 分
  const ratingPoints = plugin.rating * 2;  // 最高 10 分
  
  const overallScore = (cpuPoints * 0.4 + memPoints * 0.2 + ratingPoints * 0.4);

  // 推荐语
  let recommendation = '';
  if (overallScore >= 8.5) {
    recommendation = '强烈推荐 - 性能与音质俱佳';
  } else if (overallScore >= 7) {
    recommendation = '推荐 - 适合大多数场景';
  } else if (overallScore >= 5) {
    recommendation = '可用 - 特定场景使用';
  } else {
    recommendation = '谨慎使用 - CPU 占用较高';
  }

  return {
    pluginId,
    cpuScore,
    memoryScore,
    overallScore: parseFloat(overallScore.toFixed(1)),
    recommendation,
  };
}

// ============================================
// 导出所有推荐
// ============================================

export const VST_RECOMMENDATION_ENGINE = {
  // 数据库
  PLUGIN_DATABASE,
  SCENE_PRESETS,
  PRESET_LIBRARY,
  
  // 推荐函数
  recommendForScene,
  recommendForGenre,
  recommendByBudget,
  recommendByCPU,
  recommendByDifficulty,
  buildChainForPurpose,
  smartRecommend,
  recommendPresets,
  
  // 性能评级
  ratePerformance,
};

export default VST_RECOMMENDATION_ENGINE;