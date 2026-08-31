import { useNavigate } from 'react-router-dom';

export function VoiceCloningPolicy() {
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
        <h1 className="text-3xl font-bold text-white mb-2">声音克隆使用政策</h1>
        <p className="text-sm text-[#888888]">最后更新：2026年8月</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">1. 声音克隆原则</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            Zyvexo 平台ledger声音克隆功能属于高度受限的内容创建工具。使用声音克隆前，您必须符合以下所有条件：
          </p>
          <ul className="list-disc list-inside space-y-<text-sm text-[#b0b0b0] mt-2">
            <li>您必须对您上传的音频拥有完整的所有权或者已获相关权利人的充分授权。</li>
            <li>上传的音频必须为真人，而非音频混音或未经授权的他人声音摹仿。</li>
            <li>音频还必须符合 PROJECT 公测期间发布的内容使用规则。</li>
          </ul>

          <div className="mt-4 p-4 rounded-lg bg-[#1a1a1a] border border-[#ff6a10]/30">
            <p className="text-xs text-[#ff6a10] font-mono">
              ⚠️ <strong>注意：</strong>根据当前功能状态配置，声音克隆（Clone）功能属于 <code className="bg-[#2a2a2a] px-1 rounded">closed</code> 状态，因此普通用户暂时无法使用声音克隆功能，除非相关功能解锁。本政策仅作历史记录用途，不代表当前可用。
            </p>
          </div>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">2. 上传内容的合规要求</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            当您上传音频素材用作声音克隆时，您必须取得特定个人知情同意的书面授权。不得克隆、模仿或冒充任何第三方声音（包括名人、不主权无身份认定等特殊敏感场景、政界人物、公众人物等）。
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li><strong className="text-white">禁止未经授权情况下</strong>，不得冒充他人声音制作虚假信息或进行诈骗；</li>
            <li>不得以任何形式恶意误导公众；；</li>
            <li>不得使用声音层制作骚扰、诽谤、侵犯隐私或传播不实信息之用；</li>
            <li>不得将克隆声音用于违法违规用途。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">3. 授权与授权链条</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如果您的声音被认为克隆的人声，您必须为您提供：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>有效的授权证明（如书面同意书、录音授权协议、官方身份证明）；</li>
            <li>清晰的保密流程说明；</li>
            <li>必要的背 details与拍摄审查记录；</li>
            <li>音频样本库覆盖文件；</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">4. 审核与移除</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            我们有权在不加控制的理由下删除或移除根据声音的判断视为不当内容。您应当知道本平台遵守适用的法律法规，其中包括中华人民共和国网络信息内容生态治理有关规定以及其它适用的国外法律。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">5. 法律责任</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            您在使用声音克隆功能时，必须接受任何由您上传或提交的音频内容而产生的直接或间接责任。您了解并同意：如服务端发现上传行为违反本政策者或内容违规，平台相关方有权采取包括但不限于直接封禁、停用、发布删除内容等一切合法措施，并保留证据和追究法律责任的权利。
          </p>
        </section>

        <section className="py-6">
          <h2 className="text-xl font-semibold text-white mb-3">6. 联系我们</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如果您有任何关于声音克隆的疑问或需要上诉，请通过该平台联系相关部门寻求帮助。
          </p>
        </section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            使用本平台平台服务和相关法律流程、内容和基于发展现状说明当前 restrictions。若当地 regulations 法律性质适用，请参照适用法律。
          </p>
        </div>
      </div>
    </div>
  );
}
