/**
 * CompingPanel — 多次录制取最佳片段面板
 * 
 * 功能:
 * - 显示多次录音轨道 (Takes)
 * - 片段选择/高亮
 * - 评分系统 (0-5 星)
 * - 可视化时间线
 * - 自动拼接预览
 */

import { useState, useCallback } from 'react';

interface TakeSegment {
  id: string;
  start_time: number;
  end_time: number;
  take_index: number;
  is_selected: boolean;
  rating: number;
  notes?: string;
}

interface CompingSession {
  session_id: string;
  track_name: string;
  takes: TakeSegment[];
  total_duration: number;
  is_compiled: boolean;
}

const TAKE_COLORS = [
  'from-red-500/20 to-red-600/20 border-red-500/30',
  'from-blue-500/20 to-blue-600/20 border-blue-500/30',
  'from-green-500/20 to-green-600/20 border-green-500/30',
  'from-purple-500/20 to-purple-600/20 border-purple-500/30',
  'from-orange-500/20 to-orange-600/20 border-orange-500/30',
];

interface Props {
  onClose: () => void;
}

export function CompingPanel({ onClose }: Props) {
  const [session, setSession] = useState<CompingSession | null>(null);
  const [numTakes, setNumTakes] = useState(3);
  const [isLoading, setIsLoading] = useState(false);

  // 创建 Comping 会话 (Mock)
  const handleCreateSession = useCallback(async () => {
    setIsLoading(true);
    
    // Mock 创建会话
    setTimeout(() => {
      const mockSession: CompingSession = {
        session_id: 'comp_vocal_1',
        track_name: 'Lead Vocal',
        total_duration: 60,
        is_compiled: false,
        takes: Array(numTakes).fill(null).map((_, i) => ({
          id: `take_${i}`,
          start_time: 0,
          end_time: 60,
          take_index: i,
          is_selected: i === 0,
          rating: i === 0 ? 4.5 : 0,
        })),
      };
      setSession(mockSession);
      setIsLoading(false);
    }, 800);
  }, [numTakes]);

  // 选择片段
  const handleSelectSegment = useCallback((segmentId: string) => {
    if (!session) return;
    
    setSession({
      ...session,
      takes: session.takes.map(take => ({
        ...take,
        is_selected: take.id === segmentId ? !take.is_selected : take.is_selected,
      })),
    });
  }, [session]);

  // 评分
  const handleRateSegment = useCallback((segmentId: string, rating: number) => {
    if (!session) return;
    
    setSession({
      ...session,
      takes: session.takes.map(take =>
        take.id === segmentId ? { ...take, rating } : take
      ),
    });
  }, [session]);

  // 编译最佳片段
  const handleCompile = useCallback(async () => {
    if (!session) return;
    
    setIsLoading(true);
    
    // Mock 编译
    setTimeout(() => {
      setSession(prev => prev ? { ...prev, is_compiled: true, compiled_url: 'mock://compiled.wav' } : null);
      setIsLoading(false);
    }, 1500);
  }, [session]);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-5xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎙️ Comping</h2>
            <p className="text-sm text-zinc-400 mt-1">多次录制取最佳片段</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            关闭
          </button>
        </div>

        {!session ? (
          /* 创建会话界面 */
          <div className="text-center py-12">
            <div className="text-5xl mb-4">🎙️</div>
            <h3 className="text-xl font-bold text-white mb-2">创建 Comping 会话</h3>
            <p className="text-zinc-400 mb-6">录制多次后选择最佳片段拼接</p>
            
            <div className="max-w-md mx-auto mb-6">
              <label className="text-xs text-zinc-400 mb-2 block">录音次数</label>
              <input
                type="range"
                min="2"
                max="10"
                value={numTakes}
                onChange={(e) => setNumTakes(Number(e.target.value))}
                className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
              />
              <div className="text-center text-purple-400 font-bold mt-2">{numTakes} 次录音</div>
            </div>
            
            <button
              onClick={handleCreateSession}
              disabled={isLoading}
              className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition disabled:opacity-50"
            >
              {isLoading ? '创建中...' : '创建 Comping 会话'}
            </button>
          </div>
        ) : (
          /* Comping 编辑界面 */
          <div>
            {/* 轨道信息 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-white">{session.track_name}</h3>
                  <p className="text-sm text-zinc-400">
                    {session.takes.length} 次录音 · {session.total_duration.toFixed(1)}秒
                  </p>
                </div>
                <button
                  onClick={handleCompile}
                  disabled={isLoading || !session.takes.some(t => t.is_selected)}
                  className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition disabled:opacity-50"
                >
                  {isLoading ? '编译中...' : '✨ 编译最佳片段'}
                </button>
              </div>
            </div>

            {/* 录音轨道列表 */}
            <div className="space-y-3 mb-6">
              {session.takes.map((take, idx) => (
                <div
                  key={take.id}
                  className={`relative p-4 rounded-xl border-2 transition cursor-pointer ${
                    TAKE_COLORS[idx % TAKE_COLORS.length]
                  } ${take.is_selected ? 'ring-2 ring-purple-500' : ''}`}
                  onClick={() => handleSelectSegment(take.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center text-white font-bold">
                        {idx + 1}
                      </div>
                      <div>
                        <div className="text-white font-medium">Take {idx + 1}</div>
                        <div className="text-xs text-zinc-400">
                          {take.start_time.toFixed(1)}s - {take.end_time.toFixed(1)}s
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      {/* 评分 */}
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map(star => (
                          <button
                            key={star}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRateSegment(take.id, star);
                            }}
                            className={`text-lg transition ${
                              star <= take.rating
                                ? 'text-yellow-400'
                                : 'text-zinc-600 hover:text-yellow-400'
                            }`}
                          >
                            ★
                          </button>
                        ))}
                      </div>
                      
                      {/* 选中状态 */}
                      <div className={`px-3 py-1 rounded text-xs font-medium ${
                        take.is_selected
                          ? 'bg-purple-500 text-white'
                          : 'bg-zinc-700 text-zinc-400'
                      }`}>
                        {take.is_selected ? '✓ 选中' : '未选中'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 时间线可视化 */}
            <div className="p-4 bg-zinc-800/30 rounded-xl">
              <h4 className="text-sm font-medium text-zinc-400 mb-3">📊 时间线</h4>
              <div className="relative h-24 bg-zinc-900 rounded-lg overflow-hidden">
                {/* 选中片段的高亮区域 */}
                {session.takes.filter(t => t.is_selected).map((take, idx) => (
                  <div
                    key={take.id}
                    className={`absolute h-full ${
                      TAKE_COLORS[idx % TAKE_COLORS.length].split(' ')[0]
                    } opacity-50`}
                    style={{
                      left: `${(take.start_time / session.total_duration) * 100}%`,
                      width: `${((take.end_time - take.start_time) / session.total_duration) * 100}%`,
                    }}
                  />
                ))}
                
                {/* 时间刻度 */}
                <div className="absolute bottom-0 left-0 right-0 flex justify-between px-2 text-xs text-zinc-500">
                  {[0, 25, 50, 75, 100].map(pct => (
                    <span key={pct}>{(session.total_duration * pct / 100).toFixed(0)}s</span>
                  ))}
                </div>
              </div>
            </div>

            {/* 编译结果 */}
            {session.is_compiled && (
              <div className="mt-6 p-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="text-2xl">✅</div>
                  <div>
                    <div className="text-green-400 font-bold">编译成功！</div>
                    <div className="text-xs text-zinc-400">
                      已拼接 {session.takes.filter(t => t.is_selected).length} 个最佳片段
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default CompingPanel;