/** 音色克隆合规协议弹窗 v2 — 强制勾选 + 多语言 */
import { useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';

const CONSENT_KEY = 'zyvexo_clone_consent';

const CONSENT_TEXTS: Record<string, { title: string; lines: string[]; checkbox: string; confirm: string; cancel: string }> = {
  'zh': {
    title: '声音克隆法律授权协议',
    lines: [
      '本人承诺上传的音频为本人自有合法录音，绝不上传他人、公众人物、明星人声；',
      '禁止利用克隆音色制作造谣、侵权、诈骗、色情暴力等内容；',
      '平台永久留存操作日志、上传音频、生成记录，用于监管溯源，存储时长≥6个月；',
      '违规账号将直接删除全部私有音色并封禁，相关内容平台有权清除。',
    ],
    checkbox: '我已阅读并同意以上全部条款',
    confirm: '✓ 已同意，开始克隆',
    cancel: '取消',
  },
  'en': {
    title: 'Voice Clone Legal Consent',
    lines: [
      'I confirm the uploaded audio is my own lawful recording. I will never upload voices of others, celebrities, or public figures;',
      'I will not use cloned voices for defamation, infringement, fraud, or obscene/violent content;',
      'The platform permanently retains operation logs, uploaded audio, and generation records for regulatory audit (≥6 months);',
      'Violating accounts will have all private voices deleted and the account banned.',
    ],
    checkbox: 'I have read and agree to all terms above',
    confirm: '✓ Agreed, start cloning',
    cancel: 'Cancel',
  },
  'pt': {
    title: 'Consentimento Legal para Clonagem de Voz',
    lines: [
      'Confirmo que o áudio enviado é minha própria gravação legal. Nunca enviarei vozes de terceiros, celebridades ou figuras públicas;',
      'É proibido usar vozes clonadas para difamação, infração, fraude ou conteúdo obsceno/violento;',
      'A plataforma retém permanentemente logs, áudios e registros para auditoria regulatória (≥6 meses);',
      'Contas violadoras terão todas as vozes privadas excluídas e a conta banida.',
    ],
    checkbox: 'Li e concordo com todos os termos acima',
    confirm: '✓ Concordo, começar',
    cancel: 'Cancelar',
  },
  'es': {
    title: 'Consentimiento Legal para Clonación de Voz',
    lines: [
      'Confirmo que el audio subido es mi propia grabación legal. Nunca subiré voces de terceros, celebridades o figuras públicas;',
      'Prohibido usar voces clonadas para difamación, infracción, fraude o contenido obsceno/violento;',
      'La plataforma retiene permanentemente logs, audios y registros para auditoría (≥6 meses);',
      'Las cuentas infractoras serán eliminadas y baneadas.',
    ],
    checkbox: 'He leído y acepto todos los términos',
    confirm: '✓ Acepto, comenzar',
    cancel: 'Cancelar',
  },
  'fr': {
    title: 'Consentement Légal pour Clonage Vocal',
    lines: [
      'Je confirme que l\'audio est mon propre enregistrement légal. Je ne téléverserai jamais la voix d\'autrui, de célébrités ou de personnalités publiques;',
      'Interdit d\'utiliser des voix clonées pour diffamation, infraction, fraude ou contenu obscène/violent;',
      'La plateforme conserve les logs, audios et enregistrements pour audit (≥6 mois);',
      'Les comptes contrevenants seront supprimés et bannis.',
    ],
    checkbox: 'J\'ai lu et accepte tous les termes ci-dessus',
    confirm: '✓ J\'accepte, commencer',
    cancel: 'Annuler',
  },
  'de': {
    title: 'Rechtliche Einwilligung zur Stimmklonung',
    lines: [
      'Ich bestätige, dass das Audio meine eigene rechtmäßige Aufnahme ist. Ich werde niemals Stimmen anderer oder Prominenter hochladen;',
      'Verboten: Verwendung geklonter Stimmen für Verleumdung, Betrug oder obszone/gewalttätige Inhalte;',
      'Die Plattform speichert dauerhaft Logs und Audios zur Überwachung (≥6 Monate);',
      'Verstöße führen zu Löschung aller privaten Stimmen und Kontosperrung.',
    ],
    checkbox: 'Ich habe alle Bedingungen gelesen und stimme zu',
    confirm: '✓ Zugestimmt, beginnen',
    cancel: 'Abbrechen',
  },
  'ja': {
    title: '音声クローン法的同意',
    lines: [
      'アップロードする音声は本人の合法的な録音であることを確認します。他人の声は絶対にアップロードしません；',
      'クローン音声を用いた誹謗、詐欺、猥褻/暴力コンテンツの制作を禁止します；',
      'プラットフォームは規制監査のため操作ログ等を永続保存します（≥6ヶ月）；',
      '違反アカウントは全プライベート音声が削除され凍結されます。',
    ],
    checkbox: '上記全条件に同意します',
    confirm: '✓ 同意、開始',
    cancel: 'キャンセル',
  },
  'ko': {
    title: '음성 클론 법적 동의',
    lines: [
      '업로드하는 오디오는 본인의 합법적 녹음임을 확인합니다；',
      '클론 음성을 사용한 명예훼손, 사기, 음란/폭력 콘텐츠 제작을 금지합니다；',
      '플랫폼은 규제 감사를 위해 로그 등을 영구 보관합니다(≥6개월)；',
      '위반 계정은 모든 개인 음성이 삭제되고 정지됩니다.',
    ],
    checkbox: '위 모든 약관에 동의합니다',
    confirm: '✓ 동의, 시작',
    cancel: '취소',
  },
  'ru': {
    title: 'Юридическое согласие на клонирование голоса',
    lines: [
      'Подтверждаю, что аудио — моя законная запись；',
      'Запрещено использовать клонированные голоса для клеветы, мошенничества или непристойного контента；',
      'Платформа хранит логи и аудио для аудита (≥6 месяцев)；',
      'Нарушающие аккаунты будут удалены и заблокированы.',
    ],
    checkbox: 'Я прочитал и согласен со всеми условиями',
    confirm: '✓ Согласен, начать',
    cancel: 'Отмена',
  },
};

export function CloneConsentModal({ onAgree, onDismiss }: { onAgree: () => void; onDismiss?: () => void }) {
  const [checked, setChecked] = useState(false);
  const { locale } = useTranslation();
  const map: Record<string, string> = { 'zh': 'zh', 'en': 'en', 'pt': 'pt', 'es': 'es', 'fr': 'fr', 'de': 'de', 'ja': 'ja', 'ko': 'ko', 'ru': 'ru' };
  const lang = map[locale?.slice(0, 2)] || 'zh';
  const t = CONSENT_TEXTS[lang] || CONSENT_TEXTS['zh'];

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onDismiss}>
      <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8 w-full max-w-lg mx-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-white mb-2">⚖️ {t.title}</h2>
        <div className="space-y-2 mb-4 mt-4">
          {t.lines.map((line, i) => (
            <p key={i} className="text-xs text-zinc-400 leading-relaxed">{i + 1}. {line}</p>
          ))}
        </div>
        <p className="text-xs text-red-400 mb-4">⚠️ {lang === 'en' ? 'Illegal cloning of others\' voices will result in full legal liability.' : '违规克隆他人声音将承担全部法律责任。'}</p>
        <label className="flex items-start gap-3 cursor-pointer mb-4 p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
          <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} className="mt-1 accent-orange-400 w-4 h-4" />
          <span className="text-sm text-zinc-300">{t.checkbox}</span>
        </label>
        <button onClick={onAgree} disabled={!checked} className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed">
          {t.confirm}
        </button>
        {onDismiss && <button onClick={onDismiss} className="w-full mt-2 py-2 text-xs text-zinc-600 hover:text-white transition">{t.cancel}</button>}
      </div>
    </div>
  );
}

export function hasCloneConsent(): boolean { return localStorage.getItem(CONSENT_KEY) === 'true'; }
export function setCloneConsent(v: boolean): void { localStorage.setItem(CONSENT_KEY, String(v)); }
