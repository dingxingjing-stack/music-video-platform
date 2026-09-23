import type { LegalDocPair } from './types';

/**
 * AI 音乐版权政策（中英双语）。
 *
 * 中文侧只做不通顺语句的字面修复（原文有机器痕迹：把 AI 生成内容写成“AI 绘画”、
 * “不承担任何游戏因您…”等），义务范围与免责立场与原文一致，未新增任何承诺。
 */
export const COPYRIGHT_DOC: LegalDocPair = {
  zh: {
    sections: [
      {
        title: '1. 适用范围',
        blocks: [
          {
            k: 'p',
            t: '本政策适用于您在 Melovar 平台上使用 AI 音乐生成功能（包括但不限于音乐生成、音频协作、音乐数据处理等）时产生的全部内容（以下简称「AI 生成内容」）。',
          },
        ],
      },
      {
        title: '2. 重要声明',
        blocks: [
          {
            k: 'p',
            b: '您知悉并同意：',
            t: 'AI 生成音乐的版权归属是一个复杂的法律问题。AI 生成内容可能受到以下因素影响：',
          },
          {
            k: 'ul',
            items: [
              '模型训练素材的版权归属问题；',
              '提示词输入的影响与重要性；',
              '平台提供的音乐生成技术、界面设计对最终内容知识产权归属的影响；',
              '不同司法管辖区对 AI 生成内容版权认定的差异；',
              '相关法律法规的不确定性。',
            ],
          },
        ],
      },
      {
        title: '3. 用户的责任与义务',
        blocks: [
          {
            k: 'p',
            t: '本平台对 AI 生成内容的权利不提供任何明示或暗示的保证，包括适销性、特定用途适用性和不侵权性；对于因您使用 AI 生成内容造成的任何直接、间接、附带或衍生损失，本平台不承担责任；即使已被告知此类损失可能发生，亦不承担任何义务或责任。',
          },
          { k: 'p', b: '您必须：', t: '' },
          {
            k: 'ul',
            items: [
              '自行确认使用 AI 生成内容是否符合适用法律；',
              '自行确认您对相关内容的使用权利与商业使用资格；',
              '评估生成内容是否涉及第三方版权或其他知识产权；',
              '自行承担 AI 生成内容可能存在的歧义、误认或误用风险。',
            ],
          },
        ],
      },
      {
        title: '4. 免责声明',
        blocks: [
          {
            k: 'p',
            t: '本平台按「现状」提供服务，不保证无错误、不保证准确性、不保证时效性。我们不对 AI 生成内容的真实性、准确性、可商用性或第三方权利进行任何形式的承诺。',
          },
        ],
      },
      {
        title: '5. 使用建议',
        blocks: [
          {
            k: 'p',
            t: '如您将 AI 生成内容用于商业用途、公开发表或其他需要法律确认的场景，请先咨询专业律师，确认相关内容不违反您所在地区的法律法规，并自行承担相应法律责任。本平台仅提供信息与技术层面的说明，不构成法律意见。',
          },
        ],
      },
    ],
    closing:
      '使用本平台即表示您已阅读并同意本「AI 音乐版权政策」。本政策与《服务条款》不一致时，以《服务条款》为准。',
  },

  en: {
    sections: [
      {
        title: '1. Scope',
        blocks: [
          {
            k: 'p',
            t: 'This policy applies to all content you produce on the Melovar platform using the AI music generation features (including, without limitation, music generation, audio collaboration and music data processing) (“AI-generated content”).',
          },
        ],
      },
      {
        title: '2. Important statement',
        blocks: [
          {
            k: 'p',
            b: 'You acknowledge and agree that ',
            t: 'copyright in AI-generated music is a complex legal question. AI-generated content may be affected by:',
          },
          {
            k: 'ul',
            items: [
              'the copyright position of the material on which the models were trained;',
              'the influence and importance of the prompts you enter;',
              'the effect of the generation technology and interface the platform provides on ownership of the final content;',
              'differences between jurisdictions in how copyright in AI-generated content is treated;',
              'uncertainty in the applicable law.',
            ],
          },
        ],
      },
      {
        title: '3. User responsibilities',
        blocks: [
          {
            k: 'p',
            t: 'The platform gives no express or implied warranty as to rights in AI-generated content, including merchantability, fitness for a particular purpose and non-infringement; the platform is not liable for any direct, indirect, incidental or consequential loss arising from your use of AI-generated content, and assumes no obligation or liability even if advised that such loss might occur.',
          },
          { k: 'p', b: 'You must: ', t: '' },
          {
            k: 'ul',
            items: [
              'satisfy yourself that your use of AI-generated content complies with applicable law;',
              'confirm your own right to use the content and your eligibility to use it commercially;',
              'assess whether generated content involves third-party copyright or other intellectual property;',
              'bear the risk that AI-generated content may be ambiguous, misattributed or misused.',
            ],
          },
        ],
      },
      {
        title: '4. Disclaimers',
        blocks: [
          {
            k: 'p',
            t: 'The platform is provided “as is”. We do not warrant that it is error-free, accurate or up to date, and we make no commitment of any kind as to the truthfulness, accuracy, commercial usability of AI-generated content or as to third-party rights.',
          },
        ],
      },
      {
        title: '5. Advice on use',
        blocks: [
          {
            k: 'p',
            t: 'If you intend to use AI-generated content commercially, publish it, or use it in a situation that needs legal certainty, consult a qualified lawyer first, confirm that the content does not breach the laws of your region, and accept responsibility for the legal consequences yourself. The platform provides information and technical description only, not legal advice.',
          },
        ],
      },
    ],
    closing:
      'By using the platform you confirm that you have read and accept this AI Music Copyright Policy. Where it differs from the Terms of Service, the Terms of Service prevail.',
  },
};
