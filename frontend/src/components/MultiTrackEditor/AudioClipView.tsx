/**
 * AudioClipView — 音频片段可视化（支持拖拽、调整大小、淡入淡出）
 */

import { useCallback } from 'react';
import { AudioClip } from '../../types/trackStudio';

interface Zoom {
  x: number;
  y: number;
}

interface Props {
  clip: AudioClip;
  zoom: Zoom;
  isSelected: boolean;
  onSelect: (clipId: string) => void;
  onChange: (updates: Partial<AudioClip>) => void;
  onDelete?: () => void;
}

export function AudioClipView({ clip, zoom, isSelected, onSelect, onChange }: Props) {
  const width = clip.duration * zoom.x;
  const left = clip.startTime * zoom.x;

  // 处理拖拽移动
  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onSelect(clip.id);

      const startX = e.clientX;
      const originalStart = clip.startTime;

      const onMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaSeconds = deltaX / zoom.x;
        const newStart = Math.max(0, originalStart + deltaSeconds);
        onChange({ ...clip, startTime: newStart });
      };

      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [clip, zoom.x, onSelect, onChange]
  );

  // 处理右侧调整大小
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onSelect(clip.id);

      const startX = e.clientX;
      const originalDuration = clip.duration;

      const onMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaSeconds = deltaX / zoom.x;
        const newDuration = Math.max(0.5, originalDuration + deltaSeconds);
        onChange({ ...clip, duration: newDuration });
      };

      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [clip, zoom.x, onSelect, onChange]
  );

  // 处理左侧淡入调整
  const handleFadeInStart = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const currentFadeIn = clip.fadeIn || 0;
      const newFadeIn = Math.max(0, Math.min(clip.duration / 2, currentFadeIn + 0.1));
      onChange({ ...clip, fadeIn: newFadeIn });
    },
    [clip, onChange]
  );

  // 右键菜单删除
  const handleContextMenu = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      onSelect(clip.id);
    },
    [clip.id, onSelect]
  );

  return (
    <div
      className={`absolute top-1 h-16 rounded-md cursor-pointer transition-all
        ${isSelected
          ? 'bg-gradient-to-r from-orange-500 to-pink-500 ring-2 ring-white'
          : 'bg-gradient-to-r from-orange-600/80 to-pink-600/80 hover:from-orange-500 hover:to-pink-500'
        }`}
      style={{
        left: `${left}px`,
        width: `${width}px`,
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(clip.id);
      }}
      onContextMenu={handleContextMenu}
    >
      {/* 拖拽区域 */}
      <div
        className="absolute inset-0 cursor-move flex items-center px-2"
        onMouseDown={handleDragStart}
      >
        <span className="text-xs font-medium text-white truncate drop-shadow-md">
          {clip.name}
        </span>
      </div>

      {/* 左侧淡入控制 */}
      {(clip.fadeIn || 0) > 0 && (
        <div
          className="absolute left-0 top-0 bottom-0 w-5 bg-gradient-to-r from-black/20 to-transparent cursor-ew-resize"
          title="淡入"
          onMouseDown={handleFadeInStart}
        />
      )}

      {/* 右侧调整大小手柄 */}
      <div
        className="absolute right-0 top-0 bottom-0 w-3 cursor-e-resize bg-white/20 hover:bg-white/40 rounded-r-md"
        onMouseDown={handleResizeStart}
      />

      {/* 波形占位 */}
      <div className="absolute inset-0 opacity-30">
        <svg className="w-full h-full" preserveAspectRatio="none">
          <path
            d={`M0,32 Q${width / 4},12 ${width / 2},32 T${width},32 L${width},96 Q${width * 3 / 4},116 ${width / 2},96 T0,96 Z`}
            fill="rgba(0,0,0,0.3)"
          />
        </svg>
      </div>

      {/* 时长标签 */}
      <div className="absolute bottom-1 right-1 text-[10px] text-white/80 font-mono">
        {clip.duration.toFixed(1)}s
      </div>
    </div>
  );
}