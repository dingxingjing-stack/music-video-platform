/**
 * PianoRoll — MIDI 音符编辑（钢琴卷帘）
 */

import { useCallback, useRef } from 'react';
import { MidiTrack } from '../../types/trackStudio';

interface Zoom {
  x: number; // px per tick
  y: number; // px per note
}

interface Props {
  track: MidiTrack;
  zoom: Zoom;
  selectedNoteId: string | null;
  onSelectNote: (noteId: string | null) => void;
  onDeleteNote: (noteId: string) => void;
  onAddNote: (pitch: number, startTick: number) => void;
}

const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const OCTAVES = 11; // 0-10
const TOTAL_PIANO_KEYS = OCTAVES * 12 + 1; // 0-127

function getNoteName(pitch: number): string {
  const noteName = NOTES[pitch % 12];
  const octave = Math.floor(pitch / 12) - 1;
  return `${noteName}${octave}`;
}

function isBlackKey(pitch: number): boolean {
  const noteInOctave = pitch % 12;
  return [1, 3, 6, 8, 10].includes(noteInOctave);
}

export function PianoRoll({
  track,
  zoom,
  selectedNoteId,
  onSelectNote,
  onDeleteNote,
  onAddNote,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 处理网格点击（添加音符）
  const handleGridClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 计算对应的音高和起始位置
    const pitch = Math.floor(y / zoom.y);
    const startTick = Math.floor(x / zoom.x);

    if (pitch >= 0 && pitch < TOTAL_PIANO_KEYS && startTick >= 0) {
      onAddNote(pitch, startTick);
    }
  }, [zoom, onAddNote]);

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Piano Keys (左侧) */}
      <div className="w-20 flex-shrink-0 border-r border-[#2a2a2a] bg-[#1e1e1e] overflow-hidden">
        {Array.from({ length: TOTAL_PIANO_KEYS }).map((_, i) => {
          const pitch = TOTAL_PIANO_KEYS - 1 - i;
          const isBlack = isBlackKey(pitch);
          const noteName = getNoteName(pitch);

          return (
            <div
              key={pitch}
              className={`flex items-center justify-end pr-1 text-xs border-b border-[#2a2a2a] ${
                isBlack ? 'bg-[#333333] text-[#999999]' : 'bg-[#e0e0e0] text-[#333333]'
              }`}
              style={{ height: `${zoom.y}px` }}
            >
              {noteName}
            </div>
          );
        })}
      </div>

      {/* Grid (右侧) */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-[#121212] relative"
        onClick={handleGridClick}
      >
        {/* Horizontal grid lines */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(to bottom, #2a2a2a 1px, transparent 1px)`,
            backgroundSize: `100% ${zoom.y}px`,
          }}
        />

        {/* Vertical grid lines (every beat) */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(to right, #2a2a2a 1px, transparent 1px)`,
            backgroundSize: `${zoom.x * 480}px 100%`,
          }}
        />

        {/* Notes */}
        {track.notes.map((note) => {
          const width = note.durationTicks * zoom.x;
          const left = note.startTick * zoom.x;
          const top = (TOTAL_PIANO_KEYS - 1 - note.pitch) * zoom.y;
          const isSelected = note.id === selectedNoteId;

          return (
            <div
              key={note.id}
              className={`absolute rounded-sm cursor-pointer transition-all
                ${isSelected
                  ? 'bg-gradient-to-r from-orange-500 to-pink-500 ring-2 ring-white z-10'
                  : 'bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-400 hover:to-purple-400'
                }`}
              style={{
                left: `${left}px`,
                top: `${top + 1}px`,
                width: `${Math.max(width, 10)}px`,
                height: `${zoom.y - 2}px`,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onSelectNote(note.id);
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onSelectNote(note.id);
                onDeleteNote(note.id);
              }}
              title={`${getNoteName(note.pitch)} (vel: ${note.velocity})`}
            />
          );
        })}
      </div>
    </div>
  );
}