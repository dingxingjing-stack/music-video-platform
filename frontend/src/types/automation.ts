/**
 * 自动化曲线类型定义
 */

export type AutomationType = 'volume' | 'pan' | 'eq_low' | 'eq_mid' | 'eq_high' | 'reverb_wet' | 'delay_wet';

export interface AutomationPoint {
  id: string;
  time: number; // seconds
  value: number; // 0-1 (or -1 to 1 for pan)
}

export interface AutomationLane {
  type: AutomationType;
  label: string;
  color: string;
  points: AutomationPoint[];
  visible: boolean;
  locked: boolean;
}

export interface AutomationSession {
  lanes: AutomationLane[];
  zoom: {
    x: number; // px per second
    y: number; // px per lane
  };
  currentTime: number;
  isPlaying: boolean;
}

export const AUTOMATION_COLORS: Record<AutomationType, string> = {
  volume: '#3b82f6',    // blue
  pan: '#8b5cf6',       // purple
  eq_low: '#22c55e',    // green
  eq_mid: '#eab308',    // yellow
  eq_high: '#f97316',   // orange
  reverb_wet: '#ec4899', // pink
  delay_wet: '#06b6d4', // cyan
};

export const AUTOMATION_LABELS: Record<AutomationType, string> = {
  volume: '音量',
  pan: '声像',
  eq_low: 'EQ 低频',
  eq_mid: 'EQ 中频',
  eq_high: 'EQ 高频',
  reverb_wet: '混响',
  delay_wet: '延迟',
};

export function createDefaultLanes(): AutomationLane[] {
  return [
    {
      type: 'volume',
      label: AUTOMATION_LABELS.volume,
      color: AUTOMATION_COLORS.volume,
      points: [
        { id: 'p1', time: 0, value: 1 },
        { id: 'p2', time: 30, value: 1 },
      ],
      visible: true,
      locked: false,
    },
    {
      type: 'pan',
      label: AUTOMATION_LABELS.pan,
      color: AUTOMATION_COLORS.pan,
      points: [
        { id: 'p1', time: 0, value: 0 },
        { id: 'p2', time: 30, value: 0 },
      ],
      visible: false,
      locked: false,
    },
    {
      type: 'eq_low',
      label: AUTOMATION_LABELS.eq_low,
      color: AUTOMATION_COLORS.eq_low,
      points: [
        { id: 'p1', time: 0, value: 0.5 },
        { id: 'p2', time: 30, value: 0.5 },
      ],
      visible: false,
      locked: false,
    },
    {
      type: 'eq_mid',
      label: AUTOMATION_LABELS.eq_mid,
      color: AUTOMATION_COLORS.eq_mid,
      points: [
        { id: 'p1', time: 0, value: 0.5 },
        { id: 'p2', time: 30, value: 0.5 },
      ],
      visible: false,
      locked: false,
    },
    {
      type: 'eq_high',
      label: AUTOMATION_LABELS.eq_high,
      color: AUTOMATION_COLORS.eq_high,
      points: [
        { id: 'p1', time: 0, value: 0.5 },
        { id: 'p2', time: 30, value: 0.5 },
      ],
      visible: false,
      locked: false,
    },
    {
      type: 'reverb_wet',
      label: AUTOMATION_LABELS.reverb_wet,
      color: AUTOMATION_COLORS.reverb_wet,
      points: [
        { id: 'p1', time: 0, value: 0.3 },
        { id: 'p2', time: 30, value: 0.3 },
      ],
      visible: false,
      locked: false,
    },
    {
      type: 'delay_wet',
      label: AUTOMATION_LABELS.delay_wet,
      color: AUTOMATION_COLORS.delay_wet,
      points: [
        { id: 'p1', time: 0, value: 0.2 },
        { id: 'p2', time: 30, value: 0.2 },
      ],
      visible: false,
      locked: false,
    },
  ];
}

export function generatePointId(): string {
  return `ap-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}