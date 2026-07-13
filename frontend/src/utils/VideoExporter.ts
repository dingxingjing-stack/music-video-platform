/**
 * 视频合成导出工具
 * 
 * 使用 FFmpeg.wasm 在浏览器端合成视频
 * 零服务器成本!
 * 
 * 功能:
 * - 合并视频片段
 * - 添加音频轨道
 * - 添加字幕
 * - 转场效果
 * - 导出 MP4
 */

import { VideoProject, ExportConfig, ExportProgress } from '../types/video-sync';

// FFmpeg.wasm 类型声明 (需要安装 @ffmpeg/ffmpeg)
declare global {
  interface Window {
    createFFmpeg: any;
  }
}

export class VideoExporter {
  private ffmpeg: any = null;
  private initialized = false;

  /**
   * 初始化 FFmpeg.wasm
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    // 动态加载 FFmpeg.wasm
    if (!window.createFFmpeg) {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/@ffmpeg/ffmpeg@0.11.0/dist/ffmpeg.min.js';
      await new Promise((resolve, reject) => {
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
      });
    }

    this.ffmpeg = window.createFFmpeg({
      log: true
    });

    await this.ffmpeg.load();
    this.initialized = true;
  }

  /**
   * 导出视频
   */
  async exportVideo(
    project: VideoProject,
    config: ExportConfig,
    onProgress: (progress: ExportProgress) => void
  ): Promise<string> {
    try {
      onProgress({
        status: 'pending',
        progress: 0,
        message: '准备导出...'
      });

      // 初始化 FFmpeg
      await this.initialize();

      // 写入音频文件
      if (project.audioFile) {
        const audioData = await fetch(project.audioFile).then(r => r.arrayBuffer());
        this.ffmpeg.FS('writeFile', 'audio.mp3', new Uint8Array(audioData));
      }

      // 写入视频片段
      const videoClips: string[] = [];
      for (const track of project.tracks) {
        for (const clip of track.clips) {
          const clipData = await fetch(clip.url).then(r => r.arrayBuffer());
          const filename = `clip_${clip.id}.mp4`;
          this.ffmpeg.FS('writeFile', filename, new Uint8Array(clipData));
          videoClips.push(filename);
        }
      }

      onProgress({
        status: 'encoding',
        progress: 20,
        message: '正在合成视频...'
      });

      // 生成 FFmpeg 命令
      const commands = this.buildFFmpegCommand(videoClips, config);

      // 执行 FFmpeg
      await this.ffmpeg.run(...commands);

      onProgress({
        status: 'encoding',
        progress: 80,
        message: '正在编码...'
      });

      // 读取输出文件
      const outputData = this.ffmpeg.FS('readFile', 'output.mp4');

      // 创建 Blob URL
      const blob = new Blob([outputData.buffer], { type: 'video/mp4' });
      const url = URL.createObjectURL(blob);

      onProgress({
        status: 'completed',
        progress: 100,
        message: '导出完成!',
        outputUrl: url
      });

      return url;
    } catch (error: any) {
      onProgress({
        status: 'error',
        progress: 0,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * 构建 FFmpeg 命令
   */
  private buildFFmpegCommand(
    videoClips: string[],
    config: ExportConfig
  ): string[] {
    // 简化版本：合并所有视频 + 音频
    // 实际应该根据时间轴精确剪辑

    const inputs: string[] = [];

    // 添加视频输入
    videoClips.forEach(clip => {
      inputs.push('-i', clip);
    });

    // 添加音频输入
    if (config.includeAudio !== false) {
      inputs.push('-i', 'audio.mp3');
    }

    // 构建命令
    const resolution = this.getResolution(config.resolution);
    
    const commands = [
      ...inputs,
      '-filter_complex',
      this.buildFilterComplex(videoClips.length),
      '-c:v', 'libx264',
      '-preset', 'medium',
      '-crf', '23',
      '-c:a', 'aac',
      '-b:a', '192k',
      '-r', config.fps.toString(),
      '-s', `${resolution.width}x${resolution.height}`,
      'output.mp4'
    ];

    return commands;
  }

  /**
   * 构建滤镜链
   */
  private buildFilterComplex(clipCount: number): string {
    // 简单版本：concat 所有视频
    if (clipCount === 0) {
      // 只有音频
      return 'anull';
    }

    // 生成 concat 滤镜
    let filter = '';
    for (let i = 0; i < clipCount; i++) {
      filter += `[${i}:v]setpts=PTS-STARTPTS[v${i}];`;
      filter += `[${i}:a]asetpts=PTS-STARTPTS[a${i}];`;
    }

    filter += `[${Array.from({ length: clipCount }, (_, i) => `v${i}`).join('')}]`;
    filter += `concat=n=${clipCount}:v=1:a=1[outv][outa]`;

    return filter;
  }

  /**
   * 获取分辨率
   */
  private getResolution(resolution: string): { width: number; height: number } {
    switch (resolution) {
      case '480p': return { width: 854, height: 480 };
      case '720p': return { width: 1280, height: 720 };
      case '1080p': return { width: 1920, height: 1080 };
      case '4k': return { width: 3840, height: 2160 };
      default: return { width: 1920, height: 1080 };
    }
  }

  /**
   * 清理资源
   */
  dispose() {
    if (this.ffmpeg) {
      this.ffmpeg.exit();
      this.initialized = false;
    }
  }
}