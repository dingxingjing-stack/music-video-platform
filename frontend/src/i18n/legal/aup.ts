import type { LegalDocPair } from './types';

/** 可接受使用政策（中英双语）。英文为原中文条款的对等翻译，未增删义务范围。 */
export const AUP_DOC: LegalDocPair = {
  zh: {
    sections: [
      {
        title: '1. 合法使用原则',
        blocks: [
          {
            k: 'p',
            t: '本平台提供 AI 音乐创作工具和相关服务，仅可用于合法合规用途。您使用本平台时应遵守适用的法律法规以及本政策。',
          },
        ],
      },
      {
        title: '2. 禁止的内容',
        blocks: [
          { k: 'p', t: '严禁在本平台上传、传输或展示以下内容：' },
          {
            k: 'ul',
            items: [
              '违法违规、淫秽色情、暴力恐怖等不当内容；',
              '侵犯他人人身权、财产权、肖像权、名誉权、隐私权或版权的内容；',
              '虚假或误导性的信息，尤其意在误导公众影响公共安全的；',
              '恶意软件、病毒、蠕虫或其他有害代码；',
              '未经授权的第三方商业性内容。',
            ],
          },
        ],
      },
      {
        title: '3. 人工智能使用规范',
        blocks: [
          {
            k: 'p',
            t: '平台提供的 AI 功能（如自动生成歌词、MIDI 编辑、音乐创作等）应遵循以下原则：',
          },
          {
            k: 'ul',
            items: [
              '不得使用 AI 工具侵犯他人版权或知识产权；',
              '不得滥用 AI 生成内容进行欺诈、诽谤或误导；',
              '对于 AI 生成内容中的文本、音频、图片或视频，您应自行确保其符合适用法律、版权或其他法律要求；',
              '未经许可不得上传包含他人声音、图像或肖像的隐私性内容；',
              '您应负责 AI 生成内容的合法性判断，本平台不承担其后果。',
            ],
          },
        ],
      },
      {
        title: '4. 报告违规行为',
        blocks: [
          {
            k: 'p',
            t: '若您发现任何违反本政策的内容，请通过平台举报系统或邮件联系我们。我们的团队将积极处理并在合理时间内反馈处理结果。本平台有权对涉嫌违规的内容进行审查、限制、下架、删除，直至封禁相关账号。',
          },
        ],
      },
      {
        title: '5. 账户和访问权限',
        blocks: [
          {
            k: 'p',
            t: '您对您的账户及其凭据（密码、访问令牌等）负有独有责任。如果您发现他人未经授权使用您的账户，请立即通知我们。本平台不对因您账户被未经授权访问而可能导致的任何损失承担责任。',
          },
        ],
      },
      {
        title: '6. 数据保护',
        blocks: [
          {
            k: 'p',
            t: '所有基于本平台的记录和使用数据将按照《隐私政策》进行收集、处理和保护。若您不同意相关条款，可以停止使用本平台。',
          },
        ],
      },
      {
        title: '7. 联系我们',
        blocks: [
          {
            k: 'p',
            t: '如对本政策有任何疑问，请通过平台反馈渠道联系我们。我们会在法律允许的范围内进一步讨论违规行为的处理方式及可能采取的措施。',
          },
        ],
      },
    ],
    closing:
      '使用本平台即表示您同意遵守本可接受使用政策。本政策与《服务条款》不一致时，以《服务条款》为准；本平台保留修改、暂停或终止向您提供服务的权利，并在法律允许的范围内决定是否需要提前通知。',
  },

  en: {
    sections: [
      {
        title: '1. Lawful use',
        blocks: [
          {
            k: 'p',
            t: 'This platform provides AI music creation tools and related services and may only be used for lawful purposes. When using the platform you must comply with applicable laws and regulations and with this policy.',
          },
        ],
      },
      {
        title: '2. Prohibited content',
        blocks: [
          { k: 'p', t: 'You must not upload, transmit or display the following on the platform:' },
          {
            k: 'ul',
            items: [
              'unlawful, obscene, pornographic, violent or terrorist content;',
              'content that infringes another person’s personal rights, property rights, image rights, reputation, privacy or copyright;',
              'false or misleading information, in particular information intended to mislead the public or affect public safety;',
              'malware, viruses, worms or other harmful code;',
              'third-party commercial content without authorisation.',
            ],
          },
        ],
      },
      {
        title: '3. Rules for using the AI features',
        blocks: [
          {
            k: 'p',
            t: 'The AI features provided by the platform (automatic lyric writing, MIDI editing, music generation and so on) are subject to the following principles:',
          },
          {
            k: 'ul',
            items: [
              'do not use the AI tools to infringe another party’s copyright or intellectual property;',
              'do not misuse AI-generated content to defame, defraud or mislead;',
              'for text, audio, images or video in AI-generated content, you are responsible for making sure it meets applicable law, copyright and other legal requirements;',
              'do not upload private material containing someone else’s voice, likeness or image without their permission;',
              'you are responsible for judging the lawfulness of AI-generated content; the platform does not take on the consequences.',
            ],
          },
        ],
      },
      {
        title: '4. Reporting violations',
        blocks: [
          {
            k: 'p',
            t: 'If you become aware of content that violates this policy, please contact us through the platform’s reporting channel or by email. Our team will act on it and report the outcome within a reasonable time. The platform may review, restrict, unpublish or remove content suspected of violating this policy, up to and including suspending or banning the related account.',
          },
        ],
      },
      {
        title: '5. Accounts and access',
        blocks: [
          {
            k: 'p',
            t: 'You are solely responsible for your account and its credentials (password, access tokens and so on). If you discover unauthorised use of your account, notify us immediately. The platform is not liable for any loss that may result from unauthorised access to your account.',
          },
        ],
      },
      {
        title: '6. Data protection',
        blocks: [
          {
            k: 'p',
            t: 'Records and usage data generated on the platform are collected, processed and protected in accordance with our Privacy Policy. If you do not agree with those terms you may stop using the platform.',
          },
        ],
      },
      {
        title: '7. Contact us',
        blocks: [
          {
            k: 'p',
            t: 'If you have any question about this policy, contact us through the platform’s feedback channel. We will discuss how a violation is handled and what measures may be taken so far as the law allows.',
          },
        ],
      },
    ],
    closing:
      'By using the platform you agree to comply with this Acceptable Use Policy. Where it conflicts with the Terms of Service, the Terms of Service prevail. The platform reserves the right to modify, suspend or terminate the service to you and decides, within the limits of applicable law, whether advance notice is required.',
  },
};
