import { motion, AnimatePresence } from 'framer-motion';

interface ProgressModalProps {
  visible: boolean;
  title: string;
  progress: number; // 0-100
  message?: string;
}

export function ProgressModal({ visible, title, progress, message }: ProgressModalProps) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm"
        >
          <motion.div
            initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }}
            className="card-glass p-6 w-80 text-center space-y-4"
          >
            <h3 className="text-white font-semibold">{title}</h3>
            <div className="h-2 bg-border-default rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 rounded-full"
                initial={{ width: 0 }} animate={{ width: `${progress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <p className="text-xs text-text-muted">{message || `处理中 ${progress}%`}</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}