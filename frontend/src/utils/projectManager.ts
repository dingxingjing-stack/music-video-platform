/**
 * 项目管理工具 - 保存/加载/删除项目
 */

import { ProjectFile, ProjectMeta, SaveOptions, LoadResult, generateProjectId, PROJECT_STORAGE_KEY } from '../types/project';

// 压缩项目数据（移除冗余字段）
function compressProject(project: ProjectFile): Partial<ProjectFile> {
  return {
    name: project.name,
    version: project.version,
    tempo: project.tempo,
    timeSignature: project.timeSignature,
    totalDuration: project.totalDuration,
    tracks: project.tracks,
    midiTracks: project.midiTracks,
    automation: project.automation,
    effects: project.effects,
  };
}

// 解压项目数据
function decompressProject(data: any, id: string): ProjectFile {
  const now = Date.now();
  return {
    id,
    name: data.name || 'Untitled Project',
    version: data.version || 1,
    createdAt: data.createdAt || now,
    updatedAt: now,
    tempo: data.tempo || 120,
    timeSignature: data.timeSignature || { numerator: 4, denominator: 4 },
    totalDuration: data.totalDuration || 300,
    tracks: data.tracks || [],
    midiTracks: data.midiTracks || [],
    automation: data.automation || [],
    effects: data.effects || null,
    isDirty: false,
  };
}

// 保存到 localStorage
export async function saveProject(
  project: ProjectFile,
  options: SaveOptions
): Promise<ProjectMeta> {
  const compressed = compressProject(project);
  const serialized = JSON.stringify(compressed);
  const bytes = new TextEncoder().encode(serialized).length;

  // 获取现有项目列表
  const existingJson = localStorage.getItem(PROJECT_STORAGE_KEY);
  const projects: Record<string, any> = existingJson ? JSON.parse(existingJson) : {};

  // 保存项目数据
  const projectId = project.id || generateProjectId();
  projects[projectId] = {
    data: compressed,
    meta: {
      id: projectId,
      name: options.name,
      tags: [],
      createdAt: project.createdAt || Date.now(),
      updatedAt: Date.now(),
      fileSize: bytes,
    } as ProjectMeta,
  };

  localStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(projects));

  return projects[projectId].meta;
}

// 从 localStorage 加载
export async function loadProject(projectId: string): Promise<LoadResult> {
  try {
    const existingJson = localStorage.getItem(PROJECT_STORAGE_KEY);
    if (!existingJson) {
      return { project: null as any, meta: null as any, success: false, error: 'No projects found' };
    }

    const projects: Record<string, any> = JSON.parse(existingJson);
    const stored = projects[projectId];

    if (!stored) {
      return { project: null as any, meta: null as any, success: false, error: 'Project not found' };
    }

    const project = decompressProject(stored.data, projectId);
    const meta = stored.meta as ProjectMeta;

    return { project, meta, success: true };
  } catch (error) {
    return {
      project: null as any,
      meta: null as any,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

// 删除项目
export async function deleteProject(projectId: string): Promise<boolean> {
  try {
    const existingJson = localStorage.getItem(PROJECT_STORAGE_KEY);
    if (!existingJson) return false;

    const projects: Record<string, any> = JSON.parse(existingJson);
    if (!projects[projectId]) return false;

    delete projects[projectId];
    localStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(projects));
    return true;
  } catch {
    return false;
  }
}

// 列出所有项目
export async function listProjects(): Promise<ProjectMeta[]> {
  try {
    const existingJson = localStorage.getItem(PROJECT_STORAGE_KEY);
    if (!existingJson) return [];

    const projects: Record<string, any> = JSON.parse(existingJson);
    return Object.values(projects).map(p => p.meta as ProjectMeta);
  } catch {
    return [];
  }
}

// 导出为 JSON 文件（下载）
export function exportProjectAsFile(project: ProjectFile, fileName: string): void {
  const compressed = compressProject(project);
  const serialized = JSON.stringify(compressed, null, 2);
  const blob = new Blob([serialized], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = `${fileName}.mpp`; // Music Platform Project
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// 从 JSON 文件导入
export async function importProjectFromFile(file: File): Promise<LoadResult> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        const projectId = generateProjectId();
        const project = decompressProject(data, projectId);
        const meta: ProjectMeta = {
          id: projectId,
          name: data.name || file.name.replace('.mpp', ''),
          createdAt: Date.now(),
          updatedAt: Date.now(),
          fileSize: file.size,
          tags: [],
        };
        resolve({ project, meta, success: true });
      } catch (error) {
        resolve({
          project: null as any,
          meta: null as any,
          success: false,
          error: error instanceof Error ? error.message : 'Invalid file format',
        });
      }
    };
    reader.onerror = () => {
      resolve({
        project: null as any,
        meta: null as any,
        success: false,
        error: 'Failed to read file',
      });
    };
    reader.readAsText(file);
  });
}