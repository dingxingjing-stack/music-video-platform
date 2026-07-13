/**
 * 五线谱组件 (Staff Notation)
 * 
 * 功能:
 * - 渲染五线谱线
 * - 显示音符 (全音符、二分音符、四分音符等)
 * - 显示调号、节拍号
 * - 显示小节线
 * - 支持附点、连音线
 */

import { Note, StaffConfig, NoteDuration } from '../types/score';

interface Props {
  config: StaffConfig;
  width?: number;
  height?: number;
  onNoteClick?: (note: Note) => void;
  onNoteDoubleCick?: (note: Note) => void;
}

// 音符 SVG 路径
const NOTE_PATHS: Record<NoteDuration, string> = {
  'whole': 'M 0,0 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 z',
  'half': 'M 0,0 L 0,-20 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 L 0,-20 z',
  'quarter': 'M 0,0 L 0,-20 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 L 0,-20 L 0,0 z',
  'eighth': 'M 0,0 L 0,-20 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 L 0,-20 L 0,0 M 0,-20 L 12,-18 L 12,-28 L 0,-20',
  'sixteenth': 'M 0,0 L 0,-20 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 L 0,-20 L 0,0 M 0,-20 L 12,-18 L 12,-28 L 0,-20 M 0,-24 L 12,-22 L 12,-32 L 0,-24',
  'thirty-second': 'M 0,0 L 0,-20 c 0,-8 8,-12 16,-12 c 8,0 16,4 16,12 c 0,8 -8,12 -16,12 c -8,0 -16,-4 -16,-12 L 0,-20 L 0,0 M 0,-20 L 12,-18 L 12,-28 L 0,-20 M 0,-24 L 12,-22 L 12,-32 L 0,-24 M 0,-28 L 12,-26 L 12,-36 L 0,-28'
};

// 变音记号
const ACCIDENTAL_SYMBOLS = {
  'natural': '♮',
  'sharp': '♯',
  'flat': '♭',
  'double-sharp': '𝄪',
  'double-flat': '𝄫'
};

export function ScoreStaff({ config, width = 800, height = 200, onNoteClick, onNoteDoubleCick }: Props) {
  // 五线谱参数
  const staffTop = 40;
  const lineSpacing = 10;
  const measureWidth = 100;

  // 渲染五线谱线
  const renderStaffLines = (measureNumber: number) => {
    const x = measureNumber * measureWidth + 20;
    const lines = [];
    
    for (let i = 0; i < 5; i++) {
      const y = staffTop + i * lineSpacing;
      lines.push(
        <line
          key={i}
          x1={x}
          y1={y}
          x2={x + measureWidth - 20}
          y2={y}
          stroke="#444"
          strokeWidth="1"
        />
      );
    }
    return lines;
  };

  // 渲染小节线
  const renderBarLine = (measureNumber: number) => {
    const x = measureNumber * measureWidth + 20;
    return (
      <line
        x1={x}
        y1={staffTop}
        x2={x}
        y2={staffTop + 4 * lineSpacing}
        stroke="#666"
        strokeWidth="2"
      />
    );
  };

  // 计算音符 Y 坐标
  const getNoteY = (staffPosition: number): number => {
    // staffPosition: 1=底线，5=顶线
    const centerY = staffTop + 2 * lineSpacing; // 中央 C (第三间)
    return centerY - (staffPosition - 3) * (lineSpacing / 2);
  };

  // 渲染音符
  const renderNote = (note: Note, measureNumber: number) => {
    const x = measureNumber * measureWidth + 40 + note.x;
    const y = getNoteY(note.staffPosition);
    const isSelected = note.selected;

    return (
      <g
        key={note.id}
        onClick={() => onNoteClick?.(note)}
        onDoubleClick={() => onNoteDoubleCick?.(note)}
        className="cursor-pointer"
        style={{ opacity: isSelected ? 0.6 : 1 }}
      >
        {/* 变音记号 */}
        {note.accidental && (
          <text
            x={x - 12}
            y={y + 4}
            fontSize="14"
            fill="#e0e0e0"
          >
            {ACCIDENTAL_SYMBOLS[note.accidental]}
          </text>
        )}

        {/* 符头 */}
        <path
          d={NOTE_PATHS[note.duration]}
          fill={note.duration === 'whole' ? 'none' : '#e0e0e0'}
          stroke="#e0e0e0"
          strokeWidth="2"
          transform={`translate(${x}, ${y}) scale(0.8)`}
        />

        {/* 符干 (二分音符及更短时值) */}
        {['quarter', 'eighth', 'sixteenth', 'thirty-second'].includes(note.duration) && (
          <line
            x1={x + 12}
            y1={y}
            x2={x + 12}
            y2={y - 40}
            stroke="#e0e0e0"
            strokeWidth="1.5"
          />
        )}

        {/* 附点 */}
        {note.dotted && (
          <circle
            cx={x + 18}
            cy={y + 2}
            r="2"
            fill="#e0e0e0"
          />
        )}

        {/* 连接线 (连音线) */}
        {note.tied && (
          <path
            d={`M ${x + 8} ${y - 2} Q ${x + 20} ${y - 10} ${x + 32} ${y - 2}`}
            stroke="#e0e0e0"
            strokeWidth="1.5"
            fill="none"
          />
        )}

        {/* 选择高亮 */}
        {isSelected && (
          <circle
            cx={x + 8}
            cy={y + 2}
            r="20"
            stroke="#ff6a10"
            strokeWidth="2"
            fill="none"
          />
        )}
      </g>
    );
  };

  // 渲染节拍号
  const renderTimeSignature = (measureNumber: number) => {
    const measure = config.measures[measureNumber];
    if (!measure?.timeSignature && measureNumber > 0) return null;

    const timeSig = measure?.timeSignature || config.timeSignature;
    const [top, bottom] = timeSig.split('/');
    const x = measureNumber * measureWidth + 30;
    const y = staffTop + 2 * lineSpacing;

    return (
      <text
        x={x}
        y={y + 10}
        fontSize="24"
        fontWeight="bold"
        fill="#e0e0e0"
      >
        {top}
        <tspan x={x} y={y + 25}>{bottom}</tspan>
      </text>
    );
  };

  // 渲染调号
  const renderKeySignature = (measureNumber: number) => {
    const measure = config.measures[measureNumber];
    if (!measure?.keySignature && measureNumber > 0) return null;

    const keySig = measure?.keySignature || config.keySignature;
    // 简化实现：只显示文字
    const x = measureNumber * measureWidth + 70;
    const y = staffTop - 5;

    return (
      <text
        x={x}
        y={y}
        fontSize="12"
        fill="#888"
      >
        {keySig}调
      </text>
    );
  };

  // 渲染小节号
  const renderMeasureNumber = (measureNumber: number) => {
    return (
      <text
        x={measureNumber * measureWidth + 5}
        y={staffTop - 10}
        fontSize="10"
        fill="#666"
      >
        {measureNumber + 1}
      </text>
    );
  };

  return (
    <svg
      width={width}
      height={height}
      className="bg-[#1e1e1e] rounded-lg"
    >
      {/* 渲染所有小节 */}
      {config.measures.map((measure, idx) => (
        <g key={idx}>
          {/* 小节线 */}
          {renderBarLine(idx)}
          
          {/* 五线谱线 */}
          {renderStaffLines(idx)}
          
          {/* 小节号 */}
          {renderMeasureNumber(idx)}
          
          {/* 节拍号 */}
          {renderTimeSignature(idx)}
          
          {/* 调号 */}
          {renderKeySignature(idx)}
          
          {/* 音符 */}
          {measure.notes.map(note => renderNote(note, idx))}
        </g>
      ))}
    </svg>
  );
}