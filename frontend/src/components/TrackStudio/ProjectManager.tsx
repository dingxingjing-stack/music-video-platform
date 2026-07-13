/**
 * ProjectManager — 项目管理面板（新建/打开/保存/导入/导出）
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { ProjectMeta, generateProjectId } from '../../types/project';
import { saveProject, loadProject, deleteProject, listProjects, exportProjectAsFile, importProjectFromFile } from '../../utils/projectManager';
import type { Track } from '../../types/trackStudio';
import type { MidiTrack } from '../../types/trackStudio';
import type { AutomationLane } from '../../types/automation';
import type { EffectChain } from '../../types/effects';

interface ProjectState {
  tracks: Track[];
  midiTracks: MidiTrack[];
  automation: AutomationLane[];
  effects: EffectChain | null;
  tempo: number;
  totalDuration: number;
}

interface Props {
  projectState: ProjectState;
  onLoadProject: (state: ProjectState) => void;
  onClose: () => void;
}

export function ProjectManager({ projectState, onLoadProject, onClose }: Props) {
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectMeta | null>(null);
  const [projectName, setProjectName] = useState('Untitled Project');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 加载项目列表
  const refreshProjects = useCallback(async () => {
    const list = await listProjects();
    setProjects(list);
  }, []);

  // 新建项目
  const handleNewProject = useCallback(() => {
    onLoadProject({
      tracks: [],
      midiTracks: [],
      automation: [],
      effects: null,
      tempo: 120,
      totalDuration: 300,
    });
    setSuccess('已新建项目');
    setTimeout(() => setSuccess(null), 2000);
  }, [onLoadProject]);

  // 保存项目
  const handleSave = useCallback(async () => {
    const project = {
      id: selectedProject?.id || generateProjectId(),
      name: projectName,
      ...projectState,
      version: 1,
      createdAt: selectedProject?.createdAt ? Date.now() : Date.now(),
      updatedAt: Date.now(),
      isDirty: false,
    };

    try {
      const meta = await saveProject(project as any, { name: projectName, includeAudio: false, format: 'json' });
      setSuccess(`已保存：${meta.name}`);
      setError(null);
      refreshProjects();
      setTimeout(() => setSuccess(null), 2000);
    } catch (e) {
      setError('保存失败');
    }
  }, [projectState, projectName, selectedProject, refreshProjects]);

  // 打开项目
  const handleOpen = useCallback(async () => {
    if (!selectedProject) return;

    try {
      const result = await loadProject(selectedProject.id);
      if (result.success) {
        onLoadProject({
          tracks: result.project.tracks || [],
          midiTracks: result.project.midiTracks || [],
          automation: result.project.automation || [],
          effects: result.project.effects,
          tempo: result.project.tempo || 120,
          totalDuration: result.project.totalDuration || 300,
        });
        setSuccess(`已加载：${result.project.name}`);
        setTimeout(() => setSuccess(null), 2000);
      } else {
        setError(result.error || '加载失败');
      }
    } catch (e) {
      setError('加载失败');
    }
  }, [selectedProject, onLoadProject]);

  // 删除项目
  const handleDelete = useCallback(async () => {
    if (!selectedProject) return;

    if (!confirm(`确定要删除 "${selectedProject.name}" 吗？`)) return;

    try {
      await deleteProject(selectedProject.id);
      refreshProjects();
      setSelectedProject(null);
      setSuccess('已删除项目');
      setTimeout(() => setSuccess(null), 2000);
    } catch {
      setError('删除失败');
    }
  }, [selectedProject, refreshProjects]);

  // 导出项目
  const handleExport = useCallback(() => {
    if (!selectedProject) return;

    loadProject(selectedProject.id).then((result: any) => {
      if (result.success) {
        exportProjectAsFile(result.project, selectedProject.name);
        setSuccess('已导出项目文件');
        setTimeout(() => setSuccess(null), 2000);
      }
    });
  }, [selectedProject]);

  // 导入项目
  const handleImport = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    importProjectFromFile(file).then((result: any) => {
      if (result.success) {
        saveProject(result.project, { name: result.meta.name, includeAudio: false, format: 'json' });
        onLoadProject({
          tracks: result.project.tracks || [],
          midiTracks: result.project.midiTracks || [],
          automation: result.project.automation || [],
          effects: result.project.effects,
          tempo: result.project.tempo || 120,
          totalDuration: result.project.totalDuration || 300,
        });
        refreshProjects();
        setSuccess(`已导入：${result.project.name}`);
        setTimeout(() => setSuccess(null), 2000);
      } else {
        setError(result.error || '导入失败');
      }
    });

    // 重置 input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [onLoadProject, refreshProjects]);

  // 初始化加载列表
  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[700px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">📁 项目管理</h2>
            <p className="text-xs text-[#777777]">新建/打开/保存/导入/导出 工程文件</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 p-4 bg-[#121212] border-b border-[#2a2a2a]">
          <button
            onClick={handleNewProject}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition"
          >
            📄 新建
          </button>
          <button
            onClick={handleSave}
            disabled={!projectName}
            className="px-3 py-1.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded text-sm transition disabled:opacity-50"
          >
            💾 保存
          </button>
          <button
            onClick={handleOpen}
            disabled={!selectedProject}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50"
          >
            📂 打开
          </button>
          <button
            onClick={handleDelete}
            disabled={!selectedProject}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#ef4444] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50"
          >
            🗑️ 删除
          </button>
          <button
            onClick={handleExport}
            disabled={!selectedProject}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50"
          >
            📤 导出
          </button>
          <label className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition cursor-pointer">
            📥 导入
            <input
              ref={fileInputRef}
              type="file"
              accept=".mpp,.json"
              onChange={handleImport}
              className="hidden"
            />
          </label>
        </div>

        {/* 项目名称输入 */}
        <div className="p-4 border-b border-[#2a2a2a]">
          <label className="text-xs text-[#777777] mb-1 block">项目名称</label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded px-3 py-2 text-sm text-[#e0e0e0]"
            placeholder="Untitled Project"
          />
        </div>

        {/* 项目列表 */}
        <div className="flex-1 overflow-auto p-4">
          <h3 className="text-sm font-semibold text-[#e0e0e0] mb-3">已保存的项目</h3>
          {projects.length === 0 ? (
            <p className="text-xs text-[#777777] text-center py-8">暂无项目</p>
          ) : (
            <div className="space-y-2">
              {projects.map(project => (
                <div
                  key={project.id}
                  onClick={() => setSelectedProject(project)}
                  className={`p-3 rounded border cursor-pointer transition ${
                    selectedProject?.id === project.id
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-[#2a2a2a] bg-[#121212] hover:border-[#3a3a3a]'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-[#e0e0e0]">{project.name}</p>
                      <p className="text-xs text-[#777777]">
                        {new Date(project.updatedAt).toLocaleString()} · {(project.fileSize / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    {selectedProject?.id === project.id && (
                      <span className="text-xs text-orange-500">● 已选择</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 状态提示 */}
        {(error || success) && (
          <div className={`p-3 text-center text-sm ${
            error ? 'bg-[#ef4444]/20 text-[#ef4444]' : 'bg-[#22c55e]/20 text-[#22c55e]'
          }`}>
            {error || success}
          </div>
        )}

        {/* 底部 */}
        <div className="p-4 border-t border-[#2a2a2a] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}