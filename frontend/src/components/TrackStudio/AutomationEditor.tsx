/**
 * AutomationEditor — 自动化曲线编辑器
 */

import { useState, useCallback, useRef } from 'react';
import { AutomationLane, AutomationPoint, generatePointId } from '../../types/automation';

interface Zoom {
  x: number; // px per second
  y: number; // lane height
}

interface Props {
  lanes: AutomationLane[];
  onLanesChange: (lanes: AutomationLane[]) => void;
  zoom: Zoom;
  duration: number; // total duration in seconds
}

function getValueLabel(value: number, type: string): string {
  if (type === 'pan') {
    return value.toFixed(2);
  }
  if (type.includes('eq')) {
    return `${((value - 0.5) * 24).toFixed(1)} dB`;
  }
  return `${(value * 100).toFixed(0)}%`;
}

export function AutomationEditor({ lanes, onLanesChange, zoom, duration }: Props) {
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState<string | null>(null);

  // 处理点击添加点（需要 laneIndex）
  const handleLaneClickWithIndex = useCallback((laneIndex: number, e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const time = x / zoom.x;

    if (time < 0 || time > duration) return;

    const lane = lanes[laneIndex];
    if (lane.locked || !lane.visible) return;

    // 计算值（从顶部到底部 0-1）
    const laneY = laneIndex * zoom.y;
    const y = e.clientY - rect.top - laneY;
    const value = 1 - (y / zoom.y);
    const clampedValue = Math.max(0, Math.min(1, value));

    const newPoint: AutomationPoint = {
      id: generatePointId(),
      time,
      value: clampedValue,
    };

    const newLanes = lanes.map((l, i) => {
      if (i !== laneIndex) return l;
      return {
        ...l,
        points: [...l.points, newPoint].sort((a, b) => a.time - b.time),
      };
    });

    onLanesChange(newLanes);
    setSelectedPointId(newPoint.id);
  }, [lanes, onLanesChange, zoom, duration]);

  // 处理点拖拽（laneIndex 在 handleMouseMove 中使用）
  const handlePointMouseDown = useCallback((_laneIndex: number, pointId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedPointId(pointId);
    setIsDragging(pointId);
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging || !containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const time = Math.max(0, Math.min(duration, x / zoom.x));

    // 找到对应的 lane 和 point
    const laneIndex = lanes.findIndex(l => l.points.some(p => p.id === isDragging));
    if (laneIndex === -1) return;

    const laneY = laneIndex * zoom.y;
    const y = e.clientY - rect.top - laneY;
    const value = 1 - (y / zoom.y);
    const clampedValue = Math.max(0, Math.min(1, value));

    const newLanes = lanes.map((l, i) => {
      if (i !== laneIndex) return l;
      return {
        ...l,
        points: l.points.map(p =>
          p.id === isDragging ? { ...p, time, value: clampedValue } : p
        ),
      };
    });

    onLanesChange(newLanes);
  }, [isDragging, lanes, onLanesChange, zoom, duration]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(null);
  }, []);

  // 删除选中的点（右键）
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (selectedPointId) {
      const newLanes = lanes.map(lane => ({
        ...lane,
        points: lane.points.filter(p => p.id !== selectedPointId),
      }));
      onLanesChange(newLanes);
      setSelectedPointId(null);
    }
  }, [selectedPointId, lanes, onLanesChange]);

  return (
    <div
      ref={containerRef}
      className="relative bg-[#121212] overflow-hidden"
      style={{ height: `${lanes.length * zoom.y}px` }}
      onClick={(e) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        const y = e.clientY - rect.top;
        const laneIdx = Math.floor(y / zoom.y);
        if (laneIdx >= 0 && laneIdx < lanes.length) {
          handleLaneClickWithIndex(laneIdx, e);
        }
      }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onContextMenu={handleContextMenu}
    >
      {/* 网格线 */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, #2a2a2a 1px, transparent 1px),
            linear-gradient(to bottom, #2a2a2a 1px, transparent 1px)
          `,
          backgroundSize: `${zoom.x * 4}px 100%, 100% ${zoom.y}px`,
        }}
      />

      {/* 时间标记 */}
      <div className="absolute top-0 left-0 right-0 h-6 pointer-events-none">
        {Array.from({ length: Math.ceil(duration / 4) + 1 }).map((_, i) => (
          <div
            key={i}
            className="absolute text-xs text-[#777777]"
            style={{ left: `${i * 4 * zoom.x}px` }}
          >
            {`${i * 4}s`}
          </div>
        ))}
      </div>

      {/* 渲染每条轨道 */}
      {lanes.map((lane, laneIndex) => {
        if (!lane.visible) return null;

        const laneY = laneIndex * zoom.y;

        // 绘制曲线
        const pathD = lane.points.length > 0
          ? lane.points.map((p, i) => {
              const x = p.time * zoom.x;
              const y = (1 - p.value) * zoom.y;
              return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
            }).join(' ')
          : '';

        return (
          <div
            key={lane.type}
            className="absolute left-0 right-0 border-b border-[#2a2a2a]"
            style={{ top: `${laneY}px`, height: `${zoom.y}px` }}
          >
            {/* 轨道标签 */}
            <div
              className="absolute left-2 top-1 text-xs font-medium"
              style={{ color: lane.color }}
            >
              {lane.label}
            </div>

            {/* SVG 曲线 */}
            <svg className="absolute inset-0" style={{ top: '24px' }}>
              {/* 背景线 */}
              <line
                x1="0"
                y1={zoom.y * 0.5}
                x2={duration * zoom.x}
                y2={zoom.y * 0.5}
                stroke={lane.color}
                strokeWidth="1"
                strokeDasharray="4,4"
                opacity="0.3"
              />
              {/* 实际曲线 */}
              <path
                d={pathD}
                fill="none"
                stroke={lane.color}
                strokeWidth="2"
              />
              {/* 点 */}
              {lane.points.map((point) => {
                const x = point.time * zoom.x;
                const y = (1 - point.value) * zoom.y;
                const isSelected = point.id === selectedPointId;

                return (
                  <g key={point.id}>
                    <circle
                      cx={x}
                      cy={y}
                      r={isSelected ? 6 : 4}
                      fill={lane.color}
                      stroke={isSelected ? '#fff' : 'transparent'}
                      strokeWidth="2"
                      className="cursor-pointer"
                      onMouseDown={(e) => handlePointMouseDown(laneIndex, point.id, e)}
                    />
                    {isSelected && (
                      <text
                        x={x + 10}
                        y={y - 10}
                        fill="#fff"
                        fontSize="10"
                        fontFamily="monospace"
                      >
                        {getValueLabel(point.value, lane.type)}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        );
      })}
    </div>
  );
}