/**
 * 项目/工程文件管理类型
 */

export interface ProjectFile {
  id: string;
  name: string;
  version: number;
  createdAt: number;
  updatedAt: number;
  // 会话数据
  tracks: any[]; // Track[]
  midiTracks: any[]; // MidiTrack[]
  automation: any[]; // AutomationLane[]
  effects: any; // EffectChain
  // 元数据
  tempo: number;
  timeSignature: { numerator: number; denominator: number };
  totalDuration: number; // seconds
  // 状态
  isDirty: boolean; // 是否有未保存的修改
}

export interface ProjectMeta {
  id: string;
  name: string;
  thumbnail?: string;
  tags: string[];
  description?: string;
  createdAt: number;
  updatedAt: number;
  fileSize: number; // bytes
}

export interface SaveOptions {
  name: string;
  includeAudio: boolean; // 是否嵌入音频数据（会显著增加文件大小）
  format: 'json' | 'binary'; // 未来支持二进制压缩格式
}

export interface LoadResult {
  project: ProjectFile;
  meta: ProjectMeta;
  success: boolean;
  error?: string;
}

export const DEFAULT_PROJECT: Omit<ProjectFile, 'id' | 'createdAt' | 'updatedAt'> = {
  name: 'Untitled Project',
  version: 1,
  tracks: [],
  midiTracks: [],
  automation: [],
  effects: null,
  tempo: 120,
  timeSignature: { numerator: 4, denominator: 4 },
  totalDuration: 300, // 5 minutes default
  isDirty: false,
};

export function generateProjectId(): string {
  return `proj-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export const PROJECT_STORAGE_KEY = 'music-platform-projects';