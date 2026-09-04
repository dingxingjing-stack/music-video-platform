import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../i18n/useTranslation';

export function AIMusicCopyrightPolicy() {
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
        <h1 className="text-3xl font-bold text-white mb-2">{t('legal.titleAiCopyright')}</h1>
        <p className="text-sm text-[#888888]">{t('legal.updated')}</p>
      </div>

      <div className="space-y-6 text-[#cccccc] leading-relaxed">
        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">1. 适用范围</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            本政策适用于您在 Zyvexo 平台上使用 AI 音乐生成功能（包括但不限于音乐生成、音频协作、音乐数据处理等）时产生的全部内容（以下简称「AI 生成内容」）。
          </p>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">2. 重要声明</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            <strong className="text-white">您知悉并同意：</strong>AI 生成音乐的版权归属是一个复杂的法律问题。AI 生成内容可能受到以下因素影响：
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>模型训练素材的版权归属问题；</li>
            <li>提示词输入的影响与重要性；</li>
            <li>平台提供的音乐生成技术、界面设计对最终内容知识产权归属的影响；</li>
            <li>不同司法管辖区对 AI 生成内容版权认定的差异；</li>
            <li>相关法律法规的不确定性。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">3. 用户的责任与义务</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            本平台对 AI 生成内容的权利不提供任何明示或暗示的保证，包括适销性、特定用途适用性和不侵权性；不承担任何游戏因您利用 AI 生成内容造成直接、间接、附属或衍生损失；即使已获得未来事件通知，也不承担任何义务或责任。
          </p>
          <p className="text-sm leading-relaxed text-[#b0b0b0] mt-3">
            <strong className="text-white">您必须：</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm text-[#b0b0b0] mt-2">
            <li>自行使用 AI 生成内容是否符合适用法律；</li>
            <li>自行确认使用权利和商业使用资格；</li>
            <li>评估生成内容是否涉及第三方版权或知识产权！</li>
            <li>不承担平台可能存在的 AI 绘制造成内容误解风险。</li>
          </ul>
        </section>

        <section className="py-6 border-b border-[#2a2a2a]">
          <h2 className="text-xl font-semibold text-white mb-3">4. 免责声明</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            本平台按「现状」提供服务，不保证无错误、不保证准确性、不保证时效性。我们不对 AI 生成内容的真实性、准确性、可商用性或第三方权利进行任何形式的承诺。
          </p>
        </section>

        <section className="py-6">
          <h2 className="text-xl font-semibold text-white mb-3">5. 使用建议</h2>
          <p className="text-sm leading-relaxed text-[#b0b0b0]">
            如您依赖 AI 生成内容用于商业用途、公开发表或需要法律确认的场景，请先咨询专业律师，确认以下内容不违反您所在地区的法律法规，并自行承担相应法律责任。本平台仅提供信息和技术背景查考文档自身内容。
          </p>
        </section>

        <div className="mt-12 pt-6 border-t border-[#2a2a2a]">
          <p className="text-xs text-[#666666] text-center">
            使用本平台即表示您已阅读并同意本「AI 生成内容使用协议」。本平台按照现有用户指导原则要求解释。
          </p>
        </div>
      </div>
    </div>
  );
}
