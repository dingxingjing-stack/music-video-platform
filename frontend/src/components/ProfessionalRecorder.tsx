/**
 * 专业录音组件
 * 
 * 功能:
 * - 多轨录音控制
 * - 实时电平表
 * - 输入监听
 * - MIDI 录音
 * - 量化设置
 */

import { useState, useEffect } from 'react';
import { RecordingEngine } from '../utils/RecordingEngine';
import { RecordingTrackConfig, LevelMeterData } from '../types/vst';

interface Props {
  onRecordingComplete?: (session: any) => void;
}

export function ProfessionalRecorder({ onRecordingComplete }: Props) {
  const [engine] = useState(() => new RecordingEngine());
  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [levelMeters, setLevelMeters] = useState<Map<string, LevelMeterData>>(new Map());
  const [tracks, setTracks] = useState<RecordingTrackConfig[]>([
    {
      trackId: 'track-1',
      name: '人声',
      inputType: 'mic',
      inputChannel: 1,
      monitoringEnabled: true,
      monitoringType: 'input',
      recordArmed: true,
      recordMonitor: true,
      inputGain: 0,
      phaseReverse: false,
      phantomPower: false
    },
    {
      trackId: 'track-2',
      name: '吉他',
      inputType: 'instrument',
      inputChannel: 1,
      monitoringEnabled: true,
      monitoringType: 'input',
      recordArmed: false,
      recordMonitor: true,
      inputGain: 0,
      phaseReverse: false,
      phantomPower: false
    }
  ]);

  const [midiMode, setMidiMode] = useState(false);
  const [midiEvents, setMidiEvents] = useState<any[]>([]);

  // 初始化
  useEffect(() => {
    engine.initialize();

    // 监听电平表事件
    const handleLevelMeter = (e: Event) => {
      const event = e as CustomEvent<LevelMeterData>;
      setLevelMeters(prev => new Map(prev.set(event.detail.trackId, event.detail)));
    };

    window.addEventListener('levelmeter', handleLevelMeter);
    return () => {
      window.removeEventListener('levelmeter', handleLevelMeter);
      engine.dispose();
    };
  }, []);

  // 更新录音时间
  useEffect(() => {
    let interval: number;
    if (isRecording) {
      interval = window.setInterval(() => {
        setRecordingTime(prev => prev + 100);
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isRecording]);

  // 开始录音
  const startRecording = async () => {
    await engine.startRecording(tracks.filter(t => t.recordArmed));
    setIsRecording(true);
    setRecordingTime(0);
    setLevelMeters(new Map());
  };

  // 停止录音
  const stopRecording = async () => {
    const session = await engine.stopRecording();
    setIsRecording(false);
    
    if (session && onRecordingComplete) {
      onRecordingComplete(session);
    }
  };

  // 开始 MIDI 录音
  const startMidiRecording = async () => {
    await engine.startMidiRecording();
    setIsRecording(true);
    setRecordingTime(0);
  };

  // 停止 MIDI 录音
  const stopMidiRecording = () => {
    const events = engine.stopMidiRecording();
    setIsRecording(false);
    setMidiEvents(events);
    console.log(`录制了 ${events.length} 个 MIDI 事件`);
  };

  // 切换轨道录音准备
  const toggleRecordArm = (trackId: string) => {
    setTracks(prev =>
      prev.map(t =>
        t.trackId === trackId ? { ...t, recordArmed: !t.recordArmed } : t
      )
    );
  };

  // 切换监听
  const toggleMonitoring = (trackId: string) => {
    setTracks(prev =>
      prev.map(t =>
        t.trackId === trackId ? { ...t, monitoringEnabled: !t.monitoringEnabled } : t
      )
    );
  };

  // 设置输入增益
  const setInputGain = (trackId: string, gain: number) => {
    setTracks(prev =>
      prev.map(t =>
        t.trackId === trackId ? { ...t, inputGain: gain } : t
      )
    );
  };

  // 格式化时间
  const formatTime = (ms: number) => {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const centiseconds = Math.floor((ms % 1000) / 10);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${centiseconds.toString().padStart(2, '0')}`;
  };

  // 获取电平表颜色
  const getMeterColor = (db: number) => {
    if (db > -1) return 'bg-red-500';
    if (db > -6) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full">
      {/* 顶部控制栏 */}
      <div className="flex items-center gap-4 mb-4">
        {/* 录音按钮 */}
        <button
          onClick={isRecording ? stopRecording : startRecording}
          className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl transition ${
            isRecording
              ? 'bg-red-500 hover:bg-red-600 animate-pulse'
              : 'bg-red-600 hover:bg-red-500'
          }`}
        >
          {isRecording ? '⏹️' : '⏺️'}
        </button>

        {/* 播放按钮 */}
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl transition ${
            isPlaying ? 'bg-green-500 hover:bg-green-600' : 'bg-green-600 hover:bg-green-500'
          }`}
        >
          {isPlaying ? '⏸️' : '▶️'}
        </button>

        {/* 时间显示 */}
        <div className="bg-gray-800 rounded px-4 py-2 font-mono text-2xl text-orange-500 min-w-[150px] text-center">
          {formatTime(recordingTime)}
        </div>

        {/* MIDI 模式切换 */}
        <button
          onClick={() => setMidiMode(!midiMode)}
          className={`px-4 py-2 rounded transition ${
            midiMode ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'
          } text-white`}
        >
          🎹 MIDI: {midiMode ? 'ON' : 'OFF'}
        </button>

        {/* MIDI 录音 */}
        {midiMode && (
          <button
            onClick={isRecording ? stopMidiRecording : startMidiRecording}
            className={`px-4 py-2 rounded transition ${
              isRecording ? 'bg-red-500' : 'bg-purple-600 hover:bg-purple-500'
            } text-white`}
          >
            {isRecording ? '停止 MIDI' : '录制 MIDI'}
          </button>
        )}
      </div>

      {/* 轨道列表 */}
      <div className="space-y-2">
        {tracks.map(track => {
          const meter = levelMeters.get(track.trackId);
          const level = meter?.inputLevel || -60;
          const levelPercent = Math.max(0, Math.min(100, ((level + 60) / 60) * 100));

          return (
            <div
              key={track.trackId}
              className={`bg-gray-800 rounded p-3 flex items-center gap-4 ${
                track.recordArmed ? 'border-l-4 border-red-500' : ''
              }`}
            >
              {/* 轨道名称 */}
              <div className="w-24 text-white font-medium">{track.name}</div>

              {/* 录音准备 */}
              <button
                onClick={() => toggleRecordArm(track.trackId)}
                className={`w-8 h-8 rounded flex items-center justify-center transition ${
                  track.recordArmed
                    ? 'bg-red-500 hover:bg-red-600'
                    : 'bg-gray-700 hover:bg-gray-600'
                }`}
                title="录音准备"
              >
                {track.recordArmed ? '🔴' : '⚪'}
              </button>

              {/* 监听开关 */}
              <button
                onClick={() => toggleMonitoring(track.trackId)}
                className={`w-8 h-8 rounded flex items-center justify-center transition ${
                  track.monitoringEnabled
                    ? 'bg-blue-500 hover:bg-blue-600'
                    : 'bg-gray-700 hover:bg-gray-600'
                }`}
                title="监听"
              >
                🎧
              </button>

              {/* 输入增益 */}
              <div className="flex-1">
                <label className="text-gray-400 text-xs block mb-1">输入增益</label>
                <input
                  type="range"
                  min="-20"
                  max="20"
                  step="1"
                  value={track.inputGain}
                  onChange={(e) => setInputGain(track.trackId, parseFloat(e.target.value))}
                  className="w-full"
                />
                <div className="text-gray-500 text-xs text-right">{track.inputGain > 0 ? '+' : ''}{track.inputGain} dB</div>
              </div>

              {/* 电平表 */}
              <div className="w-32">
                <div className="flex items-center gap-1 mb-1">
                  <span className="text-gray-500 text-xs">-60</span>
                  <div className="flex-1 h-2 bg-gray-700 rounded overflow-hidden">
                    <div
                      className={`h-full transition-all ${getMeterColor(level)}`}
                      style={{ width: `${levelPercent}%` }}
                    />
                  </div>
                  <span className="text-gray-500 text-xs">0</span>
                </div>
                <div className="text-gray-400 text-xs text-right font-mono">
                  {level.toFixed(1)} dB
                  {meter?.clipping && <span className="text-red-500 ml-2">🔴 CLIP</span>}
                </div>
              </div>

              {/* 输入类型 */}
              <select
                value={track.inputType}
                onChange={(e) => {
                  const newType = e.target.value as any;
                  setTracks(prev =>
                    prev.map(t =>
                      t.trackId === track.trackId ? { ...t, inputType: newType } : t
                    )
                  );
                }}
                className="bg-gray-700 text-white px-3 py-1 rounded text-sm"
              >
                <option value="mic">🎤 麦克风</option>
                <option value="instrument">🎸 乐器</option>
                <option value="line">📀 线路</option>
              </select>
            </div>
          );
        })}
      </div>

      {/* MIDI 事件列表 (MIDI 模式) */}
      {midiMode && midiEvents.length > 0 && (
        <div className="mt-4 bg-gray-800 rounded p-3">
          <h4 className="text-white font-semibold mb-2">录制的 MIDI 事件 ({midiEvents.length})</h4>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {midiEvents.slice(0, 20).map((event, i) => (
              <div key={i} className="text-gray-400 text-xs font-mono">
                {event.type} - Note: {event.note} - Velocity: {event.velocity} @ {event.time}ms
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 量化设置 */}
      <div className="mt-4 bg-gray-800 rounded p-3">
        <h4 className="text-white font-semibold mb-3">量化设置</h4>
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="text-gray-400 text-xs block mb-1">网格类型</label>
            <select className="w-full bg-gray-700 text-white px-2 py-1 rounded text-sm">
              <option>1/4</option>
              <option>1/8</option>
              <option selected>1/16</option>
              <option>1/32</option>
            </select>
          </div>
          <div>
            <label className="text-gray-400 text-xs block mb-1">强度</label>
            <input
              type="range"
              min="0"
              max="100"
              defaultValue="100"
              className="w-full"
            />
            <div className="text-gray-500 text-xs text-right">100%</div>
          </div>
          <div>
            <label className="text-gray-400 text-xs block mb-1">Swing</label>
            <input
              type="range"
              min="0"
              max="100"
              defaultValue="0"
              className="w-full"
            />
            <div className="text-gray-500 text-xs text-right">0%</div>
          </div>
          <div className="flex items-end">
            <button className="w-full bg-purple-600 hover:bg-purple-500 text-white py-1 rounded text-sm">
              应用量化
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}