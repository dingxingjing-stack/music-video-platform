import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '../../i18n';

interface PathEditorProps {
  pathId: string;
  icon: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: (id: string) => void;
  children?: React.ReactNode;
}

export function PathEditor({
  pathId,
  icon,
  selected,
  disabled,
  onSelect,
  children,
}: PathEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const { t } = useTranslation();

  const handleSelect = useCallback(() => {
    onSelect(pathId);
    if (selected) setExpanded(!expanded);
    else setExpanded(true);
  }, [pathId, selected, expanded, onSelect]);

  return (
    <motion.div
      whileHover={{ scale: selected ? 1.01 : 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      className={`relative rounded-xl border transition-all duration-300 
        ${selected
          ? 'border-[#ff6a10]/50 bg-[#1f1f1f] shadow-xl shadow-[#ff6a10]/10 ring-1 ring-[#ff6a10]/20'
          : 'border-[#2a2a38] bg-[#1f1f1f] hover:border-[#3a3a48] hover:bg-[#262626]'
        } 
        ${disabled ? 'opacity-40 pointer-events-none' : 'cursor-pointer'}
        backdrop-blur-sm`}
    >
      {/* 氛围光晕 (selected 时) */}
      {selected && (
        <motion.div
          layoutId={`glow-${pathId}`}
          className="absolute inset-0 rounded-xl bg-gradient-to-br from-[#ff6a10]/10 via-[#533afd]/5 to-[#f96bee]/5 blur-sm pointer-events-none"
          transition={{ type: 'spring', damping: 30, stiffness: 350 }}
        />
      )}

      <div
        onClick={handleSelect}
        className="relative z-10 p-4 flex items-center justify-between"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <motion.span
            animate={{ rotate: selected ? 0 : 0 }}
            className="text-2xl shrink-0"
          >
            {icon}
          </motion.span>
          <div className="min-w-0">
            <h3 className="font-semibold text-sm text-[#e0e0e0] truncate" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {t(`paths.path${pathId.toUpperCase()}`)}
            </h3>
            <p className="text-xs text-[#b0b0b0] mt-0.5 line-clamp-1">
              {t(`paths.path${pathId.toUpperCase()}Desc`)}
            </p>
          </div>
        </div>

        {/* 展开/收起指示器 */}
        {selected && (
          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.25 }}
            className="text-[#777777] text-lg ml-2 shrink-0"
          >
            ▾
          </motion.span>
        )}
      </div>

      {/* 展开的详细编辑区 */}
      <AnimatePresence initial={false}>
        {selected && expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 border-t border-white/5 space-y-3">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}