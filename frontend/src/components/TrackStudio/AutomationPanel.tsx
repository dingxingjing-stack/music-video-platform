/**
 * AutomationPanel — 自动化曲线面板
 */

import { useState, useCallback } from 'react';
import { AutomationEditor } from './AutomationEditor';
import { createDefaultLanes, AutomationLane } from '../../types/automation';

interface Zoom {
  x: number;
  y: number;
}

interface Props {
  onClose: () => void;
}

export function AutomationPanel({ onClose }: Props) {
  const [lanes, setLanes] = useState<AutomationLane[]>(createDefaultLanes());
  const [zoom, setZoom] = useState<Zoom>({ x: 50, y: 120 });

  const handleLanesChange = useCallback((newLanes: AutomationLane[]) => {
    setLanes(newLanes);
  }, []);

  const toggleLaneVisibility = useCallback((type: string) => {
    setLanes(lanes.map(lane =>
      lane.type === type ? { ...lane, visible: !lane.visible } : lane
    ));
  }, [lanes]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[800px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">📈 自动化曲线</h2>
            <p className="text-xs text-[#777777]">绘制音量、声像、效果参数随时间变化</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* 轨道可见性切换 */}
        <div className="flex items-center gap-2 p-3 bg-[#121212] border-b border-[#2a2a2a] flex-wrap">
          <span className="text-xs text-[#777777] mr-2">显示:</span>
          {lanes.map(lane => (
            <button
              key={lane.type}
              onClick={() => toggleLaneVisibility(lane.type)}
              className={`px-2 py-1 text-xs rounded transition-colors border ${
                lane.visible
                  ? 'bg-orange-500/20 border-orange-500 text-orange-500'
                  : 'bg-[#2a2a2a] border-[#3a3a3a] text-[#777777]'
              }`}
              style={{ borderColor: lane.visible ? lane.color : undefined }}
            >
              {lane.label}
            </button>
          ))}
        </div>

        {/* 编辑器 */}
        <div className="flex-1 overflow-auto">
          <AutomationEditor
            lanes={lanes}
            onLanesChange={handleLanesChange}
            zoom={zoom}
            duration={60}
          />
        </div>

        {/* 底部控制 */}
        <div className="p-4 border-t border-[#2a2a2a] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#777777]">缩放:</span>
            <button
              onClick={() => setZoom(z => ({ ...z, x: Math.max(20, z.x / 1.5) }))}
              className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs"
            >
              −
            </button>
            <span className="text-xs text-[#e0e0e0]">{zoom.x.toFixed(0)} px/s</span>
            <button
              onClick={() => setZoom(z => ({ ...z, x: Math.min(200, z.x * 1.5) }))}
              className="px-2 py-1 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-xs"
            >
              +
            </button>
          </div>
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