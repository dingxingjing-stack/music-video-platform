import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../i18n/useTranslation';

export function CreditsRefundPolicy() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-[#666666] hover:text-white transition mb-4 inline-block"
        >
          ← {t('common.back')}
        </button>
        <h1 className="text-3xl font-bold text-white mb-2">{t('legal.titleCredits')}</h1>
        <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">1. Credits 是什么</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            Credits（“积分”）是本平台为 AI 音乐生成、音频预览、歌声处理等功能提供的一种内部使用额度。用户通过完成日常任务、参与公会活动等方式获得 Credits；Credits 可用于解锁平台的完整功能模块。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">2. 与真实货币完全解绑</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            <strong className="text-white">左侧的 Credits 不可兑换任何现金、实物、虚拟商品或其他形式的货币。</strong> Credits 仅可用于本平台内的功能使用，不可转移至其他用户或平台。
          </p>
          <div className="mt-3 p-4 rounded-lg bg-[#1a1a1a] border border-[#ff6a10]/30">
            <p className="text-xs text-[#ff6a10] font-mono">
              ℹ️ <strong>当前状态：</strong>当前支付/充值功能尚未开放。本平台目前暂不接入 Stripe、Shopify、小程序Pay 等第三方支付服务。因此您目前无法通过本网页支付购买 Credits 或进行任何真实货币交易操作。
            </p>
          </div>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">3. 服务暂停或中断</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们可能会随时出于技术维护、功能调整、安全或合规原因暂停服务。目前尚不能明确标准的退款规则：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li><strong className="text-[#cccccc]">服务中断。</strong>若本平台因平台自身原因（如重大技术故障导致持续无法使用）导致您已获得的 Credits 无法使用，我们不承担退款责任。但我们将尽最大努力恢复服务并补偿等值时间或其他合理方式。</li>
            <li><strong className="text-[#cccccc]">适用法律强制要求。</strong>如果依据法律规定（如消费者权益保护法、网络交易管理办法等）必须退款，我们将遵循该法律规定执行。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">4. 您是否获得提及的退款价值</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            现行法律没有针对本类虚拟积分/数字内容（即使用了不可退款且已获得明确使用价值的服务）的任何改装。我们尚不承诺、不会保证你在任何情况下都有提出退款要求，除非平台被证明存在重大失误、性质违法或符合法律保护要求，我们将在合理范围内保留对可能合理的退款请求进行冻结、拒绝或依据合理规定减少对可及退款金额所做出的个别实际支付金额。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">5. 期限与到期</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            Credits 默认有指定的有效期（根据具体活动规则而定）。到期后，未使用的 Credits 将失效，不可回收或转让。
          </p>
        </section>

        <section className="py-6">
          <h2 className="text-xl font-semibold text-white mb-3">6. 反馈渠道</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如您对退款或 Credits 有任何疑问或想法，请通过平台内或联系页面与我们沟通。所有反馈将人工审核后再做最终决定。退款处理过程中涉及的行政费用或风险由您自行承担。
          </p>
        </section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            本政策并非隐私或服务条款的一部分。请在适用法律允许范围内提供完整的退款条款。如需帮助，请联系我们的支持团队。
          </p>
        </div>
      </div>
    </div>
  );
}
