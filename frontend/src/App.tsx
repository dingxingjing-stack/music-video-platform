import { Routes, Route } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AppLayout } from './AppLayout';
import { ConsentGuard, GrayRoute } from './components/RouteGuards';
import { PageTransition } from './components/PageTransition';

// 路由级懒加载
const Landing = lazy(() => import('./pages/Landing').then(m => ({ default: m.Landing })));
const TrackStudio = lazy(() => import('./pages/TrackStudio').then(m => ({ default: m.TrackStudio })));
const PathAPage = lazy(() => import('./pages/PathAPage').then(m => ({ default: m.PathAPage })));
const PathBPage = lazy(() => import('./pages/PathBPage').then(m => ({ default: m.PathBPage })));
const PathCPage = lazy(() => import('./pages/PathCPage').then(m => ({ default: m.PathCPage })));
const PathDPage = lazy(() => import('./pages/PathDPage').then(m => ({ default: m.PathDPage })));
const Community = lazy(() => import('./pages/Community').then(m => ({ default: m.Community })));
const CommunityFeed = lazy(() => import('./pages/CommunityFeed').then(m => ({ default: m.CommunityFeed })));
const Feed = lazy(() => import('./pages/Feed').then(m => ({ default: m.Feed })));
const Profile = lazy(() => import('./pages/Profile').then(m => ({ default: m.Profile })));
const StockLibrary = lazy(() => import('./pages/StockLibrary'));
const MyWorks = lazy(() => import('./pages/MyWorks'));

const Loading = () => (
  <div className="flex items-center justify-center h-screen bg-[#121212]">
    <div className="text-[#555555] animate-pulse">加载中...</div>
  </div>
);

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* 落地首页 — 独立展示，无侧边栏，无需协议 */}
        <Route path="/landing" element={<Landing />} />

        {/* 主应用路由 — 侧边栏布局 + 公测协议守卫 */}
        <Route element={<AppLayout />}>
          {/* 全开放功能 — 需同意协议 */}
          <Route path="/" element={<ConsentGuard><PageTransition><TrackStudio /></PageTransition></ConsentGuard>} />
          <Route path="/path-a" element={<ConsentGuard><PageTransition><PathAPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-b" element={<ConsentGuard><PageTransition><PathBPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-c" element={<ConsentGuard><PageTransition><PathCPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-d" element={<ConsentGuard><PageTransition><PathDPage /></PageTransition></ConsentGuard>} />
          <Route path="/community" element={<ConsentGuard><PageTransition><Community /></PageTransition></ConsentGuard>} />
          <Route path="/community-feed" element={<ConsentGuard><PageTransition><CommunityFeed /></PageTransition></ConsentGuard>} />
          <Route path="/my-works" element={<ConsentGuard><PageTransition><MyWorks /></PageTransition></ConsentGuard>} />
          <Route path="/feed" element={<ConsentGuard><PageTransition><Feed /></PageTransition></ConsentGuard>} />
          <Route path="/profile/:userId?" element={<ConsentGuard><PageTransition><Profile /></PageTransition></ConsentGuard>} />

          {/* 灰度功能路由 — 协议 + 灰度权限双守卫 */}
          <Route path="/mv-generate" element={<GrayRoute featureKey="mv_generate"><PathAPage /></GrayRoute>} />
          <Route path="/collab" element={<GrayRoute featureKey="ws_collab"><PathDPage /></GrayRoute>} />

          {/* 关闭功能路由 — 公测期间保留路由但不显示入口 */}
          <Route path="/stock-library" element={<ConsentGuard><StockLibrary /></ConsentGuard>} />
        </Route>
      </Routes>
    </Suspense>
  );
}
