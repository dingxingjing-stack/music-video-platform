import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import App from './App';
import { SoundProvider } from './context/SoundContext';
import { AuthProvider } from './context/AuthContext';
import { LoginModal } from './components/LoginModal';

// 注销所有旧的 Service Worker，防止 PWA 缓存导致功能失效
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(regs => {
    regs.forEach(r => r.unregister());
  });
  caches.keys().then(keys => {
    keys.forEach(k => caches.delete(k));
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <SoundProvider>
          <App />
        </SoundProvider>
        <LoginModal />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);