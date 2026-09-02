import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AppLayout } from './AppLayout';
import { ConsentGuard, GrayRoute } from './components/RouteGuards';
import { PageTransition } from './components/PageTransition';

const Landing = lazy(() => import('./pages/Landing').then(m => ({ default: m.Landing })));
const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })));
const CreateMusicPage = lazy(() => import('./pages/CreateMusicPage').then(m => ({ default: m.CreateMusicPage })));
const VoiceClonePage = lazy(() => import('./pages/VoiceClonePage').then(m => ({ default: m.VoiceClonePage })));
const AudioToolsPage = lazy(() => import('./pages/AudioToolsPage').then(m => ({ default: m.AudioToolsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
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
const StudioPage = lazy(() => import('./pages/StudioPage').then(m => ({ default: m.StudioPage })));
const TermsOfService = lazy(() => import('./pages/legal/TermsOfService').then(m => ({ default: m.TermsOfService })));
const PrivacyPolicy = lazy(() => import('./pages/legal/PrivacyPolicy').then(m => ({ default: m.PrivacyPolicy })));
const AIMusicCopyrightPolicy = lazy(() => import('./pages/legal/AIMusicCopyrightPolicy').then(m => ({ default: m.AIMusicCopyrightPolicy })));
const VoiceCloningPolicy = lazy(() => import('./pages/legal/VoiceCloningPolicy').then(m => ({ default: m.VoiceCloningPolicy })));
const CreditsRefundPolicy = lazy(() => import('./pages/legal/CreditsRefundPolicy').then(m => ({ default: m.CreditsRefundPolicy })));
const AcceptableUsePolicy = lazy(() => import('./pages/legal/AcceptableUsePolicy').then(m => ({ default: m.AcceptableUsePolicy })));
const P2AudioSeparationPage = lazy(() => import('./pages/P2AudioSeparationPage').then(m => ({ default: m.P2AudioSeparationPage })));
const P2AudioMasteringPage = lazy(() => import('./pages/P2AudioMasteringPage').then(m => ({ default: m.P2AudioMasteringPage })));
const P2LyricPage = lazy(() => import('./pages/P2LyricPage').then(m => ({ default: m.P2LyricPage })));

const Loading = () => (
  <div className="flex items-center justify-center h-screen bg-[#0a0a0a]">
    <div className="text-[#555555] animate-pulse text-sm">Loading...</div>
  </div>
);

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/landing" element={<Landing />} />

        <Route element={<AppLayout />}>
          {/* New primary navigation */}
          <Route path="/" element={<ConsentGuard><PageTransition><HomePage /></PageTransition></ConsentGuard>} />
          <Route path="/create" element={<ConsentGuard><PageTransition><CreateMusicPage /></PageTransition></ConsentGuard>} />
          <Route path="/generate" element={<Navigate to="/create" replace />} />
          <Route path="/voice-clone" element={<ConsentGuard><PageTransition><VoiceClonePage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools" element={<ConsentGuard><PageTransition><AudioToolsPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/separation" element={<ConsentGuard><PageTransition><P2AudioSeparationPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/mastering" element={<ConsentGuard><PageTransition><P2AudioMasteringPage /></PageTransition></ConsentGuard>} />
          <Route path="/audio-tools/lyrics" element={<ConsentGuard><PageTransition><P2LyricPage /></PageTransition></ConsentGuard>} />
          <Route path="/my-works" element={<ConsentGuard><PageTransition><MyWorks /></PageTransition></ConsentGuard>} />
          <Route path="/settings" element={<ConsentGuard><PageTransition><SettingsPage /></PageTransition></ConsentGuard>} />

          {/* Legacy routes — kept for compatibility, reuse new pages where appropriate */}
          <Route path="/path-a" element={<ConsentGuard><PageTransition><PathAPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-b" element={<ConsentGuard><PageTransition><PathBPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-c" element={<ConsentGuard><PageTransition><PathCPage /></PageTransition></ConsentGuard>} />
          <Route path="/path-d" element={<ConsentGuard><PageTransition><PathDPage /></PageTransition></ConsentGuard>} />
          <Route path="/studio" element={<ConsentGuard><PageTransition><StudioPage /></PageTransition></ConsentGuard>} />
          <Route path="/community" element={<ConsentGuard><PageTransition><Community /></PageTransition></ConsentGuard>} />
          <Route path="/community-feed" element={<ConsentGuard><PageTransition><CommunityFeed /></PageTransition></ConsentGuard>} />
          <Route path="/feed" element={<ConsentGuard><PageTransition><Feed /></PageTransition></ConsentGuard>} />
          <Route path="/profile/:userId?" element={<ConsentGuard><PageTransition><Profile /></PageTransition></ConsentGuard>} />

          {/* Gray */}
          <Route path="/collab" element={<GrayRoute featureKey="ws_collab"><PathDPage /></GrayRoute>} />

          {/* Closed legacy MV route — redirect to Voice Clone */}
          <Route path="/mv-generate" element={<Navigate to="/voice-clone" replace />} />

          <Route path="/stock-library" element={<ConsentGuard><StockLibrary /></ConsentGuard>} />

          <Route path="/legal/terms" element={<ConsentGuard><PageTransition><TermsOfService /></PageTransition></ConsentGuard>} />
          <Route path="/legal/privacy" element={<ConsentGuard><PageTransition><PrivacyPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/aimusic-copyright" element={<ConsentGuard><PageTransition><AIMusicCopyrightPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/voice-cloning" element={<ConsentGuard><PageTransition><VoiceCloningPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/credits-refund" element={<ConsentGuard><PageTransition><CreditsRefundPolicy /></PageTransition></ConsentGuard>} />
          <Route path="/legal/aup" element={<ConsentGuard><PageTransition><AcceptableUsePolicy /></PageTransition></ConsentGuard>} />
        </Route>
      </Routes>
    </Suspense>
  );
}
