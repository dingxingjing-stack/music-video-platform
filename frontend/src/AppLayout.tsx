import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useUserGrayStatus } from './hooks/useUserGrayStatus';
import { BetaConsentModal } from './components/BetaConsentModal';
import { useSound } from './context/SoundContext';

// 公测导航 — 普通创作大厅（全开放）
const NAV_OPEN = [
  { to: '/', label: '工作台', icon: '🏠', group: 'open' },
  { to: '/path-a', label: 'AI 作曲', icon: '🎵', group: 'open' },
  { to: '/path-b', label: '混合模式', icon: '🎛️', group: 'open' },
  { to: '/path-c', label: '扒带 Remix', icon: '🔊', group: 'open' },
  { to: '/path-d', label: '原创编曲', icon: '✍️', group: 'open' },
  { to: '/community', label: '社区排行榜', icon: '🏆', group: 'open' },
  { to: '/my-works', label: '我的作品', icon: '💿', group: 'open' },
];

// 灰度测试专区（仅资深测试用户可见）
const NAV_GRAY = [
  { to: '/path-a?feature=mv', label: 'MV 生成', icon: '🎬', feature: 'mv_generate' },
  { to: '/path-d?feature=collab', label: '实时协作', icon: '🤝', feature: 'ws_collab' },
  { to: '/path-a?feature=hf', label: 'HF 高级模型', icon: '🧠', feature: 'hf_models' },
  { to: '/path-a?feature=subtitle', label: '字幕识别', icon: '📝', feature: 'subtitle' },
  { to: '/path-a?feature=publish', label: '一键发布', icon: '📢', feature: 'oneclick_publish' },
];

const STATUS_DOT: Record<string, string> = {
  online: 'bg-[#34d399]',
  idle: 'bg-[#777777]',
  busy: 'bg-[#ff6a10] animate-pulse',
};

const AI_TEAM = [
  { name: '总经理', icon: '👔', color: '#ff6a10', desc: '统筹协调', status: 'online' },
  { name: '市场调研员', icon: '📊', color: '#38bdf8', desc: '数据分析', status: 'idle' },
  { name: '财务经理', icon: '💰', color: '#34d399', desc: '预算规划', status: 'idle' },
  { name: '推广专员', icon: '📢', color: '#f472b6', desc: '营销策略', status: 'idle' },
  { name: '运维工程师', icon: '🔧', color: '#a78bfa', desc: '系统监控', status: 'idle' },
  { name: '设计研发', icon: '🎨', color: '#fb923c', desc: 'UI/UX 开发', status: 'busy' },
  { name: '出纳会计', icon: '🧾', color: '#facc15', desc: '收支管理', status: 'idle' },
];

export function AppLayout() {
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { status } = useUserGrayStatus('beta_user');
  const { muted, toggle } = useSound();

  // 合并导航：普通用户只看 NAV_OPEN，灰度用户加 NAV_GRAY
  const allNav = status.isGray ? [...NAV_OPEN, ...NAV_GRAY] : NAV_OPEN;

  return (
    <div className="flex h-screen bg-[#121212] text-[#e0e0e0]">
      {/* 公测规则弹窗 */}
      <BetaConsentModal />

      {/* 汉堡菜单 (移动) */}
      <button onClick={() => setMobileMenuOpen(true)} className="lg:hidden fixed top-3 left-3 z-50 p-2 bg-[#1e1e1e]/90 backdrop-blur-sm rounded-lg border border-[#2a2a2a] text-white" aria-label="打开菜单">
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
      </button>

      {/* 移动遮罩 */}
      {mobileMenuOpen && <div className="lg:hidden fixed inset-0 bg-black/50 z-40" onClick={() => setMobileMenuOpen(false)} />}

      {/* 侧边栏 */}
      <aside className={`${sidebarCollapsed ? 'w-16' : 'w-64'} ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 fixed lg:static inset-y-0 left-0 z-50 lg:z-auto flex flex-col border-r border-[#2a2a2a] bg-[#0e0e0e]/95 backdrop-blur-xl transition-all duration-300`}>
        {/* Logo */}
        <div className="h-14 flex items-center px-3 gap-2 border-b border-[#2a2a2a]">
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="text-[#777777] hover:text-white transition-colors text-lg" title={sidebarCollapsed ? '展开' : '收起'}>{sidebarCollapsed ? '▸' : '◂'}</button>
          {!sidebarCollapsed && (
            <span className="font-bold text-base gradient-text cursor-pointer truncate" onClick={() => navigate('/')}>Zyvexo</span>
          )}
          <button onClick={() => setMobileMenuOpen(false)} className="lg:hidden ml-auto text-[#777777] hover:text-white">✕</button>
        </div>

        {/* 公测标识 Badge */}
        {!sidebarCollapsed && (
          <div className="px-3 py-2 border-b border-[#2a2a2a]">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gradient-to-r from-[#ff6a10]/10 to-[#ee0979]/10 border border-[#ff6a10]/20 text-[10px] font-medium text-[#ff6a10]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#ff6a10] animate-pulse" />
              公测测试版 v2.0
            </div>
          </div>
        )}

        {/* 导航 */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {!sidebarCollapsed && <div className="px-4 mb-2 text-[10px] uppercase tracking-widest text-[#555555]">🎵 创作大厅</div>}
          {allNav.slice(0, NAV_OPEN.length).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} onClick={() => { if (window.innerWidth < 768) setMobileMenuOpen(false); }}>
              {({ isActive }) => (
                <div className={`mx-2 px-3 py-2.5 rounded-lg text-sm flex items-center gap-3 cursor-pointer transition-all duration-200 ease-out ${isActive ? 'bg-gradient-to-r from-[#ff6a10]/20 to-[#ee0979]/10 text-white shadow-sm' : 'text-[#888888] hover:text-white hover:bg-white/5'}`}>
                  <span className="text-base flex-shrink-0">{n.icon}</span>
                  {!sidebarCollapsed && <span className="truncate">{n.label}</span>}
                </div>
              )}
            </NavLink>
          ))}

          {/* 灰度测试专区（仅灰度用户可见） */}
          {status.isGray && (
            <>
              {!sidebarCollapsed && <div className="px-3 mb-2 mt-4 text-[10px] uppercase tracking-widest text-[#ff6a10]">🔓 灰度专区</div>}
              {NAV_GRAY.map((n) => (
                <NavLink key={n.to} to={n.to} onClick={() => { if (window.innerWidth < 768) setMobileMenuOpen(false); }}>
                  {({ isActive }) => (
                    <div className={`mx-1.5 px-3 py-2 rounded-lg text-sm flex items-center gap-3 cursor-pointer transition-all ${isActive ? 'bg-[#ff6a10]/10 text-[#ff6a10]' : 'text-[#888888] hover:text-[#ff6a10] hover:bg-[#ff6a10]/5'}`}>
                      <span className="text-base flex-shrink-0">{n.icon}</span>
                      {!sidebarCollapsed && <span className="truncate">{n.label}</span>}
                    </div>
                  )}
                </NavLink>
              ))}
            </>
          )}
        </nav>

        {/* 灰度状态指示器 */}
        {!sidebarCollapsed && (
          <div className="px-3 py-2 border-t border-[#2a2a2a]">
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a]">
              <span className={`w-2 h-2 rounded-full ${status.isGray ? 'bg-[#ff6a10]' : 'bg-[#34d399]'}`} />
              <span className="text-[11px] text-[#888888] truncate">
                {status.isGray ? '资深测试用户' : '普通创作者'}
              </span>
              {!status.isGray && (
                <span className="ml-auto text-[10px] text-[#555555]">额度 {status.dailyCredits - status.usedToday}/{status.dailyCredits}</span>
              )}
            </div>
          </div>
        )}

        {/* 音效开关 */}
        {!sidebarCollapsed && (
          <div className="px-3 pt-2 pb-1">
            <button onClick={toggle} className="flex items-center gap-2 text-[11px] text-[#888888] hover:text-white transition w-full">
              <span className="text-sm">{muted ? '🔇' : '🔊'}</span>
              <span>音效{muted ? '已关' : '已开'}</span>
            </button>
          </div>
        )}

      </aside>

      {/* 主内容区 */}
      <main className="flex-1 overflow-auto pt-14 lg:pt-0 pb-20 lg:pb-0">
        <Outlet />
      </main>

      {/* 移动底部导航 — 隐藏付费入口，仅显示创作大厅 */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0e0e0e]/95 backdrop-blur-xl border-t border-[#2a2a2a] z-30">
        <div className="flex items-center justify-around py-2">
          {NAV_OPEN.slice(0, 5).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} onClick={() => setMobileMenuOpen(false)}>
              {({ isActive }) => (
                <div className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg transition-all ${isActive ? 'text-white' : 'text-[#777777]'}`}>
                  <span className="text-xl">{n.icon}</span>
                  <span className="text-[10px] truncate max-w-[60px]">{n.label.split(' ')[0]}</span>
                </div>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

// AI Team Section 组件（简化）
function AITeamSection({ collapsed }: { collapsed: boolean }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <button onClick={() => setExpanded(!expanded)} className={`w-full flex items-center gap-2 px-3 py-2.5 text-xs transition-colors ${collapsed ? 'justify-center' : ''}`}>
        <span className="text-base">🤖</span>
        {!collapsed && (<><span className="truncate font-medium">AI 员工团队</span><span className="ml-auto text-[#555555]">{expanded ? '▾' : '▸'}</span></>)}
      </button>
      {!collapsed && expanded && (
        <div className="pb-3 px-2 space-y-1">
          {AI_TEAM.map((member) => (
            <div key={member.name} className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[#1a1a1a] hover:bg-[#222222] cursor-pointer transition-colors group">
              <span className="text-lg">{member.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-[#e0e0e0] truncate">{member.name}</span>
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[member.status]}`} />
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[10px] text-[#555555]">{member.desc}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
