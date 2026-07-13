/**
 * 钢琴卷帘编辑器 (Piano Roll)
 * 
 * 功能:
 * - 钢琴键盘 (左侧)
 * - 音符网格区域 (右侧)
 * - 绘制/编辑音符
 * - 选择/移动/删除
 * - 吸附网格
 * - 播放头
 */

import { useState, useRef, useCallback } from 'react';
import { Note, PianoRollState, NoteDuration } from '../types/score';

interface Props {
  notes: Note[];
  onChange?: (notes: Note[]) => void;
  state?: PianoRollState;
  playbackTime?: number;
  width?: number;
  height?: number;
  selectedDuration?: NoteDuration;
}

const KEY_HEIGHT = 20;
const PIXELS_PER_BEAT = 40;
const BEATS_PER_MEASURE = 4;

// 钢琴键盘键名
const OCTAVE_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

export function PianoRoll({ notes, onChange, state, playbackTime, width = 600, height = 400, selectedDuration }: Props) {
  const [selectedNotes, setSelectedNotes] = useState<string[]>(state?.selectedNotes || []);
  const [isDrawing, setIsDrawing] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  
  // 可见的八度范围 (从 C2 到 C7)
  const startOctave = 2;
  const endOctave = 7;
  const totalKeys = (endOctave - startOctave + 1) * 12;
  const keyboardWidth = 60;

  // 音符转 Y 坐标
  const noteToY = useCallback((noteName: string, octave: number): number => {
    const keyIndex = OCTAVE_NOTES.indexOf(noteName);
    const octaveOffset = octave - startOctave;
    const totalIndex = octaveOffset * 12 + (11 - keyIndex); // 反转：高音在上
    return totalIndex * KEY_HEIGHT;
  }, [startOctave]);

  // 时间转 X 坐标
  // const timeToX = useCallback((timeMs: number): number => {
  //   const beats = timeMs / (60000 / 120);
  //   return keyboardWidth + beats * PIXELS_PER_BEAT;
  // }, [keyboardWidth]);

  // X 坐标转时间（未使用，保留供未来扩展）
  // const xToTime = useCallback((x: number): number => {
  //   const gridX = x - keyboardWidth;
  //   const beats = gridX / PIXELS_PER_BEAT;
  //   return beats * (60000 / 120);
  // }, [keyboardWidth]);

  // Y 坐标转音符
  const yToNote = useCallback((y: number): { noteName: string; octave: number } => {
    const keyIndex = Math.floor(y / KEY_HEIGHT);
    const octaveIndex = Math.floor(keyIndex / 12);
    const noteIndex = keyIndex % 12;
    const octave = startOctave + (totalKeys / 12 - 1 - octaveIndex);
    const noteName = OCTAVE_NOTES[11 - noteIndex];
    return { noteName, octave };
  }, [startOctave, totalKeys]);

  // 处理鼠标按下 (绘制音符)
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!svgRef.current) return;
    
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    if (x < keyboardWidth) return; // 点在键盘区域外
    
    setIsDrawing(true);
    const { noteName, octave } = yToNote(y);
    
    const newNote: Note = {
      id: `note-${Date.now()}`,
      noteName: noteName as any,
      octave,
      duration: selectedDuration || 'quarter',
      staffPosition: 3,
      x: 0,
      velocity: 100,
      selected: true
    };
    
    setSelectedNotes([newNote.id]);
    onChange?.([...notes, newNote]);
  };

  // 处理鼠标移动
  const handleMouseMove = () => {
    if (!isDrawing) return;
    // 简化实现
  };

  // 处理鼠标松开
  const handleMouseUp = () => {
    setIsDrawing(false);
  };

  // 渲染钢琴键盘
  const renderKeyboard = () => {
    const keys = [];
    let y = 0;
    
    for (let octave = endOctave; octave >= startOctave; octave--) {
      for (let i = OCTAVE_NOTES.length - 1; i >= 0; i--) {
        const noteName = OCTAVE_NOTES[i];
        const isBlack = noteName.includes('#');
        const isC = noteName === 'C';
        
        keys.push(
          <g key={`${octave}-${noteName}`}>
            <rect
              x={0}
              y={y}
              width={keyboardWidth}
              height={KEY_HEIGHT}
              fill={isBlack ? '#333' : '#e0e0e0'}
              stroke={isC ? '#ff6a10' : '#555'}
              strokeWidth={isC ? 2 : 1}
              className="cursor-pointer hover:opacity-80"
            />
            {isC && (
              <text
                x={keyboardWidth - 15}
                y={y + KEY_HEIGHT / 2 + 4}
                fontSize="10"
                fill="#ff6a10"
              >
                C{octave}
              </text>
            )}
          </g>
        );
        y += KEY_HEIGHT;
      }
    }
    
    return keys;
  };

  // 渲染音符
  const renderNotes = () => {
    return notes.map(note => {
      const y = noteToY(note.noteName, note.octave);
      const x = keyboardWidth + note.x * PIXELS_PER_BEAT;
      const isSelected = selectedNotes.includes(note.id);
      
      // 音符颜色
      const isBlackKey = note.noteName.includes('#');
      const noteColor = isBlackKey ? '#ff6a10' : '#38bdf8';
      
      return (
        <g
          key={note.id}
          onClick={() => {
            setSelectedNotes([note.id]);
          }}
          className="cursor-pointer"
        >
          {/* 音符矩形 */}
          <rect
            x={x}
            y={y + 2}
            width={PIXELS_PER_BEAT * 0.8}
            height={KEY_HEIGHT - 4}
            fill={isSelected ? noteColor + '80' : noteColor}
            stroke={isSelected ? '#fff' : 'none'}
            strokeWidth="2"
            rx="4"
            className="hover:opacity-80"
          />
          
          {/* 音符名称 */}
          <text
            x={x + 4}
            y={y + KEY_HEIGHT / 2 + 4}
            fontSize="10"
            fill="#fff"
          >
            {note.noteName}{note.octave}
          </text>
        </g>
      );
    });
  };

  // 渲染网格线
  const renderGrid = () => {
    const lines = [];
    const measures = 8; // 显示 8 个小节
    
    // 垂直网格线 (每拍)
    for (let i = 0; i <= measures * BEATS_PER_MEASURE; i++) {
      const x = keyboardWidth + i * PIXELS_PER_BEAT;
      const isMeasure = i % BEATS_PER_MEASURE === 0;
      
      lines.push(
        <line
          key={`v-${i}`}
          x1={x}
          y1={0}
          x2={x}
          y2={totalKeys * KEY_HEIGHT}
          stroke={isMeasure ? '#444' : '#2a2a2a'}
          strokeWidth={isMeasure ? 1.5 : 1}
        />
      );
    }
    
    // 水平网格线 (每个键)
    for (let i = 0; i <= totalKeys; i++) {
      const y = i * KEY_HEIGHT;
      lines.push(
        <line
          key={`h-${i}`}
          x1={keyboardWidth}
          y1={y}
          x2={keyboardWidth + measures * BEATS_PER_MEASURE * PIXELS_PER_BEAT}
          y2={y}
          stroke="#2a2a2a"
          strokeWidth="1"
        />
      );
    }
    
    return lines;
  };

  // 渲染播放头
  const renderPlaybackHead = () => {
    if (playbackTime === undefined) return null;
    
    // 简化实现：固定位置
    const beats = playbackTime / (60000 / 120);
    const x = keyboardWidth + beats * PIXELS_PER_BEAT;
    return (
      <line
        x1={x}
        y1={0}
        x2={x}
        y2={totalKeys * KEY_HEIGHT}
        stroke="#ff6a10"
        strokeWidth="2"
      />
    );
  };

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="bg-[#121212] rounded-lg cursor-crosshair"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* 钢琴键盘 */}
      {renderKeyboard()}
      
      {/* 网格 */}
      {renderGrid()}
      
      {/* 音符 */}
      {renderNotes()}
      
      {/* 播放头 */}
      {renderPlaybackHead()}
    </svg>
  );
}