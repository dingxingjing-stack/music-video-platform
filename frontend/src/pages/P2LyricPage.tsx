/**
 * P2 功能页面 - AI 作词
 * 包含 AI 作词生成器组件
 */

import { AILyricGenerator } from '../components/AILyricGenerator';

export function P2LyricPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <AILyricGenerator />
    </div>
  );
}