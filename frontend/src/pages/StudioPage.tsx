/**
 * 录音室页面
 * 
 * 整合:
 * - 专业录音
 * - VST 插件管理
 * - 多轨编辑
 * - MIDI 编辑器
 */

import { useState } from 'react';
import { ProfessionalRecorder } from '../components/ProfessionalRecorder';
import { VSTPluginManager } from '../components/VSTPluginManager';
import { PianoRoll } from '../components/PianoRoll';
import { ScoreStaff } from '../components/ScoreStaff';
import { Note } from '../types/score';

export function StudioPage() {
  const [activeView, setActiveView] = useState<'record' | 'edit' | 'mix'>('record');
  const [showPluginManager, setShowPluginManager] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [staffConfig, setStaffConfig] = useState({
    type: 'staff' as const,
    tempo: 120,
    measures: Array(8).fill(null).map((_, i) => ({ number: i, notes: [] as Note[] })),
    keySignature: 'C' as const,
    timeSignature: '4/4' as const
  });

  return (
    <div className="h-screen bg-gray-950 flex flex-col">
      {/* 顶部工具栏 */}
      <div className="bg-gray-900 border-b border-gray-800 p-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-white font-bold text-xl">🎙️ 录音室</h1>
          
          {/* 视图切换 */}
          <div className="flex bg-gray-800 rounded p-1">
            <button
              onClick={() => setActiveView('record')}
              className={`px-4 py-2 rounded text-sm transition ${
                activeView === 'record'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              🎤 录音
            </button>
            <button
              onClick={() => setActiveView('edit')}
              className={`px-4 py-2 rounded text-sm transition ${
                activeView === 'edit'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              ✏️ 编辑
            </button>
            <button
              onClick={() => setActiveView('mix')}
              className={`px-4 py-2 rounded text-sm transition ${
                activeView === 'mix'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              🎚️ 混音
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* VST 插件管理器开关 */}
          <button
            onClick={() => setShowPluginManager(!showPluginManager)}
            className={`px-4 py-2 rounded text-sm transition ${
              showPluginManager
                ? 'bg-purple-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            🎛️ VST 插件
          </button>

          {/* 导出按钮 */}
          <button className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm transition">
            💾 导出
          </button>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：主工作区 */}
        <div className="flex-1 p-4 overflow-y-auto">
          {activeView === 'record' && (
            <ProfessionalRecorder
              onRecordingComplete={(session) => {
                console.log('录音完成:', session);
              }}
            />
          )}

          {activeView === 'edit' && (
            <div className="space-y-4">
              <div className="bg-gray-900 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">钢琴卷帘编辑器</h3>
                <PianoRoll
                  notes={notes}
                  onChange={setNotes}
                  height={400}
                  selectedDuration="quarter"
                />
              </div>

              <div className="bg-gray-900 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">五线谱视图</h3>
                <ScoreStaff
                  notes={notes}
                  config={staffConfig}
                />
              </div>
            </div>
          )}

          {activeView === 'mix' && (
            <div className="bg-gray-900 rounded-lg p-4">
              <h3 className="text-white font-semibold mb-3">混音台</h3>
              <div className="grid grid-cols-8 gap-2">
                {Array(8).fill(null).map((_, i) => (
                  <div key={i} className="bg-gray-800 rounded p-3 flex flex-col items-center">
                    <div className="text-gray-400 text-xs mb-2">轨道 {i + 1}</div>
                    
                    {/* 推子 */}
                    <div className="h-48 w-12 bg-gray-700 rounded relative mb-2">
                      <div
                        className="absolute bottom-0 left-0 right-0 bg-orange-500 rounded transition-all"
                        style={{ height: `${50 + Math.random() * 30}%` }}
                      />
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-8 h-4 bg-gray-600 rounded cursor-pointer hover:bg-gray-500" />
                      </div>
                    </div>

                    {/* 电平表 */}
                    <div className="w-4 h-24 bg-gray-700 rounded overflow-hidden flex flex-col-reverse">
                      <div
                        className="bg-gradient-to-t from-green-500 via-yellow-500 to-red-500 transition-all"
                        style={{ height: `${30 + Math.random() * 40}%` }}
                      />
                    </div>

                    {/* 按钮 */}
                    <div className="flex gap-1 mt-2">
                      <button className="w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white">
                        M
                      </button>
                      <button className="w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white">
                        S
                      </button>
                      <button className="w-6 h-6 bg-red-600 hover:bg-red-500 rounded text-xs text-white">
                        ●
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 右侧：VST 插件管理器 (可选显示) */}
        {showPluginManager && (
          <div className="w-96 border-l border-gray-800 bg-gray-900">
            <VSTPluginManager
              onPluginLoad={(plugin) => {
                console.log('插件已加载:', plugin);
              }}
            />
          </div>
        )}
      </div>

      {/* 底部：运输控制 */}
      <div className="bg-gray-900 border-t border-gray-800 p-3 flex items-center justify-center gap-4">
        <button className="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-full flex items-center justify-center text-white">
          ⏮️
        </button>
        <button className="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-full flex items-center justify-center text-white">
          ⏹️
        </button>
        <button className="w-12 h-12 bg-orange-500 hover:bg-orange-600 rounded-full flex items-center justify-center text-white text-xl">
          ▶️
        </button>
        <button className="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-full flex items-center justify-center text-white">
          ⏸️
        </button>
        <button className="w-10 h-10 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center text-white">
          ⏺️
        </button>
        
        <div className="ml-8 text-orange-500 font-mono text-xl">
          00:00:00
        </div>
        
        <div className="ml-8 text-gray-400 text-sm">
          BPM: <input type="number" defaultValue="120" className="w-16 bg-gray-800 text-white px-2 py-1 rounded" />
        </div>
      </div>
    </div>
  );
}