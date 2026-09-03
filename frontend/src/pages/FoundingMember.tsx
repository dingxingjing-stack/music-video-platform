/**
 * 种子用户落地页 - 终身会员计划
 * 
 * CTA: 前 100 名注册 = 终身免费 Pro 会员
 */

import { useTranslation } from '../i18n/useTranslation';

export default function FoundingMemberPage() {
  const { t } = useTranslation();
  const foundingSpots = 100;
  const claimedSpots = 47; // Mock 数据
  const remaining = foundingSpots - claimedSpots;

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        {/* 背景渐变 */}
        <div className="absolute inset-0 bg-gradient-to-br from-orange-500/20 to-pink-500/20" />
        
        <div className="relative max-w-4xl mx-auto px-6 py-20 text-center">
          {/* 徽章 */}
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-sm font-bold mb-6">
            🏆 {t('founding.badge')}
          </div>

          <h1 className="text-5xl font-bold mb-6">
            {t('founding.titleBefore')}<span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">{t('founding.titleFree')}</span>
          </h1>

          <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
            {t('founding.desc1', { n: foundingSpots })}
            <br />
            {t('founding.desc2')}
          </p>

          {/* 进度条 */}
          <div className="max-w-md mx-auto mb-8">
            <div className="flex justify-between text-sm mb-2">
              <span>{t('founding.claimed', { claimed: claimedSpots, total: foundingSpots })}</span>
              <span className="text-orange-400">{t('founding.remaining', { n: remaining })}</span>
            </div>
            <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all duration-500"
                style={{ width: `${(claimedSpots / foundingSpots) * 100}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-2">
              🔥 {t('founding.joining', { n: Math.floor(Math.random() * 5) + 1 })}
            </p>
          </div>

          {/* CTA 按钮 */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <button className="px-8 py-4 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-lg font-bold hover:scale-105 transition-transform shadow-lg shadow-orange-500/25">
              {t('founding.cta')} →
            </button>
            <button className="px-8 py-4 bg-gray-800 rounded-full text-lg font-medium hover:bg-gray-700 transition-colors">
              {t('founding.watchVideo')}
            </button>
          </div>

          {/* 倒计时 */}
          <div className="mt-8 text-sm text-gray-400">
            ⏰ {t('founding.offerEnds')}: <span className="text-orange-400 font-mono">6 天 23:59:59</span>
          </div>
        </div>
      </div>

      {/* 权益对比 */}
      <div className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-center mb-12">
          {t('founding.perksTitle')}
        </h2>

        <div className="grid md:grid-cols-2 gap-8">
          {/* 免费用户 */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h3 className="text-xl font-bold mb-4 text-gray-400">Free</h3>
            <ul className="space-y-3">
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">{t('founding.perkGen1')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">{t('founding.perkGen2')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">{t('founding.perkGen3')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✗</span>
                <span className="text-gray-500">{t('founding.perkGen4')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✗</span>
                <span className="text-gray-500">{t('founding.perkGen5')}</span>
              </li>
            </ul>
            <div className="mt-8 pt-6 border-t border-gray-800">
              <div className="text-3xl font-bold">¥0</div>
              <div className="text-gray-400">{t('founding.freeForever')}</div>
            </div>
          </div>

          {/* 创始会员 */}
          <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl p-8 border-2 border-orange-500 relative">
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-sm font-bold">
              👑 {t('founding.popular')}
            </div>

            <h3 className="text-xl font-bold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">
              Founding Member
            </h3>
            <ul className="space-y-3">
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro1')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro2')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro3')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro4')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro5')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro6')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro7')}</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>{t('founding.perkPro8')}</span>
              </li>
            </ul>
            <div className="mt-8 pt-6 border-t border-gray-700">
              <div className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">
                ¥0
              </div>
              <div className="text-gray-400">
                <span className="line-through">¥299/年</span> {t('founding.lifetimeFree')}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 社会证明 */}
      <div className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h2 className="text-3xl font-bold mb-8">
          {t('founding.creatorsJoined', { n: claimedSpots })}
        </h2>

        <div className="grid md:grid-cols-3 gap-6">
          {[
            { name: "音乐制作人 Alex", avatar: "👨‍🎤", feat: "已创作 23 部 MV" },
            { name: "独立歌手 Luna", avatar: "👩‍🎤", feat: "B 站 5 万粉丝" },
            { name: "视频博主 Max", avatar: "👨‍💻", feat: "YouTube 10 万订阅" }
          ].map((user, i) => (
            <div key={i} className="bg-gray-900 rounded-xl p-6">
              <div className="text-4xl mb-3">{user.avatar}</div>
              <div className="font-bold mb-1">{user.name}</div>
              <div className="text-gray-400 text-sm">{user.feat}</div>
            </div>
          ))}
        </div>
      </div>

      {/* FAQ */}
      <div className="max-w-3xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-center mb-12">{t('founding.faqTitle')}</h2>

        <div className="space-y-6">
          {[
            {
              q: t('founding.faq1q'),
              a: t('founding.faq1a')
            },
            {
              q: t('founding.faq2q'),
              a: t('founding.faq2a')
            },
            {
              q: t('founding.faq3q'),
              a: t('founding.faq3a')
            },
            {
              q: t('founding.faq4q'),
              a: t('founding.faq4a')
            }
          ].map((faq, i) => (
            <div key={i} className="bg-gray-900 rounded-xl p-6">
              <h3 className="font-bold mb-2">{faq.q}</h3>
              <p className="text-gray-400">{faq.a}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 最终 CTA */}
      <div className="max-w-2xl mx-auto px-6 py-20 text-center">
        <h2 className="text-4xl font-bold mb-6">
          {t('founding.seatsLeft', { n: remaining })}
        </h2>
        <p className="text-xl text-gray-400 mb-8">
          {t('founding.missChance')}
        </p>
        <button className="px-8 py-4 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-lg font-bold hover:scale-105 transition-transform shadow-lg shadow-orange-500/25">
          {t('founding.lockMembership')} →
        </button>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-8 text-center text-gray-500">
        <p>© 2026 Zyvexo. All rights reserved.</p>
      </footer>
    </div>
  );
}