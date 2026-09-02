import { useNavigate } from 'react-router-dom';

export function AcceptableUsePolicy() {
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
        <h1 className="text-3xl font-bold text-white mb-2">可接受使用政策</h1>
        <p className="text-sm text-[#888888]">最后更新：2026年8月</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">1. 合法使用原则</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            本平台提供 AI 音乐创作工具和相关服务，仅可用于合法合规用途。您使用本平台时应遵守适用的法律法规以及本政策。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">2. 禁止的内容</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            严禁在本平台上传、传输或展示以下内容：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>违法违规、淫秽色情、暴力恐怖等不当内容；</li>
            <li>侵犯他人人身权、财产权、肖像权、名誉权、隐私权或版权的内容；</li>
            <li>虚假或误导性的信息，尤其意在误导公众影响公共安全的；</li>
            <li>恶意软件、病毒、蠕虫或其他有害代码；</li>
            <li>未经授权的第三方商业性内容。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">3. 人工智能使用规范</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            平台提供的 AI 功能（如自动生成歌词、MIDI 编辑、音乐创作等）应遵循以下原则：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>不得使用 AI 工具侵犯他人版权或知识产权；</li>
            <li>不得滥用 AI 生成内容进行欺诈、诽谤或误导；</li>
            <li>对于 AI 生成内容中的文本、音频、图片或视频，您应自行确保其符合附件、版权或其他法律要求；</li>
            <li>未经许可不得上传输入性和隐私数据内容中的声音、图像或肖像；</li>
            <li>您应负责 ai 生成内容的合法性判断，本平台不承担其后果。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">4. 报告违规行为</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            若您发现任何违反本政策的内容，请通过平台举报系统或邮件联系我们。我们的团队将积极处理并在合理时间内反馈处理结果。本平台有权对涉嫌违规的内容进行审查、限制、审核、版权、删除或直至封禁相关账号。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">5. 账户和访问权限</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            您对您的账户及其凭据（密码、访问令牌等）负有独特责任。如果您发现他人未经授权使用您的账户，请立即通知我们。本平台不负责被您的账户因未经授权的使用而可能导致的任何损失。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">6. 数据保护</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            所有基于本平台的记录和使用数据将按照我们的隐私政策（点此查看）进行收集、处理和保护。若您不同意相关条款，必要时可以停止使用本平台。
          </p>
        </section>

        <section className="py-6">
          <h2 className="text-xl font-semibold text-white mb-3">7. 联系我们</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如对本政策有任何疑问，请通过平台反馈渠道联系我们。我们会在法律允许内进一步讨论如何处理违规行为并可能采取的措施。
          </p>
        </section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            使用本平台即表示您同意遵守本可接受使用政策。如与本政策冲突，本平台保留修改、暂停或终止向您提供服务的权限，且无需提前通知。
          </p>
        </div>
      </div>
    </div>
  );
}
