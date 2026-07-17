import { motion } from 'framer-motion';

const fadeIn = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' } },
};

export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div variants={fadeIn} initial="initial" animate="animate">
      {children}
    </motion.div>
  );
}