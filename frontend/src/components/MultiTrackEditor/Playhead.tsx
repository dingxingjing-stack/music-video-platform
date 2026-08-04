/**
 * Playhead — 播放头（固定在顶部）
 */

interface Props {
  currentTime: number;
  zoom: number;
  scrollLeft: number;
}

export function Playhead({ currentTime, zoom, scrollLeft }: Props) {
  const left = currentTime * zoom - scrollLeft;

  if (left < 0) return null;

  return (
    <div
      className="absolute top-0 bottom-0 w-px bg-[#ff6a10] z-50 pointer-events-none"
      style={{ left: `${left}px` }}
    >
      <div className="absolute -top-1 -left-1.5 w-3 h-3 bg-[#ff6a10] rotate-45 rounded-sm" />
    </div>
  );
}