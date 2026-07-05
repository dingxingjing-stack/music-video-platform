/**
 * PathSelector — Three-path workflow selector with batch mode toggle.
 *
 * Displays Path A/B/C cards and lets the user switch between them.
 * Disables selection while a workflow is running.
 */

import { useTranslation } from '../../i18n';
import { PATHS } from '../../types/trackStudio';

interface Props {
  selectedPath: 'a' | 'b' | 'c' | 'd';
  running: boolean;
  onSelectPath: (path: 'a' | 'b' | 'c' | 'd') => void;
}

export function PathSelector({
  selectedPath,
  running,
  onSelectPath,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-3 gap-3">
      {PATHS.map((p) => (
        <button
          key={p.id}
          onClick={() => onSelectPath(p.id)}
          disabled={running}
          className={`p-4 rounded-xl border-2 text-left transition-all ${
            selectedPath === p.id
              ? 'border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/20'
              : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'
          } ${running ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xl">{p.icon}</span>
            <span className="font-semibold text-sm">
              {t(`paths.path${p.id.toUpperCase()}`)}
            </span>
          </div>
          <p className="text-xs text-gray-400">{t(`paths.path${p.id.toUpperCase()}Desc`)}</p>
        </button>
      ))}
    </div>
  );
}
