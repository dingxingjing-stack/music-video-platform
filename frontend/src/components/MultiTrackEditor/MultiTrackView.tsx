/**
 * MultiTrackView — 多轨编辑器视图包装器
 * 集成到 TrackStudio 中作为可选视图
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { MultiTrackTimeline } from '../MultiTrackEditor';
import type { Track } from '../../types/trackStudio';
import type { MidiTrack } from '../../types/trackStudio';
import type { AutomationLane } from '../../types/automation';
import type { EffectChain } from '../../types/effects';
import { EffectsPanel } from '../TrackStudio/EffectsPanel';
import { AutomationPanel } from '../TrackStudio/AutomationPanel';
import { ProjectManager } from '../TrackStudio/ProjectManager';
import { AudioExporter } from '../TrackStudio/AudioExporter';
import { AIGeneratePanel } from '../TrackStudio/AIGeneratePanel';
import { MixConsole } from '../MixConsole';

interface Props {
  tracks: Track[];
  onTracksChange: (tracks: Track[]) => void;
  onBack: () => void;
}

export function MultiTrackView({ tracks, onTracksChange, onBack }: Props) {
  const [showEffects, setShowEffects] = useState(false);
  const [showAutomation, setShowAutomation] = useState(false);
  const [showProjectManager, setShowProjectManager] = useState(false);
  const [showAudioExporter, setShowAudioExporter] = useState(false);
  const [showAIGenerate, setShowAIGenerate] = useState(false);
  const [showMixConsole, setShowMixConsole] = useState(false);
  const [masterVolume, setMasterVolume] = useState(0.8);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const animationRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const pauseTimeRef = useRef<number>(0);

  // 处理 AI 生成完成
  const handleAIGenerated = useCallback((audioUrl: string, title: string) => {
    // 创建新轨道并添加生成的音频
    const newTrack: Track = {
      id: `track-${Date.now()}`,
      name: title,
      type: 'audio',
      status: 'ready',
      url: audioUrl,
      progress: 100,
      color: '#ff6b35',
      muted: false,
      solo: false,
      volume: 1,
      pan: 0,
      clips: [{
        id: `clip-${Date.now()}`,
        name: title,
        startTime: 0,
        duration: 180, // 默认 3 分钟
        url: audioUrl,
      }],
    };
    onTracksChange([...tracks, newTrack]);
    setShowAIGenerate(false);
  }, [tracks, onTracksChange]);

  // 项目状态（用于保存/加载）
  const projectState = {
    tracks,
    midiTracks: [] as MidiTrack[],
    automation: [] as AutomationLane[],
    effects: null as EffectChain | null,
    tempo: 120,
    totalDuration: 300,
  };

  // 加载项目数据
  const handleLoadProject = useCallback((state: { tracks: Track[]; midiTracks: MidiTrack[]; automation: AutomationLane[]; effects: EffectChain | null; tempo: number; totalDuration: number }) => {
    onTracksChange(state.tracks);
    // TODO: 加载 midiTracks, automation, effects 等
  }, [onTracksChange]);

  // 同步播放时间
  useEffect(() => {
    if (isPlaying) {
      startTimeRef.current = Date.now() - pauseTimeRef.current * 1000;
      
      const update = () => {
        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        setCurrentTime(elapsed);
        animationRef.current = requestAnimationFrame(update);
      };
      
      update();
    } else {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying]);

  const handlePlay = useCallback((time: number) => {
    pauseTimeRef.current = time;
    setIsPlaying(true);
  }, []);

  const handleStop = useCallback(() => {
    setIsPlaying(false);
    pauseTimeRef.current = currentTime;
  }, [currentTime]);

  const handleTracksChange = useCallback((newTracks: Track[]) => {
    onTracksChange(newTracks);
  }, [onTracksChange]);

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#1e1e1e] border-b border-[#2a2a2a]">
        <button
          onClick={onBack}
          className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
        >
          ← 返回
        </button>
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-[#e0e0e0]">多轨编辑器</h2>
          <button
            onClick={() => setShowAIGenerate(true)}
            className="px-3 py-1.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition"
          >
            ✨ AI 生成
          </button>
          <button
            onClick={() => setShowProjectManager(true)}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
          >
            📁 项目
          </button>
          <button
            onClick={() => setShowAudioExporter(true)}
            disabled={tracks.length === 0}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            📤 导出音频
          </button>
          <button
            onClick={() => {
              if (tracks.length > 0) {
                setSelectedTrackId(tracks[0].id);
                setShowEffects(true);
              }
            }}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
          >
            🎛️ 效果器
          </button>
          <button
            onClick={() => setShowAutomation(true)}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
          >
            📈 自动化
          </button>
          <button
            onClick={() => setShowMixConsole(true)}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded-lg text-sm font-medium transition-colors"
          >
            🎚️ 混音台
          </button>
        </div>
        <div className="w-20" />
      </div>

      {/* 多轨时间轴 */}
      <div className="flex-1">
        <MultiTrackTimeline
          tracks={tracks}
          onTracksChange={handleTracksChange}
          onPlay={handlePlay}
          onStop={handleStop}
          isPlaying={isPlaying}
          currentTime={currentTime}
        />
      </div>

      {/* 效果器面板 */}
      {showEffects && selectedTrackId && (
        <EffectsPanel
          trackId={selectedTrackId}
          trackName={tracks.find(t => t.id === selectedTrackId)?.name || 'Track'}
          onClose={() => setShowEffects(false)}
        />
      )}

      {/* 自动化面板 */}
      {showAutomation && (
        <AutomationPanel
          onClose={() => setShowAutomation(false)}
        />
      )}

      {/* 项目管理面板 */}
      {showProjectManager && (
        <ProjectManager
          projectState={projectState}
          onLoadProject={handleLoadProject}
          onClose={() => setShowProjectManager(false)}
        />
      )}

      {/* 音频导出面板 */}
      {showAudioExporter && (
        <AudioExporter
          tracks={tracks}
          onClose={() => setShowAudioExporter(false)}
        />
      )}

      {/* AI 生成面板 */}
      {showAIGenerate && (
        <AIGeneratePanel
          onGenerated={handleAIGenerated}
          onClose={() => setShowAIGenerate(false)}
        />
      )}

      {/* 混音台 */}
      {showMixConsole && (
        <MixConsole
          tracks={tracks}
          onUpdateTrack={(trackId, updates) => {
            const updated = tracks.map(t => t.id === trackId ? { ...t, ...updates } : t);
            handleTracksChange(updated);
          }}
          masterVolume={masterVolume}
          onMasterVolumeChange={setMasterVolume}
          onClose={() => setShowMixConsole(false)}
        />
      )}
    </div>
  );
}