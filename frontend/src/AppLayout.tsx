import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useUserGrayStatus } from './hooks/useUserGrayStatus';
import { BetaConsentModal } from './components/BetaConsentModal';
import { useSound } from './context/SoundContext';
import { useAuth } from './context/AuthContext';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { Under13BlockedModal } from './components/Under13BlockedModal';
import { getUserAge } from './hooks/useUserAge';
import { useTranslation } from './i18n/useTranslation';

// 主导航 — 新产品结构：Home / Create Music / Voice Clone / Audio Tools / My Creations / Settings
const NAV_MAIN = [
  { to: '/', labelKey: 'nav.home', fallback: 'Home', icon: '⌂', end: true },
  { to: '/create', labelKey: 'nav.createMusic', fallback: 'Create Music', icon: '♪' },
  { to: '/voice-clone', labelKey: 'nav.voiceClone', fallback: 'Voice Clone', icon: '◐' },
  { to: '/audio-tools', labelKey: 'nav.audioTools', fallback: 'Audio Tools', icon: '⬢' },
  { to: '/my-works', labelKey: 'nav.myCreations', fallback: 'My Creations', icon: '♡' },
  { to: '/settings', labelKey: 'nav.settings', fallback: 'Settings', icon: '⚙' },
];

// 灰度专区（已移除 MV，保留协作等）
const NAV_GRAY = [
  { to: '/path-d?feature=collab', labelKey: 'nav.liveCollab', fallback: 'Live Collaboration', icon: '◈', feature: 'ws_collab' },
  { to: '/path-a?feature=hf', labelKey: 'nav.hfModels', fallback: 'HF Models', icon: '⬡', feature: 'hf_models' },
  { to: '/path-a?feature=subtitle', labelKey: 'nav.subtitles', fallback: 'Subtitle', icon: '≡', feature: 'subtitle' },
];

export function AppLayout() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    async function checkAge() {
      const age = await getUserAge();
      if (age !== null && age < 13) setBlocked(true);
    }
    checkAge();
  }, []);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  if (blocked) return <Under13BlockedModal />;
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { status } = useUserGrayStatus('beta_user');
  const { muted, toggle } = useSound();
  const { isLoggedIn, user, setShowLogin, logout } = useAuth();

  const tr = (k: string, fallback: string) => {
    const v = t(k);
    return v === k ? fallback : v;
  };

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-[#e0e0e0] selection:bg-[#ff6a10]/30">
      <BetaConsentModal />

      {/* 移动端汉堡 */}
      <button onClick={() => setMobileMenuOpen(true)} className="lg:hidden fixed top-3 left-3 z-50 p-2.5 bg-[#141414]/90 backdrop-blur rounded-xl border border-[#262626] text-white shadow-lg" aria-label="Open menu">
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
      </button>

      {mobileMenuOpen && <div className="lg:hidden fixed inset-0 bg-black/60 z-40" onClick={() => setMobileMenuOpen(false)} />}

      {/* 侧边栏 */}
      <aside className={`${sidebarCollapsed ? 'w-[68px]' : 'w-[264px]'} ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 fixed lg:static inset-y-0 left-0 z-50 lg:z-auto flex flex-col border-r border-[#1f1f1f] bg-[#0f0f0f]/95 backdrop-blur-xl transition-all duration-300`}>
        {/* Logo */}
        <div className="h-[56px] flex items-center px-3 gap-2 border-b border-[#1f1f1f] shrink-0">
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="w-8 h-8 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#888888] hover:text-white flex items-center justify-center transition" title={sidebarCollapsed ? 'Expand' : 'Collapse'}>
            <span className="text-[11px] font-bold tracking-widest">{sidebarCollapsed ? '››' : '‹‹'}</span>
          </button>
          {!sidebarCollapsed && (
            <span className="font-black text-[17px] tracking-tight cursor-pointer" onClick={() => navigate('/')}>
              <span className="bg-gradient-to-r from-[#ff6a10] to-[#ee0979] bg-clip-text text-transparent">Zyvexo</span>
              <span className="ml-1.5 text-[10px] font-medium tracking-[0.14em] text-[#555555] align-middle">STUDIO</span>
            </span>
          )}
          <button onClick={() => setMobileMenuOpen(false)} className="lg:hidden ml-auto w-8 h-8 flex items-center justify-center text-[#666666] hover:text-white">✕</button>
        </div>

        {!sidebarCollapsed && (
          <div className="px-3 py-3 border-b border-[#1f1f1f]">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#1a1a1a] border border-[#262626] text-[10px] font-medium tracking-widest text-[#888888]">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              AI MUSIC STUDIO
            </div>
          </div>
        )}

        {/* 主导航 */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {!sidebarCollapsed && <div className="px-4 mb-2 text-[10px] font-semibold tracking-[0.14em] text-[#4a4a4a] uppercase">Navigate</div>}
          <div className="space-y-0.5 px-2">
            {NAV_MAIN.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} onClick={() => { if (window.innerWidth < 768) setMobileMenuOpen(false); }}>
                {({ isActive }) => (
                  <div className={`px-3 py-2.5 rounded-xl text-sm flex items-center gap-3 cursor-pointer transition-all ${isActive ? 'bg-white text-[#0a0a0a] font-medium shadow' : 'text-[#8a8a8a] hover:text-white hover:bg-[#1a1a1a]'}`}>
                    <span className={`w-7 h-7 rounded-lg flex items-center justify-center text-[13px] shrink-0 ${isActive ? 'bg-[#0a0a0a] text-white' : 'bg-[#1a1a1a] border border-[#262626]'}`}>{n.icon}</span>
                    {!sidebarCollapsed && <span className="truncate">{tr(n.labelKey, n.fallback)}</span>}
                  </div>
                )}
              </NavLink>
            ))}
          </div>

          {status.isGray && NAV_GRAY.length > 0 && (
            <>
              {!sidebarCollapsed && <div className="px-4 mb-2 mt-6 text-[10px] font-semibold tracking-[0.14em] text-[#4a4a4a] uppercase">Experimental</div>}
              <div className="space-y-0.5 px-2">
                {NAV_GRAY.map((n) => (
                  <NavLink key={n.to} to={n.to} onClick={() => { if (window.innerWidth < 768) setMobileMenuOpen(false); }}>
                    {({ isActive }) => (
                      <div className={`px-3 py-2 rounded-lg text-sm flex items-center gap-3 cursor-pointer transition-all ${isActive ? 'bg-[#ff6a10]/10 text-[#ff6a10]' : 'text-[#6a6a6a] hover:text-[#ff6a10] hover:bg-[#1a1a1a]'}`}>
                        <span className="text-base shrink-0">{n.icon}</span>
                        {!sidebarCollapsed && <span className="truncate text-xs">{tr(n.labelKey, n.fallback)}</span>}
                      </div>
                    )}
                  </NavLink>
                ))}
              </div>
            </>
          )}
        </nav>

        {/* 底部用户区 */}
        {!sidebarCollapsed && (
          <div className="px-3 py-3 border-t border-[#1f1f1f] space-y-2.5">
            {isLoggedIn ? (
              <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-xl bg-[#141414] border border-[#262626]">
                <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                <span className="text-xs text-[#b0b0b0] truncate">{user?.username || user?.email}</span>
                <button onClick={logout} className="ml-auto text-[11px] text-[#666666] hover:text-red-400 transition">Logout</button>
              </div>
            ) : (
              <button onClick={() => setShowLogin(true)} className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-white text-[#0a0a0a] text-sm font-semibold rounded-xl hover:bg-[#ededed] transition">
                <span>Log in</span>
              </button>
            )}
            <LanguageSwitcher />
            <button onClick={toggle} className="flex items-center gap-2 text-[11px] text-[#6a6a6a] hover:text-white transition w-full">
              <span>{muted ? '◑' : '◐'}</span>
              <span>{muted ? tr('nav.soundOff','Sound off') : tr('nav.soundOn','Sound on')}</span>
            </button>
          </div>
        )}
      </aside>

      {/* 主内容 */}
      <main className="flex-1 overflow-auto pt-14 lg:pt-0">
        <Outlet />
      </main>

      {/* 移动底部导航 - 仅显示主导航前5项 */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0f0f0f]/95 backdrop-blur-xl border-t border-[#1f1f1f] z-30">
        <div className="flex items-center justify-around py-1.5">
          {NAV_MAIN.slice(0, 5).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              {({ isActive }) => (
                <div className={`flex flex-col items-center gap-0.5 px-2.5 py-1.5 rounded-xl transition ${isActive ? 'text-white bg-white/10' : 'text-[#6a6a6a]'}`}>
                  <span className="text-[14px] leading-none">{n.icon}</span>
                  <span className="text-[9px] font-medium tracking-wide max-w-[52px] truncate">{tr(n.labelKey, n.fallback).split(' ')[0]}</span>
                </div>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
