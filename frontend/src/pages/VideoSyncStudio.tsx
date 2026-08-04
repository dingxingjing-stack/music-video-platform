/**
 * 视频同步工作室页面
 * 
 * 整合:
 * - 视频时间轴
 * - 歌词编辑器
 * - 素材库
 * - 导出功能
 */

import { useState, useRef, useEffect } from 'react';
import { VideoTimeline } from '../components/VideoTimeline';
import { LyricEditor } from '../components/LyricEditor';
import { StockVideoLibrary } from '../components/StockVideoLibrary';
import { VideoExporter } from '../utils/VideoExporter';
import { WaveformAnalyzer } from '../utils/WaveformAnalyzer';
import { SongContinuePanel } from '../components/SongContinuePanel';
import { SubtitleRecognizer } from '../components/SubtitleRecognizer';
import { MVTemplateGallery } from '../components/MVTemplateGallery';
import { TransitionLibrary } from '../components/TransitionLibrary';
import { VideoTrack, VideoClip, LyricLine, VideoProject, StockVideo, ExportConfig } from '../types/video-sync';

export function VideoSyncStudio() {
  // 项目状态
  const [project, setProject] = useState<VideoProject | null>(null);
  const [audioFile, setAudioFile] = useState<string | null>(null);
  const [duration, setDuration] = useState(180); // 默认 3 分钟
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [zoom, setZoom] = useState(50);
  const [activeToolTab, setActiveToolTab] = useState<'videos' | 'lyrics' | 'subtitles' | 'templates' | 'transitions' | 'continue'>('videos');

  // 轨道和歌词
  const [tracks, setTracks] = useState<VideoTrack[]>([]);
  const [lyrics, setLyrics] = useState<LyricLine[]>([]);
  const [beatMarkers, setBeatMarkers] = useState<any[]>([]);
  const [waveformData, setWaveformData] = useState<any>(null);

  // 导出状态
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);

  // 工具引用
  const waveformAnalyzer = useRef<WaveformAnalyzer | null>(null);
  const videoExporter = useRef<VideoExporter | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    waveformAnalyzer.current = new WaveformAnalyzer();
    videoExporter.current = new VideoExporter();
    audioRef.current = new Audio();

    return () => {
      waveformAnalyzer.current?.dispose();
      videoExporter.current?.dispose();
    };
  }, []);

  // 加载音频文件
  const handleAudioLoad = async (file: File) => {
    const url = URL.createObjectURL(file);
    setAudioFile(url);

    // 分析波形
    const analyzer = waveformAnalyzer.current;
    if (analyzer) {
      const waveform = await analyzer.loadAudio(url);
      setWaveformData(waveform);
      setDuration(waveform.duration);

      // 检测节拍
      const beats = await analyzer.detectBeats();
      setBeatMarkers(beats);
    }

    // 设置音频播放
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.ondurationchange = () => {
        setDuration(audioRef.current!.duration);
      };
    }
  };

  // 播放控制
  const togglePlay = () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  // 时间更新
  useEffect(() => {
    if (!audioRef.current) return;

    const handleTimeUpdate = () => {
      setCurrentTime(audioRef.current!.currentTime);
    };

    audioRef.current.addEventListener('timeupdate', handleTimeUpdate);
    return () => audioRef.current?.removeEventListener('timeupdate', handleTimeUpdate);
  }, []);

  // 跳转时间
  const handleTimeChange = (time: number) => {
    setCurrentTime(time);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
    }
  };

  // 添加视频剪辑到时间轴
  const handleVideoSelect = (stockVideo: StockVideo) => {
    const newClip: VideoClip = {
      id: `clip-${Date.now()}`,
      name: stockVideo.title,
      url: stockVideo.url,
      thumbnailUrl: stockVideo.thumbnailUrl,
      duration: Math.min(stockVideo.duration, duration),
      startTime: currentTime,
      endTime: currentTime + stockVideo.duration,
      trackId: tracks[0]?.id || 'track-1',
      volume: 0, // 静音原视频，只用背景音乐
    };

    // 确保有轨道
    if (tracks.length === 0) {
      const newTrack: VideoTrack = {
        id: 'track-1',
        name: '视频轨道 1',
        color: '#f97316',
        visible: true,
        locked: false,
        clips: [newClip],
        height: 96,
      };
      setTracks([newTrack]);
    } else {
      // 添加到第一个轨道
      const updatedTracks = [...tracks];
      updatedTracks[0].clips.push(newClip);
      setTracks(updatedTracks);
    }
  };

  // 移动剪辑
  const handleClipMove = (clipId: string, trackId: string, startTime: number) => {
    const updatedTracks = tracks.map(track => ({
      ...track,
      clips: track.clips.map(clip =>
        clip.id === clipId
          ? { ...clip, startTime, endTime: startTime + clip.duration }
          : clip
      )
    }));
    setTracks(updatedTracks);
  };

  // 导出视频
  const handleExport = async () => {
    if (!project || !videoExporter.current) return;

    setIsExporting(true);
    setExportProgress(0);

    try {
      const config: ExportConfig = {
        format: 'mp4',
        quality: 'high',
        resolution: '1080p',
        fps: 30,
        includeLyrics: true,
        includeWatermark: false
      };

      const exportProject: VideoProject = {
        ...project,
        tracks,
        lyrics,
        beatMarkers,
        audioFile: audioFile || undefined
      };

      await videoExporter.current.exportVideo(
        exportProject,
        config,
        (progress) => {
          if (progress.outputUrl) {
            // 触发下载
            const a = document.createElement('a');
            a.href = progress.outputUrl;
            a.download = `${project.name}.mp4`;
            a.click();
          }
          setExportProgress(progress.progress);
        }
      );
    } catch (error) {
      console.error('导出失败:', error);
      alert('导出失败，请重试');
    } finally {
      setIsExporting(false);
    }
  };

  if (!project) {
    // 创建新项目
    return (
      <div className="h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-white mb-4">🎬 视频同步工作室</h1>
          <p className="text-gray-400 mb-8">从音乐制作专业 MV</p>
          
          <div className="space-y-4 max-w-md mx-auto">
            <div>
              <label className="block text-gray-300 mb-2">项目名称</label>
              <input
                type="text"
                placeholder="我的 MV"
                onChange={(e) => {
                  setProject({
                    id: Date.now().toString(),
                    name: e.target.value,
                    width: 1920,
                    height: 1080,
                    fps: 30,
                    tracks: [],
                    lyrics: [],
                    beatMarkers: [],
                    createdAt: Date.now(),
                    updatedAt: Date.now()
                  });
                }}
                className="w-full bg-gray-800 text-white px-4 py-2 rounded"
              />
            </div>
            
            <div>
              <label className="block text-gray-300 mb-2">选择音乐文件</label>
              <input
                type="file"
                accept="audio/*"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleAudioLoad(file);
                }}
                className="w-full bg-gray-800 text-white px-4 py-2 rounded"
              />
            </div>
            
            <button
              onClick={() => {}}
              disabled={!project || !audioFile}
              className="w-full py-3 bg-orange-600 hover:bg-orange-500 disabled:bg-gray-700 text-white rounded font-semibold"
            >
              开始制作 MV
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 主工作区
  return (
    <div className="h-screen bg-gray-950 flex flex-col">
      {/* 顶部工具栏 */}
      <div className="h-16 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <h1 className="text-white font-bold text-xl">{project.name}</h1>
          
          {/* 播放控制 */}
          <div className="flex items-center gap-2">
            <button
              onClick={togglePlay}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded"
            >
              {isPlaying ? '⏸ 暂停' : '▶ 播放'}
            </button>
            <span className="text-white font-mono">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {/* 缩放控制 */}
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">缩放:</span>
            <input
              type="range"
              min="20"
              max="100"
              value={zoom}
              onChange={(e) => setZoom(parseInt(e.target.value))}
              className="w-32"
            />
          </div>
          
          {/* 导出按钮 */}
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="px-6 py-2 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 text-white rounded font-semibold"
          >
            {isExporting ? `导出中... ${exportProgress}%` : '🎬 导出 MV'}
          </button>
        </div>
      </div>
      
      {/* 主工作区 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：工具面板 */}
        <div className="w-96 border-r border-gray-800 flex flex-col">
          {/* Tab 导航 */}
          <div className="flex border-b border-gray-800">
            <button
              onClick={() => setActiveToolTab('videos')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'videos'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              📹 素材
            </button>
            <button
              onClick={() => setActiveToolTab('lyrics')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'lyrics'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              📝 歌词
            </button>
            <button
              onClick={() => setActiveToolTab('subtitles')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'subtitles'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              🎤 字幕
            </button>
            <button
              onClick={() => setActiveToolTab('templates')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'templates'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              🎬 模板
            </button>
            <button
              onClick={() => setActiveToolTab('transitions')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'transitions'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              🎞️ 转场
            </button>
            <button
              onClick={() => setActiveToolTab('continue')}
              className={`flex-1 px-2 py-2 text-xs font-medium transition ${
                activeToolTab === 'continue'
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              ✨ 续写
            </button>
          </div>
          
          {/* 工具内容 */}
          <div className="flex-1 overflow-y-auto">
            {activeToolTab === 'videos' && <StockVideoLibrary onVideoSelect={handleVideoSelect} />}
            {activeToolTab === 'lyrics' && (
              <LyricEditor
                lyrics={lyrics}
                currentTime={currentTime}
                duration={duration}
                onLyricsChange={setLyrics}
              />
            )}
            {activeToolTab === 'subtitles' && (
              <SubtitleRecognizer
                onSubtitlesReady={(subs) => setLyrics(subs.map(s => ({ id: s.id.toString(), time: s.startTime, text: s.text })))}
                duration={duration}
              />
            )}
            {activeToolTab === 'templates' && (
              <MVTemplateGallery onTemplateSelect={(t) => console.log('Applied template:', t)} />
            )}
            {activeToolTab === 'transitions' && (
              <TransitionLibrary onTransitionSelect={(tr) => console.log('Applied transition:', tr)} />
            )}
            {activeToolTab === 'continue' && (
              <SongContinuePanel onContinue={() => {}} />
            )}
          </div>
        </div>
        
        {/* 中间：时间轴 */}
        <div className="flex-1 p-4 overflow-hidden">
          <VideoTimeline
            tracks={tracks}
            waveformData={waveformData}
            beatMarkers={beatMarkers}
            currentTime={currentTime}
            duration={duration}
            onTimeChange={handleTimeChange}
            onClipMove={handleClipMove}
            zoom={zoom}
            onTrackAdd={() => {
              const newTrack: VideoTrack = {
                id: `track-${tracks.length + 1}`,
                name: `视频轨道 ${tracks.length + 1}`,
                color: '#3b82f6',
                visible: true,
                locked: false,
                clips: [],
                height: 96,
              };
              setTracks([...tracks, newTrack]);
            }}
          />
        </div>
      </div>
    </div>
  );
}

// 格式化时间
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}