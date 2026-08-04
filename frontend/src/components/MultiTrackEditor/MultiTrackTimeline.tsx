/**
 * MultiTrackTimeline — Cubase-style 多轨时间轴编辑器
 */

import { useState, useCallback, useRef } from 'react';
import { Track, AudioClip } from '../../types/trackStudio';
import { TimelineHeader } from './TimelineHeader';
import { Playhead } from './Playhead';
import { TrackLane } from './TrackLane';
import { Toolbar, Zoom } from './Toolbar';

interface Props {
  tracks: Track[];
  onTracksChange: (tracks: Track[]) => void;
  onPlay: (time: number) => void;
  onStop: () => void;
  isPlaying: boolean;
  currentTime: number;
}

export function MultiTrackTimeline({
  tracks,
  onTracksChange,
  onPlay,
  onStop,
  isPlaying,
  currentTime,
}: Props) {
  const [zoom, setZoom] = useState<Zoom>({ x: 50, y: 80 });
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollLeft, setScrollLeft] = useState(0);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollLeft(e.currentTarget.scrollLeft);
  }, []);

  const handleAddTrack = useCallback(() => {
    const newTrack: Track = {
      id: `track-${Date.now()}`,
      name: `Track ${tracks.length + 1}`,
      type: 'audio',
      status: 'ready',
      url: null,
      progress: 100,
      color: `hsl(${Math.random() * 360}, 70%, 50%)`,
      clips: [],
      muted: false,
      solo: false,
      armed: false,
      volume: 1,
      pan: 0,
    };
    onTracksChange([...tracks, newTrack]);
  }, [tracks, onTracksChange]);

  const handleDeleteTrack = useCallback((trackId: string) => {
    onTracksChange(tracks.filter(t => t.id !== trackId));
  }, [tracks, onTracksChange]);

  const handleClipChange = useCallback((trackId: string, clipId: string, updates: Partial<AudioClip>) => {
    onTracksChange(tracks.map(track => {
      if (track.id !== trackId || !track.clips) return track;
      return {
        ...track,
        clips: track.clips.map(clip =>
          clip.id === clipId ? { ...clip, ...updates } : clip
        ),
      };
    }));
  }, [tracks, onTracksChange]);

  const handleAddClip = useCallback((trackId: string) => {
    const newClip: AudioClip = {
      id: `clip-${Date.now()}`,
      name: 'Audio Clip',
      startTime: 0,
      duration: 10,
      color: '#3b82f6',
      gain: 0,
      muted: false,
    };
    
    onTracksChange(tracks.map(track => {
      if (track.id !== trackId) return track;
      return {
        ...track,
        clips: [...(track.clips || []), newClip],
      };
    }));
  }, [tracks, onTracksChange]);

  return (
    <div className="flex flex-col h-full">
      <Toolbar
        zoom={zoom}
        onZoomChange={(newZoom) => setZoom(newZoom)}
        onAddTrack={handleAddTrack}
        isPlaying={isPlaying}
        onPlay={() => onPlay(currentTime)}
        onStop={onStop}
      />

      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Timeline Header */}
        <TimelineHeader
          zoom={zoom.x}
          scrollLeft={scrollLeft}
          currentTime={currentTime}
        />

        {/* Playhead (fixed position) */}
        <div className="relative h-0">
          <Playhead
            currentTime={currentTime}
            zoom={zoom.x}
            scrollLeft={scrollLeft}
          />
        </div>

        {/* Track Lanes */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto"
          onScroll={handleScroll}
        >
          <div className="min-w-max">
            {tracks.map((track) => (
              <TrackLane
                key={track.id}
                track={track}
                zoom={zoom}
                isSelected={track.id === selectedTrackId}
                onSelect={() => setSelectedTrackId(track.id)}
                onDelete={() => handleDeleteTrack(track.id)}
                onClipChange={(clipId, updates) => handleClipChange(track.id, clipId, updates)}
                onAddClip={() => handleAddClip(track.id)}
              />
            ))}

            {tracks.length === 0 && (
              <div className="flex items-center justify-center h-32 text-[#777777]">
                <p>点击 "添加轨道" 开始创建多轨工程</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}