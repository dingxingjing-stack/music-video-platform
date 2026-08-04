/**
 * TimelineHeader — 时间尺组件
 */

interface Props {
  zoom: number; // px per second
  scrollLeft: number;
  currentTime: number;
}

export function TimelineHeader({ zoom, scrollLeft, currentTime }: Props) {
  // 计算可见区域的时间范围
  const visibleWidth = typeof window !== 'undefined' ? window.innerWidth : 1200;
  const startTime = Math.max(0, scrollLeft / zoom);
  const endTime = (scrollLeft + visibleWidth) / zoom;
  const duration = endTime - startTime;

  // 动态确定刻度间隔
  let interval: number;
  if (duration > 60) interval = 10;
  else if (duration > 30) interval = 5;
  else if (duration > 10) interval = 2;
  else interval = 1;

  const markers = [];
  const startMark = Math.floor(startTime / interval) * interval;
  
  for (let t = startMark; t <= endTime + interval; t += interval) {
    const left = t * zoom;
    markers.push(
      <div key={t} className="absolute bottom-0" style={{ left }}>
        <div className="w-px h-3 bg-[#3a3a3a]" />
        <span className="absolute bottom-4 left-1/2 -translate-x-1/2 text-xs text-[#777777] whitespace-nowrap">
          {formatTime(t)}
        </span>
      </div>
    );
  }

  return (
    <div className="relative h-10 bg-[#1a1a1a] border-b border-[#2a2a2a] mb-2">
      {/* 主刻度 */}
      {markers}
      
      {/* 播放头位置指示 */}
      <div 
        className="absolute top-0 bottom-0 w-0.5 bg-[#ff6a10] z-10"
        style={{ left: currentTime * zoom }}
      />
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);
  return `${m}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
}