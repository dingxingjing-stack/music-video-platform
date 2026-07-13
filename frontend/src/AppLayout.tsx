import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';

const NAV = [
  { to: '/', label: '工作台', icon: '🏠' },
  { to: '/path-a', label: '路径 A — Suno 风格', icon: '🎵' },
  { to: '/path-b', label: '路径 B — 混合模式', icon: '🎛️' },
  { to: '/path-c', label: '路径 C — 扒带/Remix', icon: '🔊' },
  { to: '/path-d', label: '路径 D — 原创', icon: '✍️' },
  { to: '/community', label: '社区排行榜', icon: '🏆' },
];

const AI_TEAM = [
  {
    name: '总经理',
    icon: '👔',
    color: '#ff6a10',
    desc: '统筹协调',
    status: 'online',
  },
  {
    name: '市场调研员',
    icon: '📊',
    color: '#38bdf8',
    desc: '数据分析',
    status: 'idle',
  },
  {
    name: '财务经理',
    icon: '💰',
    color: '#34d399',
    desc: '预算规划',
    status: 'idle',
  },
  {
    name: '推广专员',
    icon: '📢',
    color: '#f472b6',
    desc: '营销策略',
    status: 'idle',
  },
  {
    name: '运维工程师',
    icon: '🔧',
    color: '#a78bfa',
    desc: '系统监控',
    status: 'idle',
  },
  {
    name: '设计研发',
    icon: '🎨',
    color: '#fb923c',
    desc: 'UI/UX 开发',
    status: 'busy',
  },
  {
    name: '出纳会计',
    icon: '🧾',
    color: '#facc15',
    desc: '收支管理',
    status: 'idle',
  },
];

const STATUS_DOT: Record<string, string> = {
  online: 'bg-[#34d399]',
  idle: 'bg-[#777777]',
  busy: 'bg-[#ff6a10] animate-pulse',
};

export function AppLayout() {
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [teamExpanded, setTeamExpanded] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex h-screen bg-[#121212] text-[#e0e0e0]">
      {/* ===== 汉堡菜单按钮 (移动) ===== */}
      <button
        onClick={() => setMobileMenuOpen(true)}
        className="lg:hidden fixed top-3 left-3 z-50 p-2 bg-[#1e1e1e]/90 backdrop-blur-sm rounded-lg border border-[#2a2a2a] text-white"
        aria-label="打开菜单"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* ===== 移动端遮罩 ===== */}
      {mobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* ===== Left Sidebar ===== */}
      <aside
        className={`${
          sidebarCollapsed ? 'w-16' : 'w-64'
        } ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0 fixed lg:static inset-y-0 left-0 z-50 lg:z-auto flex flex-col border-r border-[#2a2a2a] bg-[#0e0e0e]/95 backdrop-blur-xl transition-all duration-300`}
      >
        {/* Logo */}
        <div className="h-14 flex items-center px-3 gap-2 border-b border-[#2a2a2a]">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="text-[#777777] hover:text-white transition-colors text-lg"
            title={sidebarCollapsed ? '展开' : '收起'}
          >
            {sidebarCollapsed ? '▸' : '◂'}
          </button>
          {!sidebarCollapsed && (
            <span
              className="font-bold text-base gradient-text cursor-pointer truncate"
              onClick={() => navigate('/')}
            >
              MV Studio
            </span>
          )}
          {/* 移动关闭按钮 */}
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="lg:hidden ml-auto text-[#777777] hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {!sidebarCollapsed && (
            <div className="px-3 mb-2 text-[10px] uppercase tracking-widest text-[#555555]">
              功能导航
            </div>
          )}
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              onClick={() => {
                if (window.innerWidth < 768) setSidebarCollapsed(true);
              }}
            >
              {({ isActive }) => (
                <div
                  className={`mx-1.5 px-3 py-2 rounded-lg text-sm flex items-center gap-3 cursor-pointer transition-all ${
                    isActive
                      ? 'bg-gradient-to-r from-[#ff6a10]/20 to-[#ee0979]/10 text-white shadow-sm'
                      : 'text-[#888888] hover:text-white hover:bg-white/5'
                  }`}
                >
                  <span className="text-base flex-shrink-0">{n.icon}</span>
                  {!sidebarCollapsed && <span className="truncate">{n.label}</span>}
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* AI Team Section */}
        <div className="border-t border-[#2a2a2a]">
          <button
            onClick={() => setTeamExpanded(!teamExpanded)}
            className={`w-full flex items-center gap-2 px-3 py-2.5 text-xs transition-colors ${
              sidebarCollapsed ? 'justify-center' : ''
            }`}
          >
            <span className="text-base">🤖</span>
            {!sidebarCollapsed && (
              <>
                <span className="truncate font-medium">AI 员工团队</span>
                <span className="ml-auto text-[#555555]">{teamExpanded ? '▾' : '▸'}</span>
              </>
            )}
          </button>

          {!sidebarCollapsed && teamExpanded && (
            <div className="pb-3 px-2 space-y-1">
              {AI_TEAM.map((member) => (
                <div
                  key={member.name}
                  className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[#1a1a1a] hover:bg-[#222222] cursor-pointer transition-colors group"
                >
                  <span className="text-lg">{member.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium text-[#e0e0e0] truncate">{member.name}</span>
                      <span
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[member.status]}`}
                      />
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-[10px] text-[#555555]">{member.desc}</span>
                      <span
                        className="text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ color: member.color }}
                      >
                        派遣 →
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* 移动端菜单按钮 */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="lg:hidden fixed top-4 left-4 z-40 p-2 bg-[#1e1e1e] rounded-lg border border-[#2a2a2a]"
        >
          ☰
        </button>

        {/* ===== 主内容区 ===== */}
      <main className={`flex-1 overflow-auto transition-all ${
        mobileMenuOpen ? 'lg:ml-64 ml-0' : 'lg:ml-64 ml-0'
      } pt-14 lg:pt-0 pb-20 lg:pb-0`}>
        <Outlet />
      </main>

      {/* ===== 底部导航栏 (移动端) ===== */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0e0e0e]/95 backdrop-blur-xl border-t border-[#2a2a2a] safe-bottom z-30">
        <div className="flex items-center justify-around py-2">
          {NAV.slice(0, 5).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              onClick={() => setMobileMenuOpen(false)}
            >
              {({ isActive }) => (
                <div className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg transition-all ${
                  isActive ? 'text-white' : 'text-[#777777]'
                }`}>
                  <span className="text-xl">{n.icon}</span>
                  <span className="text-[10px] truncate max-w-[60px]">{n.label.split(' — ')[0]}</span>
                </div>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
