import { useTranslation } from '../i18n/useTranslation';

type Template = {
  id: string;
  name: string;
  thumbnail: string;
  duration_sec: number;
  license: 'free' | 'premium';
};

interface Props {
  open: boolean;
  onClose: () => void;
  templates: Template[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export const MVTemplatePicker = ({ open, onClose, templates, selectedId, onSelect }: Props) => {
  const { t } = useTranslation();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#121212]/60 backdrop-blur-sm">
      <div className="bg-[#1f1f1f]/90 rounded-xl p-6 w-full max-w-4xl max-h-[80vh] overflow-y-auto border border-[#2a2a38]">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-[#e0e0e0]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>{t('ui.selectTemplate')}</h2>
          <button onClick={onClose} className="text-[#b0b0b0] hover:text-[#e0e0e0]">✕</button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((tpl) => (
            <div
              key={tpl.id}
              className={`cursor-pointer rounded-xl border-2 transition-all ${selectedId === tpl.id ? 'border-[#ff6a10] bg-[#ff6a10]/10' : 'border-[#2a2a38] hover:border-[#3a3a48]'} `}
              onClick={() => onSelect(tpl.id)}
            >
              <img src={tpl.thumbnail} alt={tpl.name} className="w-full h-48 object-cover rounded-t-xl bg-[#262626]" />
              <div className="p-3">
                <p className="font-medium text-[#e0e0e0] truncate">{tpl.name}</p>
                <p className="text-xs text-[#b0b0b0]">{tpl.duration_sec}s • {tpl.license === 'premium' ? 'Premium' : 'Free'}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-gradient-to-r from-[#ff6a10] to-[#f96bee] text-white rounded-lg text-sm font-medium hover:from-[#ff8a30] hover:to-[#ff7bee] transition-colors">
            {t('ui.done') || 'Done'}
          </button>
        </div>
      </div>
    </div>
  );
};
