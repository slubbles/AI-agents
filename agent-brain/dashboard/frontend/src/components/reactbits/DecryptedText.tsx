"use client";

import { useEffect, useRef, useState, CSSProperties, ReactNode } from "react";

interface DecryptedTextProps {
  text: string;
  className?: string;
  speed?: number;
  chars?: string;
  revealDirection?: "start" | "end" | "center";
}

export default function DecryptedText({
  text,
  className = "",
  speed = 50,
  chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()",
  revealDirection = "start",
}: DecryptedTextProps) {
  const [displayed, setDisplayed] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (hasStarted) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 }
    );

    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [hasStarted]);

  useEffect(() => {
    if (!hasStarted) {
      setDisplayed(text.replace(/./g, (c) => (c === " " ? " " : chars[Math.floor(Math.random() * chars.length)])));
      return;
    }

    let revealed = 0;
    const intervals: ReturnType<typeof setInterval>[] = [];

    const mainInterval = setInterval(() => {
      if (revealed >= text.length) {
        clearInterval(mainInterval);
        intervals.forEach(clearInterval);
        setDisplayed(text);
        return;
      }
      revealed++;

      setDisplayed(() => {
        const result = text.split("").map((char, i) => {
          if (i < revealed) return char;
          if (char === " ") return " ";
          return chars[Math.floor(Math.random() * chars.length)];
        });
        return result.join("");
      });
    }, speed);

    return () => {
      clearInterval(mainInterval);
      intervals.forEach(clearInterval);
    };
  }, [hasStarted, text, speed, chars]);

  return (
    <span ref={ref} className={`font-mono ${className}`}>
      {displayed}
    </span>
  );
}
