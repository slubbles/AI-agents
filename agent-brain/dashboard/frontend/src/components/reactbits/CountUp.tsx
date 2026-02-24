"use client";

import { useEffect, useRef, useState } from "react";
import { animate } from "motion";

interface CountUpProps {
  to: number;
  from?: number;
  duration?: number;
  separator?: string;
  decimals?: number;
  className?: string;
  prefix?: string;
  suffix?: string;
}

export default function CountUp({
  to,
  from = 0,
  duration = 2,
  separator = "",
  decimals = 0,
  className = "",
  prefix = "",
  suffix = "",
}: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [hasAnimated, setHasAnimated] = useState(false);

  useEffect(() => {
    if (hasAnimated) return;

    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasAnimated(true);
          animate(from, to, {
            duration,
            onUpdate: (value) => {
              let formatted = value.toFixed(decimals);
              if (separator) {
                const [int, dec] = formatted.split(".");
                const withSep = int.replace(/\B(?=(\d{3})+(?!\d))/g, separator);
                formatted = dec ? `${withSep}.${dec}` : withSep;
              }
              el.textContent = `${prefix}${formatted}${suffix}`;
            },
          });
          observer.disconnect();
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [to, from, duration, separator, decimals, prefix, suffix, hasAnimated]);

  return (
    <span ref={ref} className={className}>
      {prefix}{from}{suffix}
    </span>
  );
}
