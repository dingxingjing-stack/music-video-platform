import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface WorkItem {
  id: string;
  title: string;
  type: 'audio' | 'midi';
  created_at: string;
  duration: number;
  audio_url?: string;
}

const MOCK_WORKS: WorkItem[] = [
  { id: '1', title: '夏日旋律', type: 'audio', created_at: '2026-07-16', duration: 180, audio_url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3' },
  { id: '2', title: '钢琴练习曲', type: 'midi', created_at: '2026-07-15', duration: 90 },
];

export default function MyWorks() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<'all' | 'audio' | 'midi'>('all');
  const [works] = useState<WorkItem[]>(MOCK_WORKS);

  const filtered = filter === 'all' ? works : works.filter(w => w.type === filter);

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold gradient-text mb-1">💿 我的作品</h1>
      <p className="text-sm text-text-muted mb-6">统一管理你创作的所有音频与 MIDI 作品</p>

      <div className="flex gap-2 mb-6">
        {(['all', 'audio', 'midi'] as const).map(t => (
          <button key={t} onClick={() => setFilter(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              filter === t ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white' : 'bg-bg-elevated text-text-secondary hover:text-white'
            }`}
          >{t === 'all' ? '全部' : t === 'audio' ? '🎵 音频' : '🎹 MIDI'}</button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-20 card-solid">
          <div className="text-5xl mb-4">🎶</div>
          <p className="text-text-secondary mb-2">还没有作品</p>
          <p className="text-sm text-text-muted mb-6">去创作页面生成你的第一个作品吧</p>
          <button onClick={() => navigate('/path-a')}
            className="btn-base px-6 py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg font-medium"
          >🎵 开始创作</button>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map(work => (
            <div key={work.id} className="card-solid p-4 flex items-center gap-4 group">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-orange-500/20 to-pink-500/20 flex items-center justify-center text-lg">
                {work.type === 'audio' ? '🎵' : '🎹'}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-medium truncate">{work.title}</h3>
                <p className="text-xs text-text-muted">{work.created_at} · {work.type === 'audio' ? '音频' : 'MIDI'} · {Math.floor(work.duration / 60)}:{(work.duration % 60).toString().padStart(2, '0')}</p>
              </div>
              <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition">
                {work.audio_url && <button className="btn-base px-3 py-1.5 bg-bg-elevated text-text-secondary hover:text-white rounded-lg text-xs">▶️ 播放</button>}
                <button className="btn-base px-3 py-1.5 bg-bg-elevated text-text-secondary hover:text-white rounded-lg text-xs">⬇️ 下载</button>
                <button className="btn-base px-3 py-1.5 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg text-xs">📢 发布</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}