import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AppLayout } from './AppLayout';
import { ConsentGuard } from './components/RouteGuards';
import { PageTransition } from './components/PageTransition';
import { useTranslation } from './i18n/useTranslation';

const Landing = lazy(() => import('./pages/Landing').then(m => ({ default: m.Landing })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })));
const CreateMusicPage = lazy(() => import('./pages/CreateMusicPage').then(m => ({ default: m.CreateMusicPage })));
const AudioToolsPage = lazy(() => import('./pages/AudioToolsPage').then(m => ({ default: m.AudioToolsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
const TrackStudio = lazy(() => import('./pages/TrackStudio').then(m => ({ default: m.TrackStudio })));
const MyWorks = lazy(() => import('./pages/MyWorks'));
const TermsOfService = lazy(() => import('./pages/legal/TermsOfService').then(m => ({ default: m.TermsOfService })));
const PrivacyPolicy = lazy(() => import('./pages/legal/PrivacyPolicy').then(m => ({ default: m.PrivacyPolicy })));
const AIMusicCopyrightPolicy = lazy(() => import('./pages/legal/AIMusicCopyrightPolicy').then(m => ({ default: m.AIMusicCopyrightPolicy })));
const CreditsRefundPolicy = lazy(() => import('./pages/legal/CreditsRefundPolicy').then(m => ({ default: m.CreditsRefundPolicy })));
const AcceptableUsePolicy = lazy(() => import('./pages/legal/AcceptableUsePolicy').then(m => ({ default: m.AcceptableUsePolicy })));
const P2AudioSeparationPage = lazy(() => import('./pages/P2AudioSeparationPage').then(m => ({ default: m.P2AudioSeparationPage })));
const P2AudioMasteringPage = lazy(() => import('./pages/P2AudioMasteringPage').then(m => ({ default: m.P2AudioMasteringPage })));
const P2LyricPage = lazy(() => import('./pages/P2LyricPage').then(m => ({ default: m.P2LyricPage })));
const PricingPage = lazy(() => import('./pages/PricingPage').then(m => ({ default: m.PricingPage })));

const Loading = () => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center h-screen bg-[#0a0a0a]">
      <div className="text-[#555555] animate-pulse text-sm">{t('common.loading')}</div>
    </div>
  );
};

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/landing" element={<Landing />} />
        {/* 注册页（公开，无需登录） */}
        <Route path="/register" element={<RegisterPage />} />
        {/* 定价页（公开，无需登录） */}
        <Route path="/pricing" element={<PricingPage />} />

        <Route element={<AppLayout />}>
          {/* New primary navigation */}
          <Route path="/" element={<ConsentGuard><PageTransition><HomePage /></PageTransition></ConsentGuard>} />
          <Route path="/create" element={<ConsentGuard><PageTransition><CreateMusicPage /></PageTransition></ConsentGuard>} />
          <Route path="/generate" element={<Navigate to="/create" replace />} />
          <Route path="/audio-tools" element={<ConsentGuard><PageTransition><AudioToolsPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/separation" element={<ConsentGuard><PageTransition><P2AudioSeparationPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/mastering" element={<ConsentGuard><PageTransition><P2AudioMasteringPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/lyrics" element={<ConsentGuard><PageTransition><P2LyricPage /></PageTransition></ConsentGuard>} />
          <Route path="/my-works" element={<ConsentGuard><PageTransition><MyWorks /></PageTransition></ConsentGuard>} />
          <Route path="/settings" element={<ConsentGuard><PageTransition><SettingsPage /></PageTransition></ConsentGuard>} />
          {/* Legacy hidden capability：Track Studio（stems/task client 宿主，不导航不宣传，保留可达） */}
          <Route path="/track-studio" element={<ConsentGuard><PageTransition><TrackStudio /></PageTransition></ConsentGuard>} />

          <Route path="/legal/terms" element={<ConsentGuard><PageTransition><TermsOfService /></PageTransition></ConsentGuard>} />
          <Route path="/legal/privacy" element={<ConsentGuard><PageTransition><PrivacyPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/aimusic-copyright" element={<ConsentGuard><PageTransition><AIMusicCopyrightPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/credits-refund" element={<ConsentGuard><PageTransition><CreditsRefundPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/aup" element={<ConsentGuard><PageTransition><AcceptableUsePolicy /></PageTransition></ConsentGuard>} />
        </Route>
      </Routes>
    </Suspense>
  );
}
