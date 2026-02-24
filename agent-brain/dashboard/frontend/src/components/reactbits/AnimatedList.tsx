"use client";

import { ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

interface AnimatedListProps {
  children: ReactNode[];
  delay?: number;
  className?: string;
}

export default function AnimatedList({
  children,
  delay = 100,
  className = "",
}: AnimatedListProps) {
  const [visibleCount, setVisibleCount] = useState(0);

  useEffect(() => {
    if (visibleCount >= children.length) return;
    const timer = setTimeout(() => setVisibleCount((c) => c + 1), delay);
    return () => clearTimeout(timer);
  }, [visibleCount, children.length, delay]);

  return (
    <div className={className}>
      <AnimatePresence>
        {children.slice(0, visibleCount).map((child, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          >
            {child}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
