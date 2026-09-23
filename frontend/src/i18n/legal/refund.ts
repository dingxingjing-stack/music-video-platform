import type { LegalDocPair } from './types';

/**
 * Credits 与退款政策（中英双语）。
 *
 * 事实来源：backend/app/services/credits_config.py（注册赠送 50+25+25=100、
 * 一次成功创作 30 Credits、补充包 200/500/1200/2800）、credits_service.py
 * （失败生成自动退回、余额型账本、无到期字段）、paddle_service.py（Paddle 为
 * Merchant of Record）。代码里不存在的机制不写进政策，也不创造绝对退款规则。
 */
export const REFUND_DOC: LegalDocPair = {
  zh: {
    sections: [
      {
        title: '1. 本政策适用于什么',
        blocks: [
          {
            k: 'p',
            t: '本政策说明 Melovar（下称“平台”或“我们”）的 Credits 充值、会员订阅及相关付费交易的计费、发放与退款规则。本政策是《服务条款》的组成部分。',
          },
          {
            k: 'p',
            t: '平台的付款由第三方支付服务商 Paddle 作为记账商户（Merchant of Record）处理：向您的支付方式扣款、开具收据与发票、办理退款与拒付、并按适用法律处理相关税务均由 Paddle 完成，交易账单与收据由 Paddle 出具。Melovar 不收集也不存储您的完整银行卡号、CVV/CVC 或银行账户凭据。',
          },
        ],
      },
      {
        title: '2. Credits 是什么',
        blocks: [
          {
            k: 'p',
            b: 'Credits 是服务使用额度，不是现金。',
            t: '它用于衡量和兑换平台的生成、处理与存储等服务能力，例如一次成功的完整音乐创作消耗 30 Credits。Credits 不等同于现金、存款或货币，不可兑换现金、实物或其他虚拟商品，也不得转售、转让或在平台之外使用。',
          },
          {
            k: 'ul',
            items: [
              {
                b: '获取途径：',
                t: '注册赠送（欢迎 50、邮箱验证 25、首次创作 25，合计 100 Credits，每项仅发放一次）、购买 Credits 补充包、以及会员订阅按周期发放的额度。',
              },
              {
                b: '消耗与退回：',
                t: 'Credits 仅在任务成功时扣减；生成失败不扣 Credits，已扣的会自动退回您的余额。',
              },
              {
                b: '免费额度：',
                t: '赠送额度的数量与发放规则可能随运营调整，调整前会在定价页公示；调整不影响您账户中已有的余额。',
              },
            ],
          },
        ],
      },
      {
        title: '3. 价格、下单与到账',
        blocks: [
          {
            k: 'p',
            t: '平台以美元标价展示价格。结账时 Paddle 可能根据您所在地区以当地币种显示含税后的应付金额，实际扣款的币种、金额与税费以 Paddle 收银台页面显示为准。',
          },
          {
            k: 'p',
            t: 'Credits 补充包为一次性购买：只增加 Credits，不会创建订阅，也不会改变您的会员等级或到期时间。付款成功后 Credits 自动入账，通常即时到账；若未到账，请通过下方渠道联系我们，我们会核对交易记录后补发。',
          },
        ],
      },
      {
        title: '4. 订阅与自动续费',
        blocks: [
          {
            k: 'p',
            t: '会员订阅按月度周期自动续费，续费规则以购买页面与订单确认页显示为准。您可以随时取消：取消后当前周期内的权益与已发放的 Credits 保留至该周期结束，到期后不再续费、也不再扣款。',
          },
        ],
      },
      {
        title: '5. 退款',
        blocks: [
          {
            k: 'p',
            b: '可以申请退款的情形：',
            t: '重复扣款、明显的计费或金额错误、以及平台未能交付您所购买的 Credits 或订阅权益。经核实后，我们将通过 Paddle 把相应金额退回原支付方式。',
          },
          {
            k: 'p',
            b: '通常不予退款的情形：',
            t: '除适用法律另有规定或我们另行明确承诺外，已经消耗的 Credits、已经交付并使用的生成结果、以及已经提供完毕的服务期间不予退款。AI 生成具有概率性与不确定性，对生成结果的主观不满意不属于退款事由（参见《服务条款》第 11 章）。',
          },
          {
            k: 'p',
            b: '退款如何办理：',
            t: '提交请求后，我们会先核对您的交易记录与账户流水；确认应退的，由 Paddle 作为记账商户按其政策与流程执行退款，退回至原支付方式，实际到账时间取决于您的发卡机构与银行。我们无法承诺无条件退款，也不会因您主动取消订阅而就已经提供服务的期间退款。',
          },
        ],
      },
      {
        title: '6. 数字内容与撤回权',
        blocks: [
          {
            k: 'p',
            t: 'Credits 与订阅属于数字化服务。在欧盟、英国及其他设有“撤回期”（例如 14 天）的消费者保护制度下，若您明确同意在撤回期届满前开始使用服务并知悉由此可能失去撤回权，则在适用法律允许的范围内，该撤回权可能不再适用于本次交易；相关征求确认的内容以结账流程实际向您展示者为准。',
          },
          {
            k: 'p',
            b: '关于即时履行：',
            t: '购买 Credits 或开通会员后，服务通常在付款成功时立即开始提供。若您会在撤回期届满前开始使用，我们会在结账流程中就本次交易单独请您确认：您同意平台立即开始履行，并知悉作出该确认后您即不再就本次交易享有法定撤回权。该确认内容会随订单留存，供您事后查阅。',
          },
          {
            k: 'p',
            b: '强制性消费者权利不受影响：',
            t: '无论何种情况，本政策不排除、不限制您在消费者所在地依法不得放弃或限制的强制性权利（包括欧盟、英国、巴西等地法律赋予您的权利）。',
          },
        ],
      },
      {
        title: '7. 有效期、账户终止与处置',
        blocks: [
          {
            k: 'p',
            t: '当前购买的 Credits 不设到期日，在您账户内持续可用；购买的 Credits 与赠送的 Credits 合并计入同一余额。',
          },
          {
            k: 'p',
            t: '您可以随时停止使用并申请注销账户。注销前请自行导出或备份您的作品；账户注销后未使用的 Credits 随之清理，不折算为现金或退款（依法必须退款的除外）。',
          },
          {
            k: 'p',
            t: '因您违反《服务条款》《可接受使用政策》或存在欺诈、滥用、规避计费与访问控制等行为而被限制、暂停或终止的账户，其未使用 Credits 按《服务条款》第 14、15 章处理；您依法享有的强制性消费者权利不受影响。',
          },
        ],
      },
      {
        title: '8. 联系我们与发起请求',
        blocks: [
          {
            k: 'p',
            b: '退款与账务请求：',
            t: '请通过下方邮箱提交，并尽量附上账户注册邮箱、Paddle 交易号（以 txn_ 开头）、订单日期与金额（含币种）以及问题说明，我们会在核实后回复。',
          },
          { k: 'email' },
          {
            k: 'p',
            t: '您也可以使用平台内的反馈入口提交问题；涉及账务争议或紧急安全事项时，请在内容中注明“紧急”并附相关证据。',
          },
          {
            k: 'p',
            b: 'Paddle 官方买家渠道：',
            t: '退款、发票与取消订阅等事项，您也可以直接通过 Paddle 的买家帮助中心办理或查询其处理规则。',
          },
          {
            k: 'links',
            items: [
              { label: 'Paddle 帮助中心', url: 'https://www.paddle.com/help' },
              { label: 'Paddle 买家退款常见问题', url: 'https://www.paddle.com/help/manage/your-customers/buyers-refunds' },
              { label: 'Paddle《Invoiced Consumer Terms and Conditions》', url: 'https://www.paddle.com/legal/invoiced-consumer-terms-2022' },
            ],
          },
        ],
      },
    ],
    closing:
      '本政策是《服务条款》的组成部分，与其冲突时以《服务条款》为准。支付、退款与税务处理同时适用 Paddle 作为记账商户的相关政策。',
  },

  en: {
    sections: [
      {
        title: '1. What this policy covers',
        blocks: [
          {
            k: 'p',
            t: 'This policy explains how Melovar (“the platform”, “we” or “us”) charges for, delivers and refunds Credit top-ups, memberships and related paid transactions. It forms part of our Terms of Service.',
          },
          {
            k: 'p',
            t: 'Payments on the platform are processed by the third-party provider Paddle acting as Merchant of Record: Paddle charges your payment method, issues receipts and invoices, handles refunds and chargebacks and deals with the related taxes under applicable law, so your statement, receipts and invoices come from Paddle. Melovar does not collect or store your full card number, CVV/CVC or bank account credentials.',
          },
        ],
      },
      {
        title: '2. What Credits are',
        blocks: [
          {
            k: 'p',
            b: 'Credits are a usage allowance, not money. ',
            t: 'They measure and redeem the platform’s generation, processing and storage capacity – one successful full song, for example, costs 30 Credits. Credits are not cash, deposits or currency, cannot be exchanged for cash, goods or other virtual items, and may not be resold, transferred or used outside the platform.',
          },
          {
            k: 'ul',
            items: [
              {
                b: 'How you obtain them: ',
                t: 'signup bonuses (50 for welcome, 25 for verifying your email and 25 for your first creation – 100 Credits in total, each granted once), purchased Credit packs, and the allowance granted periodically by a membership.',
              },
              {
                b: 'How they are spent and returned: ',
                t: 'Credits are deducted only when a task succeeds. A failed generation costs no Credits, and anything already deducted is automatically returned to your balance.',
              },
              {
                b: 'Free allowances: ',
                t: 'the size and granting rules of bonus Credits may change over time; we announce changes on the pricing page before they apply, and they do not reduce the balance you already hold.',
              },
            ],
          },
        ],
      },
      {
        title: '3. Prices, checkout and delivery',
        blocks: [
          {
            k: 'p',
            t: 'Prices are listed in US dollars. At checkout Paddle may show the amount payable in your local currency, including tax, depending on where you are; the currency, amount and taxes actually charged are the ones displayed on the Paddle checkout page.',
          },
          {
            k: 'p',
            t: 'A Credit pack is a one-time purchase: it only adds Credits, does not create a subscription, and does not change your membership tier or its expiry. After a successful payment Credits are added automatically, usually at once. If they do not appear, contact us through the channels below and we will top them up after checking the transaction.',
          },
        ],
      },
      {
        title: '4. Memberships and automatic renewal',
        blocks: [
          {
            k: 'p',
            t: 'Memberships renew automatically on a monthly cycle, under the billing terms shown on the purchase and order-confirmation pages. You can cancel at any time: after cancelling you keep the benefits and the Credits already granted until the end of the current cycle, and no further renewal or charge takes place.',
          },
        ],
      },
      {
        title: '5. Refunds',
        blocks: [
          {
            k: 'p',
            b: 'When you can ask for a refund: ',
            t: 'duplicate charges, clear billing or amount errors, and cases where we fail to deliver the Credits or membership benefits you bought. Once verified, we have the corresponding amount returned to your original payment method through Paddle.',
          },
          {
            k: 'p',
            b: 'When a refund is normally not due: ',
            t: 'unless applicable law provides otherwise or we explicitly promise more, we do not refund Credits you have already used, generation results already delivered and used, or service periods already provided. AI generation is probabilistic and non-deterministic, so dissatisfaction with a result is not in itself a ground for refund (see Section 11 of the Terms of Service).',
          },
          {
            k: 'p',
            b: 'How a refund is processed: ',
            t: 'after you submit a request we first check the transaction against your account ledger. Where a refund is due, Paddle as Merchant of Record executes it under its own policy and process, back to your original payment method; the time it takes to reach you depends on your card issuer and bank. We cannot promise unconditional refunds, and cancelling a membership does not by itself entitle you to a refund of periods already served.',
          },
        ],
      },
      {
        title: '6. Digital content and the right of withdrawal',
        blocks: [
          {
            k: 'p',
            t: 'Credits and memberships are digital services. Under consumer-protection regimes that grant a withdrawal period (for example 14 days in the EU and the UK), if you expressly agree to start using the service before that period ends and acknowledge that you thereby lose your right of withdrawal, that right may no longer apply to this transaction to the extent applicable law allows; what is asked of you is whatever the checkout flow actually presents and records.',
          },
          {
            k: 'p',
            b: 'About immediate performance: ',
            t: 'Credits and memberships are normally made available as soon as your payment succeeds. Where you will start using the service before the withdrawal period ends, our checkout asks you to confirm separately, for this transaction, that you agree to immediate performance and that you understand this confirmation ends your statutory right of withdrawal for it. The confirmation is stored with your order so you can review it later.',
          },
          {
            k: 'p',
            b: 'Mandatory consumer rights are unaffected: ',
            t: 'in no case does this policy exclude or limit rights you receive under the law of your country of residence that cannot be waived or restricted, including rights under EU, UK and Brazilian law.',
          },
        ],
      },
      {
        title: '7. Validity, account closure and enforcement',
        blocks: [
          {
            k: 'p',
            t: 'Purchased Credits currently have no expiry date and remain available in your account; purchased and bonus Credits share one balance.',
          },
          {
            k: 'p',
            t: 'You may stop using the platform and request account closure at any time. Export or back up your works beforehand; unused Credits are cleared with the account and are not converted into cash or refunded, except where a refund is required by law.',
          },
          {
            k: 'p',
            t: 'Where an account is restricted, suspended or terminated because you breached the Terms of Service or the Acceptable Use Policy, or engaged in fraud, abuse or circumvention of billing and access controls, unused Credits are handled under Sections 14 and 15 of the Terms of Service. Your mandatory consumer rights are unaffected.',
          },
        ],
      },
      {
        title: '8. Contacting us and submitting a request',
        blocks: [
          {
            k: 'p',
            b: 'Refund and billing requests: ',
            t: 'send them to the address below and include, where possible, your account email, the Paddle transaction ID (starting with txn_), the order date and the amount with currency, and a description of the problem. We will reply after checking the records.',
          },
          { k: 'email' },
          {
            k: 'p',
            t: 'You can also use the in-product feedback channel. For billing disputes or urgent security matters, mark the message as urgent and attach the relevant evidence.',
          },
          {
            k: 'p',
            b: 'Paddle buyer channels: ',
            t: 'you can also handle refunds, invoices and subscription cancellations directly through Paddle’s buyer help centre, or check how Paddle processes them:',
          },
          {
            k: 'links',
            items: [
              { label: 'Paddle Help Center', url: 'https://www.paddle.com/help' },
              { label: 'Paddle Help Center — FAQ for Paddle Buyers', url: 'https://www.paddle.com/help/manage/your-customers/buyers-refunds' },
              { label: 'Paddle Invoiced Consumer Terms and Conditions', url: 'https://www.paddle.com/legal/invoiced-consumer-terms-2022' },
            ],
          },
        ],
      },
    ],
    closing:
      'This policy forms part of the Terms of Service, which prevail in case of conflict. Payment, refund and tax handling are additionally subject to the policies of Paddle as Merchant of Record.',
  },
};
