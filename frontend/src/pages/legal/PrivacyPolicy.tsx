import { useNavigate } from 'react-router-dom';

export function PrivacyPolicy() {
  const navigate = useNavigate();

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-[#666666] hover:text-white transition mb-4 inline-block"
        >
          ← 返回
        </button>
        <h1 className="text-3xl font-bold text-white mb-2">隐私政策</h1>
        <p className="text-sm text-[#888888]">最后更新：2026年8月</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">1. 引言</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们重视您的隐私。本隐私政策仅适用于您在 Zyvexo 提供服务（以下简称“本平台”）时的数据收集 、使用、存储、保密及删除等活动。通过访问或使用本平台，即表示您已阅读并同意本协议。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">2. 我们收集的信息</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            目前我们仅收集必要的信息，或在您选择提供时收集，包括：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li><strong className="text-[#cccccc]">注册信息。</strong> 除非法律法规另有强制性规定，否则我不会收集您的姓名 、邮箱地址或手机号。</li>
            <li><strong className="text-[#cccccc]">使用信息。</strong> 我们可能会收集日志数据、IP 地平线和您使用服务的技术信息，以用于故障排查、安全性和服务优化。</li>
            <li><strong className="text-[#cccccc]">内容信息。</strong> 您上传到本平台的内容（比如提示词、歌词、音频片段、MIDI 数据等）。</li>
          </ul>
          <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
            请注意：以下信息目前**没有**被本平台主动收集：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>支付卡或银行账户信息（当前支付系统未上线，不处理任何付款数据）</li>
            <li>用户年龄数据（当前 playtrial 仅用 API 检验未满13岁，未收集实际年龄数值）</li>
            <li>实名验证数据（身份证号码、面部识别等）</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">3. 数据使用</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们收集和使用数据的目的仅为：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>提供、维护和优化服务；</li>
            <li>处理内容以满足您的创作请求；</li>
            <li>防范欺诈、滥用和技术故障； </li>
            <li>遵守法律法规要求； </li>
            <li>进行匿名化数据统计以改进产品</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">4. 数据存储与留存</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们目前计划在 Service Animals 上使用基础任义数据库存储（SQLite，含用户注册、任务信息等），以及辅助数据。请别注意：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>所有数据存储在数据库中，根据业务需要定期清理；</li>
            <li>Activity Activity 数据可能会被定期清除（free tier rules apply）；</li>
            <li>当任何数据过时或用户自主删除时，我们将遵守适用的数据保护法律求数据进行删除。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">5. 数据共享与第三方</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们不会将你所用数据出售、出租或转让给与钓鱼活动无关的第三方。我们可能在以下情况下向您共享必要信息：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>向为我们提供基础设施服务的合作伙伴（如云端基础设施商、模型托管商）共享必要数据，以保障服务运行；</li>
            <li>向法律要求或执法机关披露，以配合司法调查；</li>
            <li>业务合并、转让时，会转移相关数据。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">6. 您的权利</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            根据适用数据保护法，您有权：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>访问我们保存的关于您的数据；</li>
            <li>要求我们更正或删除不准确的数据；</li>
            <li>要求删除任何内容资料（仅在法律允许范围内）；</li>
            <li>提出理由撤销数据处理同意；</li>
            <li>拒绝通过 Cookie（如适用）向你发送定向广告或跟踪；</li>
            <li>向监管机构提出投诉。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">7. 安全措施</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们实施推荐的行业标准安全措施来保护您的数据免遭未经授权的访问、更改、披露或破坏。这些数据保护措施包括加密传输、访问控制和定期安全审计。然而，没有任何一种网络传输或存储方法可以保证绝对安全。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">8. 修改</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们可能不时更新本隐私政策并发布最新版本。重大变更会在变更生效前通过显眼界面或邮件公告通知您。继续使用本平台意味着您接受了最新版本的隐私政策。
          </p>
        </section>

        <section className="py-6">
          <h2 className="text-xl font-semibold text-white mb-3">9. 联系我们</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如对本隐私政策有任何疑问，请通过本平台的联系渠道向我们咨询。
          </p>
        </section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            本隐私政策构成实时记录。您使用本平台即表示您同意（lawful consent）、数据法律要求收集、处理和保留您的信息数据的处理方式。但会按照本隐私政策进行。
          </p>
        </div>
      </div>
    </div>
  );
}
