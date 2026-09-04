import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../i18n/useTranslation';

export function TermsOfService() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-[#121212] text-[#e0e0e0] px-6 py-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <button
            onClick={() => navigate(-1)}
            className="text-sm text-[#888888] hover:text-white transition mb-4 inline-block border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-1 rounded"
          >
            ← {t('common.back')}
          </button>
          <h1 className="text-3xl font-black text-white mb-2">{t('legal.titleTerms')}</h1>
          <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
          <p className="text-sm text-[#888888]">{t('legal.effective')}</p>
          <p className="text-sm text-[#888888]">{t('legal.version')}</p>
        </div>

        <div className="bg-[#1e1e1e] border border-[#2a2a2a] rounded-lg p-6 mb-6">
          <p className="text-[15px] leading-relaxed text-[#e0e0e0]">
            欢迎使用 Zyvexo 平台（以下简称“本平台”、“我们”）提供的 AI 音乐创作及相关服务。请您在使用本平台前仔细阅读本《服务条款》（以下简称“本条款”）。通过注册、登录、访问或以任何方式使用本平台，即表示您已阅读、理解并同意受本条款约束。如您不同意本条款的任何内容，请停止使用本平台。
          </p>
        </div>

        <div className="space-y-0">

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第1章 服务说明</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              Zyvexo 是一个面向全球（巴西除外）用户提供 AI 音乐与音频创作工具的平台，功能可能包括 AI 音乐生成、音频编辑、多轨混音、MIDI 编辑、协作、社区分发、存储与内容分发加速等。平台免费提供约 80% 核心功能的体验，部分高级功能需通过订阅或按量付费等方式使用。平台会尽合理努力维护服务稳定，但受技术、第三方服务及合规等因素影响，不保证服务在任何特定场景下均完全无误或持续可用。具体功能、可用性及限制以平台实时展示及相关说明为准。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第2章 接受本条款</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              2.1 本条款构成您与本平台运营方之间具有法律约束力的协议，与《隐私政策》《社区准则》《付费与退款政策》等共同构成本平台的完整使用规则。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              2.2 您通过勾选同意、点击确认、创建账户或实际使用服务等方式接受本条款。您声明并保证已具备完全民事行为能力或已取得监护人同意。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              2.3 如您代表企业、团队或其他组织使用服务，您保证已获得充分授权可代表该组织接受本条款。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              2.4 我们可能根据适用法律、监管要求或业务需要更新本条款，更新后将通过站内公告、弹窗、站内信等方式通知，修订版自公布之日起生效，继续使用服务视为接受更新后的条款。本条款不影响您在消费者所在地法律规定的、依法不得排除或限制的强制性权利。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第3章 账户注册、资格与安全</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              3.1 您需年满 13 周岁方可注册；未满 18 周岁应在监护人指导下使用。您应提供真实、准确、完整的注册信息，并及时更新；因信息不实导致的损失由您自行承担。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              3.2 账户仅供本人使用，不得出借、转让、出租或共享；您应对账户下的全部行为承担责任，包括通过您的登录凭证、访问令牌或其他验证方式进行的操作。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              3.3 您应妥善保管登录凭据及访问令牌，如发现未授权使用或安全漏洞，应立即通知平台；平台有权在风险情形下采取限流、冻结或强制下线等保护措施。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              3.4 服务地区与注册资格：巴西不属于当前服务开放地区，本平台当前不面向巴西境内用户提供服务。位于巴西境内的用户不得注册、登录或使用本平台。平台可以根据合理的技术信号、账户信息、支付信息、居住地、所在地或其他合规信息判断用户是否位于非开放地区，并可据此限制、拒绝或终止相关账户的注册、登录或使用。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              3.5 您应确保您提供的信息真实且有权提供，并保证有权授权平台为提供服务所必需的处理。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第4章 服务内容、范围与可用性</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              4.1 平台提供 AI 音乐与视频一体化创作相关服务，包括但不限于灵感生成、AI 生成、编辑、协作、存储及分发等，具体以平台实际开放的功能为准。部分功能需订阅或按量付费。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.2 平台会尽合理努力保障服务可用性，但可能因第三方服务依赖、网络条件、算力调度、维护升级、合规调整等出现延迟、中断、排队或功能限制。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.3 服务地区与开放范围：当前不向巴西开放服务；面向巴西以外的其他国家/地区提供服务。巴西不属于当前服务开放地区，本平台当前不面向巴西境内用户提供服务。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.4 位于巴西境内的用户不得注册、登录或使用本平台；平台可以根据合理的技术信号、账户信息、支付信息、居住地、所在地或其他合规信息判断用户是否位于非开放地区，并可以限制、拒绝或终止非开放地区用户的访问、注册、购买或使用。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.5 除巴西之外，其他国家或地区也可能因适用法律、监管要求、支付能力、第三方服务限制、制裁或技术原因被限制、暂停或禁止提供全部或部分服务。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.6 平台不保证服务在所有国家或地区均可访问、注册、购买或使用，实际可用性以平台实时配置及第三方能力为准。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.7 用户自行负责确保其访问、注册、购买和使用平台的行为符合其所在地及其他适用司法辖区的法律要求。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              4.8 平台可能根据业务、技术或合规需要对服务进行升级、降级、限速或灰度发布，涉及重大变更将提前合理期限公示。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第5章 用户内容、知识产权与授权</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              5.1 用户对其上传至平台、通过平台生成或存储于平台的内容（包括但不限于文本、提示词、歌词、旋律、音频、视频、图片、封面、评论及元数据等）承担全部责任。用户原则上保留其合法拥有的用户内容权利，原权利人的权利不因内容上传至平台而自动转移。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              5.2 为提供、维护及优化服务之目的，平台可以对用户内容进行必要的存储、复制、传输、缓存、格式转换、技术处理和展示。您授予平台为实现上述目的所必需的非独占、全球范围、免版税的技术性许可，该许可不意味着平台取得用户内容的所有权。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              5.3 您保证您拥有或已取得合法授权，有权授予前述许可，且您的内容不侵犯任何第三方的知识产权、隐私权、肖像权或其他合法权益，亦符合适用法律及监管要求。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              5.4 AI 生成内容特别说明：平台可能使用第三方人工智能模型或服务、第三方模型服务商提供的第三方 API 等辅助生成内容。AI 生成内容具有概率性、不确定性，平台不保证原创性，不保证唯一性，不保证排他性，不保证一定受到版权保护，不保证一定可以商业使用；亦即不保证其原创性，不保证其唯一性，不保证其排他性，不保证其一定受到版权保护，不保证其一定可以商业使用。您必须自行判断生成内容是否适合发布、商业使用或其他用途；如需商业使用，还应遵守适用法律、第三方模型或服务的适用许可条件以及平台相关政策。平台不声称拥有任何 AI 模型的版权，不声称拥有任何第三方 AI 模型的商业许可，亦不保证任何具体 AI 模型一定允许商业使用，具体能否商用以第三方模型服务商的规则及适用法律为准。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第6章 平台知识产权与许可使用</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              6.1 平台的软件、算法、界面设计、商标、标识、文档、商业秘密及其他平台内容，除用户内容及第三方内容外，均归平台或合法授权方所有，受适用法律保护。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              6.2 平台授予您一项可撤销、有限、非独占、不可转让、不可转许可的个人使用许可，仅用于按本条款访问和使用服务。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              6.3 未经书面许可，您不得对平台进行反向工程、批量爬取、镜像、二次分发或用于构建竞争性产品。平台不声称拥有任何第三方人工智能模型的版权，也不声称已取得任何第三方 AI 模型的统一商业许可，相关第三方模型的权利归其各自权利人所有。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第7章 使用规范与禁止行为</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              7.1 您承诺遵守适用法律、公序良俗及平台社区准则，不得发布违法、侵权、色情、暴力、歧视、骚扰或误导性内容。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              7.2 禁止行为包括但不限于：侵犯版权或滥用他人声音或肖像进行深度伪造；上传恶意代码；规避限流、计费或访问控制；批量注册、刷量或操纵榜单；洗歌、抄袭或恶意投诉；未经授权抓取或滥用 API。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              7.3 平台有权采用版权检测、技术指纹及人工审核等手段，对违规内容采取下架、限流、扣除积分或封禁等措施。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第8章 付费、订阅、额度与退款</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              8.1 Credits 性质：Credits 是平台服务使用额度，用于衡量和兑换平台的生成、处理、存储等服务能力。Credits 不等同于现金、存款或货币，不具有货币属性。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              8.2 免费额度：平台可能提供免费额度，免费额度可能存在每日、周期性或其他限制，具体数量、有效期及使用规则以平台页面展示为准。平台可以根据运营需要调整免费额度、使用限制和消耗规则，调整前将以合理方式公示。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              8.3 Credits 限制：Credits 不得转售、转让或兑换现金，除非平台在相关规则中明确允许。Credits 的消耗以平台计费逻辑为准。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              8.4 付费服务：付费服务、订阅服务的价格、计费周期、续费规则和具体条件以购买页面、订单确认页及相关付费说明为准。订阅服务可能按周期自动续费，您可在到期前按页面指引取消，取消后权益保留至当前周期结束。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              8.5 退款：因技术故障、重复扣款、平台无法提供已购买服务等情形导致的退款，将根据适用法律和平台退款政策处理。消费者依法享有的强制性退款或其他权利不因本条款而被排除。除适用法律另有规定或平台明确承诺外，已消耗的算力、存储或已交付的生成结果不予退款；因平台原因多扣费或未交付的，经核实后将以补发额度或原路退回等方式处理。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第9章 第三方服务、API与外部链接</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              9.1 平台可能依赖或集成第三方服务以提供部分功能，包括但不限于第三方 AI 服务、第三方 API、云计算、对象存储、支付服务、CDN 及网络基础设施等，其服务受第三方自身条款与隐私政策约束。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              9.2 平台不就第三方服务的可用性、准确性、适销性或特定用途适用性作出超出适用法律要求的保证，亦不虚构任何具体供应商的许可、保证或责任范围。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              9.3 因第三方服务中断、定价变更、政策调整或数据丢失等因素导致的服务影响，平台将在合理范围内提供替代方案或指引，但不承担超出适用法律要求的额外责任。您通过 API 或开放能力接入平台时，应遵守调用频率、配额及合规使用要求。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第10章 隐私保护与数据安全</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              10.1 平台高度重视个人信息保护，收集、存储、使用及处理个人信息将遵循《隐私政策》及适用法律，遵循最小必要、公开透明原则。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              10.2 您上传的音频、视频等内容将以合理安全措施存储于受信基础设施，未经授权不会向无关第三方披露。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              10.3 尽管已采取合理安全措施，互联网传输仍存在风险，您应自行备份重要作品，平台不对因不可抗力或非因平台重大过失导致的数据丢失承担超出适用法律要求的责任。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第11章 免责声明</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              11.1 平台及所有 AI 输出均按“现状”与“可用”提供，在适用法律允许的范围内，不作任何明示或暗示的保证，包括但不限于适销性、特定用途适用性、非侵权性、准确性或持续可用性的保证。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              11.2 AI 生成具有概率性和局限性，输出可能不准确、不完整或不符合预期，您应对生成结果进行独立判断与人工审核后方可发布或商用。平台不保证 AI 生成内容的原创性，不保证唯一性，不保证排他性，不保证一定受到版权保护，不保证一定可以商业使用；亦不保证其原创性，不保证其唯一性，不保证其排他性，不保证其一定受到版权保护，不保证其一定可以商业使用。具体是否可发布或商用应由您自行评估并遵守适用法律、第三方模型或服务的适用许可条件以及平台相关政策。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              11.3 对于因免费额度限制、排队拥塞、第三方依赖或您自身网络环境导致的体验问题，平台不作可用性或时效性承诺。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第12章 责任限制</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              12.1 在适用法律允许的最大范围内，平台对任何间接、附带、特殊、后果性或惩罚性损害，以及利润、商誉或数据损失不承担责任，即使已被告知可能发生。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              12.2 对于任何索赔，平台的累计总责任不超过您在索赔发生前 12 个月内就相关服务实际支付的费用总额；若您为免费用户，则不超过适用法律允许范围内的合理限额。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              12.3 上述限制不适用于因平台故意或重大过失导致的人身伤害，或依法不得限制的责任。本条款不影响您在消费者所在地法律规定的、依法不得排除或限制的强制性权利。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第13章 赔偿与抗辩</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              13.1 如因您的内容、行为或违反本条款导致第三方索赔、行政调查或诉讼，您应自费进行抗辩、赔偿并使平台及关联方免受损害，包括合理的律师费与和解费用。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              13.2 平台保留在相关争议中自行选择律师、参与抗辩或寻求和解的权利，您应提供必要配合。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              13.3 本条义务在账户注销或本条款终止后仍继续有效。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第14章 服务的变更、中断、暂停与终止</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              14.1 平台可基于运营、安全、合规或成本原因，随时变更、限制、暂停或终止部分或全部服务，重大变更将提前合理期限公告。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              14.2 您可随时停止使用并申请注销账户；账户注销后，未备份的内容可能被清理，订阅权益按相关付费规则处理。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              14.3 如您长期未登录、违反条款、位于非开放地区或存在风险交易，平台有权在通知或不通知的情况下暂停或终止向您提供服务，且不承担退还未使用免费额度的额外义务（消费者依法享有的强制性权利除外）。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第15章 账户处置、封禁与申诉</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              15.1 对于违规账户，平台可根据情节采取警告、限流、扣除违规收益、限制发布、临时封禁或永久封禁等梯度处置。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              15.2 封禁或限制措施将通过站内信或公告等方式说明原因与期限，您可在合理期限内通过平台提供的官方反馈、支持或联系渠道提交复核材料。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              15.3 经复核确认误判的，平台将恢复账户或补偿相应额度；确认违规的，处置决定为终局，已执行的处置不予撤销。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第16章 知识产权投诉与侵权处理</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              16.1 平台尊重知识产权，设立投诉通道受理版权、商标及声音或肖像等侵权通知。投诉应包含权利证明、侵权链接、联系方式及诚信声明。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              16.2 收到合格通知后，平台将依法采取删除、屏蔽、断开链接等必要措施，并通知被投诉方；被投诉方可提交不侵权声明及反证申请恢复。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              16.3 对于恶意、虚假投诉或反复侵权的用户，平台有权限制投诉权限、列入黑名单并依法追究责任。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第17章 争议解决、适用法律与管辖法院</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              17.1 本条款的订立、效力、解释、履行及争议解决均适用适用法律。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              17.2 双方应首先通过友好协商解决争议；协商不成的，任何一方可向具有相应管辖权的法院提起诉讼或依法申请其他争议解决程序。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              17.3 本条款不影响消费者所在地法律规定的、依法不得排除或限制的强制性权利。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第18章 可分割性、完整协议与弃权</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              18.1 如本条款任何条文被认定为无效或不可执行，该条文应在必要范围内限缩或替换，其余条文仍具完全效力。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              18.2 本条款连同引用的各项政策构成双方就服务达成的完整协议，取代此前所有口头或书面约定。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              18.3 平台未行使或延迟行使某项权利，不构成对该权利的放弃；单次或部分行使亦不妨碍后续行使。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第19章 未成年人与监护人责任</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              19.1 未成年人应在监护人陪同与指导下使用服务，监护人应对未成年人的注册、付费及内容发布行为承担监督与法律责任。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              19.2 平台不向已知未满 13 周岁的儿童主动收集个人信息；如发现误收集，将及时删除。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              19.3 如监护人发现未成年人未经同意产生付费或发布不当内容，应及时通过平台提供的官方反馈、支持或联系渠道联系平台协商处理。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第20章 出口管制、制裁与合规承诺</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              20.1 您承诺遵守适用的出口管制、制裁、反洗钱及相关法律法规，不将服务用于被禁止的目的地、主体或军事用途。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              20.2 如因您的违规导致平台遭受处罚、封禁或损失，您应承担全部责任并赔偿。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              20.3 对于受限地区或高风险交易，平台有权采取增强验证、限制功能或拒绝服务的合规措施。
            </p>
          </section>

          <section className="py-6 border-b border-[#2a2a2a]">
            <h2 className="text-xl font-semibold text-white mb-3">第21章 条款的修改、通知与语言</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              21.1 平台可能不时修订本条款及相关政策，修订内容将提前通过官网公告、站内信或平台通知等方式发布；重大不利变更将提前合理期限通知。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              21.2 通知自发送或公告之日视为送达；您有义务保持联系方式有效并定期查阅条款更新。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              21.3 本条款以中文为准，如存在多语言版本，中文版与外文版不一致时以中文版为准。
            </p>
          </section>

          <section className="py-6">
            <h2 className="text-xl font-semibold text-white mb-3">第22章 联系我们与投诉反馈</h2>
            <p className="text-sm leading-relaxed text-[#b0b0b0]">
              22.1 如您对本条款、服务或账户处置有任何疑问、意见或投诉，用户可以通过平台提供的官方反馈、支持或联系渠道提交问题和投诉，平台将在合理期限内回复。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              22.2 紧急安全或侵权事项建议通过官方渠道提交时注明紧急事由并附完整证据材料以便加速处理。
            </p>
            <p className="text-sm leading-relaxed text-[#b0b0b0] mt-2">
              22.3 平台的联系渠道信息以平台内公示的官方反馈、支持或联系入口为准。
            </p>
          </section>
        </div>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            使用本平台即表示您已阅读、理解并同意遵守本服务条款。如您不同意本条款，请停止使用本平台相关服务。本条款不影响消费者所在地法律规定的、依法不得排除或限制的强制性权利。
          </p>
          <p className="text-xs text-[#666666] text-center mt-2">{t('legal.rights')}</p>
        </div>
      </div>
    </div>
  );
}

export default TermsOfService;
