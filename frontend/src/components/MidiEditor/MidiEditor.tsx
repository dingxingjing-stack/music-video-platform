/**
 * MIDI 播放引擎 - 使用 Web Audio API 合成播放 MIDI 音符
 * 
 * 当 Tone.js 可用时，会自动使用 Tone.Synth 以获取更好的音色；
 * 否则使用 Web Audio API 基础振荡器作为 fallback。
 */
function playMidiWithToneJS(track: MidiTrack, tempo: number) {
  const noteDuration = 60 / tempo; // 每拍秒数
  const tickDuration = noteDuration / 480; // 假设 480 PPQ
  
  // 检查 Tone.js 是否可用
  const hasToneJS = typeof (window as any).Tone !== 'undefined';
  
  if (hasToneJS) {
    // 使用 Tone.js 播放 (需要安装 tone npm 包)
    try {
      const Tone = (window as any).Tone;
      const synth = new Tone.Synth().toDestination();
      const now = Tone.now();
      
      track.notes.forEach(note => {
        const startTime = now + note.startTick * tickDuration;
        const duration = note.durationTicks * tickDuration;
        const freq = 440 * Math.pow(2, (note.pitch - 69) / 12);
        
        synth.triggerAttackRelease(freq, duration, startTime, note.velocity / 127);
      });
      
      console.log('[Tone.js] Playing MIDI:', track.notes.length, 'notes');
      return;
    } catch (e) {
      console.warn('[Tone.js] Error, falling back to Web Audio:', e);
    }
  }
  
  // Fallback: 使用 Web Audio API
  try {
    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const now = audioCtx.currentTime;
    
    track.notes.forEach(note => {
      const startTime = now + note.startTick * tickDuration;
      const duration = note.durationTicks * tickDuration;
      const freq = 440 * Math.pow(2, (note.pitch - 69) / 12);
      
      // 创建振荡器
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      
      osc.type = 'triangle'; // 三角波接近 MIDI 音色
      osc.frequency.value = freq;
      
      gain.gain.setValueAtTime(0, startTime);
      gain.gain.linearRampToValueAtTime(0.3 * (note.velocity / 127), startTime + 0.01);
      gain.gain.setValueAtTime(0.3 * (note.velocity / 127), startTime + duration - 0.05);
      gain.gain.linearRampToValueAtTime(0, startTime + duration);
      
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      
      osc.start(startTime);
      osc.stop(startTime + duration);
    });
    
    // 播放完成后自动关闭 AudioContext
    const maxEnd = Math.max(...track.notes.map(n => (n.startTick + n.durationTicks) * tickDuration));
    setTimeout(() => {
      audioCtx.close();
    }, (maxEnd * 1000) + 500);
    
    console.log('[Web Audio] Playing MIDI:', track.notes.length, 'notes');
  } catch (e) {
    console.error('[Web Audio] Failed to play MIDI:', e);
  }
}

import { useState, useCallback } from 'react';
import { MidiTrack, MidiNote, getInstrumentByProgram } from '../../types/trackStudio';
import { MidiToolbar } from './MidiToolbar';
import { PianoRoll } from './PianoRoll';

interface Props {
  track: MidiTrack;
  onTrackChange: (track: MidiTrack) => void;
}

function generateNoteId(): string {
  return `note-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function MidiEditor({ track, onTrackChange }: Props) {
  const [zoom, setZoom] = useState<{ x: number; y: number }>({ x: 0.2, y: 20 });
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [tempo, setTempo] = useState(120);
  const [isPlaying, setIsPlaying] = useState(false);

  // 处理音符变更
  const handleSelectNote = useCallback((noteId: string | null) => {
    setSelectedNoteId(noteId);
  }, []);

  const handleDeleteNote = useCallback((noteId: string) => {
    onTrackChange({
      ...track,
      notes: track.notes.filter((note) => note.id !== noteId),
    });
    if (selectedNoteId === noteId) {
      setSelectedNoteId(null);
    }
  }, [track, onTrackChange, selectedNoteId]);

  const handleAddNote = useCallback((pitch: number, startTick: number) => {
    const newNote: MidiNote = {
      id: generateNoteId(),
      pitch,
      velocity: 100,
      startTick,
      durationTicks: 240, // 半拍
      channel: track.channel,
    };
    onTrackChange({
      ...track,
      notes: [...track.notes, newNote],
    });
  }, [track, onTrackChange]);

  const handlePlay = useCallback(() => {
    setIsPlaying(true);
    // 使用 Tone.js 播放 MIDI
    playMidiWithToneJS(track, tempo);
    // 模拟播放完成 (实际应该监听 Tone.js 播放结束事件)
    setTimeout(() => setIsPlaying(false), 3000);
  }, [track, tempo]);

  const handleStop = useCallback(() => {
    setIsPlaying(false);
  }, []);

  const handleInstrumentChange = useCallback((program: number) => {
    onTrackChange({
      ...track,
      instrument: program,
    });
  }, [track, onTrackChange]);

  const instrument = getInstrumentByProgram(track.instrument);

  return (
    <div className="flex-1 flex flex-col bg-[#121212] overflow-hidden">
      <MidiToolbar
        zoom={zoom}
        onZoomChange={setZoom}
        tempo={tempo}
        onTempoChange={setTempo}
        onPlay={handlePlay}
        onStop={handleStop}
        isPlaying={isPlaying}
        instrumentName={instrument?.name || 'Unknown'}
        onInstrumentChange={handleInstrumentChange}
      />

      <PianoRoll
        track={track}
        zoom={zoom}
        selectedNoteId={selectedNoteId}
        onSelectNote={handleSelectNote}
        onDeleteNote={handleDeleteNote}
        onAddNote={handleAddNote}
      />
    </div>
  );
}