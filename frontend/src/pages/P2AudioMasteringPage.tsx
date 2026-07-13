/**
 * P2-5: 母带处理页面
 */

import { AudioMasteringPanel } from '../components/AudioMasteringPanel';

export function P2AudioMasteringPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <AudioMasteringPanel />
    </div>
  );
}