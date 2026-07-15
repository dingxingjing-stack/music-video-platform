import { Routes, Route } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AppLayout } from './AppLayout';

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

const Loading = () => (
  <div className="flex items-center justify-center h-screen bg-[#121212]">
    <div className="text-[#555555] animate-pulse">加载中...</div>
  </div>
);

// 公测期间独立落地页（不需要侧边栏布局）
export function StandaloneRoutes() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/landing" element={<Landing />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* 落地首页 — 独立展示，无侧边栏 */}
        <Route path="/landing" element={<Landing />} />

        {/* 主应用路由 — 侧边栏布局 */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<TrackStudio />} />
          <Route path="/path-a" element={<PathAPage />} />
          <Route path="/path-b" element={<PathBPage />} />
          <Route path="/path-c" element={<PathCPage />} />
          <Route path="/path-d" element={<PathDPage />} />
          <Route path="/community" element={<Community />} />
          <Route path="/community-feed" element={<CommunityFeed />} />
          <Route path="/feed" element={<Feed />} />
          <Route path="/profile/:userId?" element={<Profile />} />
          {/* 素材商城路由保留但导航隐不显示 */}
          <Route path="/stock-library" element={<StockLibrary />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
