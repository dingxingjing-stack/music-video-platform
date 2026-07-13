/**
 * 种子用户落地页 - 终身会员计划
 * 
 * CTA: 前 100 名注册 = 终身免费 Pro 会员
 */

export default function FoundingMemberPage() {
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
            🏆 创始人计划
          </div>

          <h1 className="text-5xl font-bold mb-6">
            成为创始会员，<span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">终身免费</span>
          </h1>

          <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
            前 <span className="text-orange-400 font-bold">{foundingSpots}</span> 名注册用户，永久享受 Pro 会员权益
            <br />
            无需订阅，无需付费，终身免费
          </p>

          {/* 进度条 */}
          <div className="max-w-md mx-auto mb-8">
            <div className="flex justify-between text-sm mb-2">
              <span>已领取：{claimedSpots}/{foundingSpots}</span>
              <span className="text-orange-400">剩余：{remaining} 席</span>
            </div>
            <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all duration-500"
                style={{ width: `${(claimedSpots / foundingSpots) * 100}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-2">
              🔥 每小时有 {Math.floor(Math.random() * 5) + 1} 位用户加入
            </p>
          </div>

          {/* CTA 按钮 */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <button className="px-8 py-4 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-lg font-bold hover:scale-105 transition-transform shadow-lg shadow-orange-500/25">
              立即领取创始会员资格 →
            </button>
            <button className="px-8 py-4 bg-gray-800 rounded-full text-lg font-medium hover:bg-gray-700 transition-colors">
              观看产品介绍视频
            </button>
          </div>

          {/* 倒计时 */}
          <div className="mt-8 text-sm text-gray-400">
            ⏰ 优惠剩余时间：<span className="text-orange-400 font-mono">6 天 23:59:59</span>
          </div>
        </div>
      </div>

      {/* 权益对比 */}
      <div className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-center mb-12">
          创始会员专属权益
        </h2>

        <div className="grid md:grid-cols-2 gap-8">
          {/* 免费用户 */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h3 className="text-xl font-bold mb-4 text-gray-400">Free</h3>
            <ul className="space-y-3">
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">每日 5 次 AI 音乐生成</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">720P MV 导出</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✓</span>
                <span className="text-gray-400">基础素材库</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✗</span>
                <span className="text-gray-500">1080P 导出</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-gray-600">✗</span>
                <span className="text-gray-500">扒带/Remix 功能</span>
              </li>
            </ul>
            <div className="mt-8 pt-6 border-t border-gray-800">
              <div className="text-3xl font-bold">¥0</div>
              <div className="text-gray-400">永久免费</div>
            </div>
          </div>

          {/* 创始会员 */}
          <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl p-8 border-2 border-orange-500 relative">
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-sm font-bold">
              👑 最受欢迎
            </div>

            <h3 className="text-xl font-bold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">
              Founding Member
            </h3>
            <ul className="space-y-3">
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>无限 AI 音乐生成</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>无限 MV 制作</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>1080P 高清导出</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>完整素材库 (100+ 模板)</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>扒带/Remix 功能</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>先析体验新功能</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>专属 Discord 频道</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span>
                <span>🏆 创始人徽章</span>
              </li>
            </ul>
            <div className="mt-8 pt-6 border-t border-gray-700">
              <div className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">
                ¥0
              </div>
              <div className="text-gray-400">
                <span className="line-through">¥299/年</span> 终身免费
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 社会证明 */}
      <div className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h2 className="text-3xl font-bold mb-8">
          已有 {claimedSpots} 位创作者加入
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
        <h2 className="text-3xl font-bold text-center mb-12">常见问题</h2>

        <div className="space-y-6">
          {[
            {
              q: "终身免费是多久？",
              a: "真的终身！只要平台还在运营，创始会员就永久免费使用所有 Pro 功能。"
            },
            {
              q: "如何成为创始会员？",
              a: "现在注册账号，完成个人资料并发布 3 个作品即可自动获得创始会员身份。"
            },
            {
              q: "已经有账号了还能加入吗？",
              a: "可以！只要你是前 100 名用户并发布 3 个作品，系统会自动升级你的账号。"
            },
            {
              q: "以后会收费吗？",
              a: "新用户会采用 Freemium 模式（免费 + 付费订阅），但创始会员永远免费。"
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
          还剩 {remaining} 个席位
        </h2>
        <p className="text-xl text-gray-400 mb-8">
          错过这次机会，下次就要 ¥299/年了
        </p>
        <button className="px-8 py-4 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full text-lg font-bold hover:scale-105 transition-transform shadow-lg shadow-orange-500/25">
          立即锁定创始会员资格 →
        </button>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-8 text-center text-gray-500">
        <p>© 2026 Music Video Platform. All rights reserved.</p>
      </footer>
    </div>
  );
}