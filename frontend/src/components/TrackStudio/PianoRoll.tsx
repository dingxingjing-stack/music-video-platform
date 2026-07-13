/**
 * PianoRoll — Core MIDI editor component for Path D (Original Creation).
 * 
 * Features:
 *   - Grid-based piano roll with time (horizontal) and pitch (vertical)
 *   - Note drawing, selection, dragging, resizing
 *   - Multi-track support with instrument selection
 *   - Playhead for playback preview
 *   - Quantization and snap-to-grid
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import type { MidiNote, MidiProject } from '../../types/trackStudio';

const PPQ = 480; // ticks per quarter note
const MIN_NOTE_DURATION = PPQ / 4; // sixteenth note
const GRID_SNAP = PPQ / 16; // sixteenth note grid

interface PianoRollProps {
  project: MidiProject;
  onProjectChange: (project: MidiProject) => void;
  isPlaying?: boolean;
  currentTick?: number;
}

interface DragState {
  type: 'create' | 'move' | 'resize-left' | 'resize-right';
  noteId?: string;
  startX: number;
  startY: number;
  startTick: number;
  startPitch: number;
  currentX?: number;
  currentY?: number;
  originalNote?: MidiNote;
}

export function PianoRoll({ project, onProjectChange, isPlaying, currentTick = 0 }: PianoRollProps) {
  const [selectedNotes, setSelectedNotes] = useState<string[]>([]);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [scrollX, setScrollX] = useState(0);
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const selectedTrack = useMemo(() => 
    project.tracks[0], 
    [project.tracks]
  );

  // Calculate visible range
  const containerWidth = containerRef.current?.clientWidth || 1200;
  const noteHeight = 20;
  const visiblePitchRange = 84; // ~7 octaves
  const startPitch = 127 - visiblePitchRange;
  const endPitch = 127;

  const ticksPerPixel = useMemo(() => PPQ / (zoom * 100), [zoom]);
  const pixelsPerTick = useMemo(() => 1 / ticksPerPixel, [ticksPerPixel]);
  const totalTicks = useMemo(() => {
    let max = PPQ * 16;
    project.tracks.forEach(track => {
      track.notes.forEach(note => {
        max = Math.max(max, note.startTick + note.durationTicks);
      });
    });
    return Math.ceil(max / PPQ) * PPQ;
  }, [project.tracks]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const newZoom = Math.max(0.25, Math.min(4, zoom * (1 - e.deltaY * 0.001)));
      setZoom(newZoom);
    } else {
      setScrollX(prev => Math.max(0, Math.min(prev + e.deltaY, totalTicks * pixelsPerTick - containerWidth)));
    }
  }, [zoom, totalTicks, pixelsPerTick]);

  const handleMouseDown = useCallback((e: React.MouseEvent, note?: MidiNote) => {
    if (e.button !== 0) return;
    
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const x = e.clientX - rect.left + scrollX;
    const y = e.clientY - rect.top;
    
    const tick = Math.round(x * ticksPerPixel / GRID_SNAP) * GRID_SNAP;
    const pitch = Math.max(0, Math.min(127, Math.floor(endPitch - y / noteHeight)));
    
    if (note) {
      if (e.shiftKey) {
        setSelectedNotes(prev => prev.includes(note.id) 
          ? prev.filter(id => id !== note.id)
          : [...prev, note.id]);
      } else if (!selectedNotes.includes(note.id)) {
        setSelectedNotes([note.id]);
      }
      
      const noteLeft = note.startTick * pixelsPerTick;
      const relativeX = x - noteLeft;
      
      let dragType: 'move' | 'resize-left' | 'resize-right' = 'move';
      if (relativeX < 10) dragType = 'resize-left';
      else if (relativeX > note.durationTicks * pixelsPerTick - 10) dragType = 'resize-right';
      
      setDragState({
        type: dragType,
        noteId: note.id,
        startX: x,
        startY: y,
        startTick: note.startTick,
        startPitch: note.pitch,
        originalNote: { ...note }
      });
    } else {
      setSelectedNotes([]);
      setDragState({
        type: 'create',
        startX: x,
        startY: y,
        startTick: tick,
        startPitch: pitch,
      });
    }
  }, [selectedNotes, selectedTrack, ticksPerPixel, pixelsPerTick, scrollX, endPitch, noteHeight]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragState || !svgRef.current) return;
    
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + scrollX;
    const y = e.clientY - rect.top;
    
    setDragState(prev => prev ? { ...prev, currentX: x, currentY: y } : null);
  }, [dragState, scrollX]);

  const handleMouseUp = useCallback(() => {
    if (!dragState || !selectedTrack) return;
    
    const newProject = { ...project, tracks: project.tracks.map(t => 
      t.id === selectedTrack.id ? { ...t } : t
    )} as MidiProject;
    const trackIndex = newProject.tracks.findIndex(t => t.id === selectedTrack.id);
    if (trackIndex === -1) return;
    
    const track = newProject.tracks[trackIndex];
    const notes = [...track.notes];
    
    if (dragState.type === 'create' && dragState.currentX) {
      const duration = Math.max(MIN_NOTE_DURATION, PPQ / 4);
      const newNote: MidiNote = {
        id: `note-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        pitch: Math.max(0, Math.min(127, dragState.startPitch)),
        velocity: 100,
        startTick: Math.max(0, dragState.startTick),
        durationTicks: duration,
        channel: track.channel,
      };
      notes.push(newNote);
      setSelectedNotes([newNote.id]);
    } else if (dragState.noteId && dragState.originalNote) {
      const noteIndex = notes.findIndex(n => n.id === dragState.noteId);
      if (noteIndex !== -1) {
        const original = dragState.originalNote;
        let newStartTick = original.startTick;
        let newDuration = original.durationTicks;
        let newPitch = original.pitch;
        
        if (dragState.currentX) {
          const deltaX = dragState.currentX - dragState.startX;
          const tickDelta = Math.round(deltaX * ticksPerPixel / GRID_SNAP) * GRID_SNAP;
          
          if (dragState.type === 'move') {
            newStartTick = Math.max(0, original.startTick + tickDelta);
          } else if (dragState.type === 'resize-left') {
            newStartTick = Math.max(0, original.startTick + tickDelta);
            newDuration = Math.max(MIN_NOTE_DURATION, original.durationTicks - tickDelta);
          } else if (dragState.type === 'resize-right') {
            newDuration = Math.max(MIN_NOTE_DURATION, original.durationTicks + tickDelta);
          }
        }
        
        if (dragState.currentY) {
          const deltaY = dragState.startY - dragState.currentY;
          const pitchDelta = Math.floor(deltaY / noteHeight);
          newPitch = Math.max(0, Math.min(127, original.pitch + pitchDelta));
        }
        
        notes[noteIndex] = { ...original, startTick: newStartTick, durationTicks: newDuration, pitch: newPitch };
      }
    }
    
    newProject.tracks[trackIndex] = { ...track, notes };
    newProject.updatedAt = Date.now();
    onProjectChange(newProject);
    setDragState(null);
  }, [dragState, selectedTrack, project, ticksPerPixel, noteHeight, onProjectChange]);

  // Keyboard handlers
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedTrack || selectedNotes.length === 0) return;
      
      const newProject = { ...project, tracks: project.tracks.map(t => 
        t.id === selectedTrack.id ? { ...t } : t
      )} as MidiProject;
      const trackIndex = newProject.tracks.findIndex(t => t.id === selectedTrack.id);
      if (trackIndex === -1) return;
      
      const track = newProject.tracks[trackIndex];
      const notes = [...track.notes];
      let changed = false;
      
      selectedNotes.forEach(noteId => {
        const noteIndex = notes.findIndex(n => n.id === noteId);
        if (noteIndex === -1) return;
        
        const note = { ...notes[noteIndex] };
        
        switch (e.key) {
          case 'Delete':
          case 'Backspace':
            notes.splice(noteIndex, 1);
            changed = true;
            break;
          case 'ArrowUp':
            note.pitch = Math.min(127, note.pitch + (e.shiftKey ? 12 : 1));
            changed = true;
            break;
          case 'ArrowDown':
            note.pitch = Math.max(0, note.pitch - (e.shiftKey ? 12 : 1));
            changed = true;
            break;
          case 'ArrowLeft':
            note.startTick = Math.max(0, note.startTick - (e.shiftKey ? PPQ : GRID_SNAP));
            changed = true;
            break;
          case 'ArrowRight':
            note.startTick += e.shiftKey ? PPQ : GRID_SNAP;
            changed = true;
            break;
          case '[':
            note.durationTicks = Math.max(MIN_NOTE_DURATION, note.durationTicks - GRID_SNAP);
            changed = true;
            break;
          case ']':
            note.durationTicks += GRID_SNAP;
            changed = true;
            break;
        }
        
        if (changed) notes[noteIndex] = note;
      });
      
      if (changed) {
        e.preventDefault();
        newProject.tracks[trackIndex] = { ...track, notes };
        newProject.updatedAt = Date.now();
        onProjectChange(newProject);
        if (e.key === 'Delete' || e.key === 'Backspace') {
          setSelectedNotes([]);
        }
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedTrack, selectedNotes, project, onProjectChange]);

  // Scroll to playhead when playing
  useEffect(() => {
    if (isPlaying && currentTick !== undefined) {
      const playheadX = currentTick * pixelsPerTick;
      if (playheadX < scrollX || playheadX > scrollX + containerWidth) {
        setScrollX(Math.max(0, playheadX - containerWidth / 2));
      }
    }
  }, [isPlaying, currentTick, pixelsPerTick, scrollX, containerWidth]);

  // Render piano keys on left
  const pianoKeys = useMemo(() => {
    const keys = [];
    for (let pitch = endPitch; pitch >= startPitch; pitch--) {
      const noteName = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][pitch % 12];
      const octave = Math.floor(pitch / 12) - 1;
      const isBlack = ['C#', 'D#', 'F#', 'G#', 'A#'].includes(noteName);
      keys.push({ pitch, noteName, octave, isBlack, y: (endPitch - pitch) * noteHeight });
    }
    return keys;
  }, [startPitch, endPitch, noteHeight]);

  // Render notes for selected track
  const renderedNotes = useMemo(() => {
    return selectedTrack.notes.map(note => ({
      ...note,
      x: note.startTick * pixelsPerTick - scrollX,
      width: Math.max(2, note.durationTicks * pixelsPerTick),
      y: (endPitch - note.pitch) * noteHeight,
      height: noteHeight - 1,
      isSelected: selectedNotes.includes(note.id),
    }));
  }, [selectedTrack, selectedNotes, pixelsPerTick, scrollX, endPitch, noteHeight]);

  // Grid pattern
  const gridPattern = useMemo(() => (
    <pattern id="grid" width={PPQ * pixelsPerTick} height={noteHeight * 12} patternUnits="userSpaceOnUse">
      <rect width={PPQ * pixelsPerTick} height={noteHeight * 12} fill="transparent"/>
      <line x1={0} y1={0} x2={0} y2={noteHeight * 12} stroke="#2a2a38" strokeWidth={1} />
            {[PPQ/4, PPQ/2, PPQ*3/4].map(div => (
              <line key={div} x1={div * pixelsPerTick} y1={0} x2={div * pixelsPerTick} y2={noteHeight * 12} stroke="#2a2a38" strokeWidth={0.5} />
            ))}
            {[...Array(7)].map((_, i) => i * 12 * noteHeight).map(y => (
              <line key={y} x1={0} y1={y} x2={PPQ * pixelsPerTick} y2={y} stroke="#2a2a38" strokeWidth={0.5} />
            ))}
    </pattern>
  ), [pixelsPerTick, noteHeight]);

  return (
    <div 
      className="flex h-full bg-[#121212] rounded-xl border border-[#2a2a38] overflow-hidden"
      onWheel={handleWheel}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* Piano Keys Sidebar */}
      <div className="flex-shrink-0 w-40 border-r border-[#2a2a38] bg-[#1f1f1f] relative overflow-hidden">
        {pianoKeys.map(key => (
          <div
            key={key.pitch}
            className={`absolute left-0 right-0 h-[20px] flex items-center justify-center px-2 text-xs font-mono text-[#777777] border-b border-[#2a2a38]/50 ${
              key.isBlack ? 'bg-[#262626] text-[#b0b0b0]' : 'bg-[#1f1f1f]'
            }`}
            style={{ top: key.y }}
          >
            {key.noteName}{key.octave}
          </div>
        ))}
      </div>
      
      {/* Grid & Notes Area */}
      <div className="flex-1 relative" ref={containerRef}>
        <svg 
          ref={svgRef}
          className="absolute inset-0"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          style={{ cursor: dragState ? 'grabbing' : 'crosshair' }}
        >
          <defs>
            {gridPattern}
          </defs>
          <rect 
            width="100%" 
            height="100%" 
            fill="url(#grid)" 
          />
          
          {/* Current bar markers */}
          {[...Array(Math.ceil(totalTicks / (PPQ * 4)))].map((_, bar) => (
            <line
              key={bar}
              x1={bar * PPQ * 4 * pixelsPerTick - scrollX}
              y1={0}
              x2={bar * PPQ * 4 * pixelsPerTick - scrollX}
              y2="100%"
              stroke="#ff6a10"
              strokeWidth={2}
              strokeDasharray="8,4"
            />
          ))}
          
          {/* Playhead */}
          {isPlaying && currentTick !== undefined && (
            <line
              x1={currentTick * pixelsPerTick - scrollX}
              y1={0}
              x2={currentTick * pixelsPerTick - scrollX}
              y2="100%"
              stroke="#ef4444"
              strokeWidth={2}
              strokeDasharray="4,4"
            />
          )}
          
          {/* Notes */}
          {renderedNotes.map(note => (
            <g key={note.id} onMouseDown={e => handleMouseDown(e.nativeEvent as unknown as React.MouseEvent, note)}>
              <rect
                x={note.x}
                y={note.y}
                width={note.width}
                height={note.height}
                rx={2}
                fill={note.isSelected ? '#ff6a10' : `hsl(${note.pitch * 2.8}, 70%, 55%)`}
                stroke={note.isSelected ? '#ff6a10' : 'transparent'}
                strokeWidth={2}
                filter="drop-shadow(0 1px 2px rgba(0,0,0,0.3))"
                className="transition-colors"
              />
            </g>
          ))}
          
          {/* Drag preview */}
          {dragState && dragState.type === 'create' && dragState.currentX && (
            <rect
              x={dragState.startX - scrollX}
              y={(endPitch - dragState.startPitch) * noteHeight}
              width={dragState.currentX - dragState.startX}
              height={noteHeight - 1}
              rx={2}
              fill="rgba(230, 90, 11, 0.5)"
              stroke="#ff6a10"
              strokeWidth={1}
              strokeDasharray="4,4"
            />
          )}
        </svg>
      </div>
    </div>
  );
}