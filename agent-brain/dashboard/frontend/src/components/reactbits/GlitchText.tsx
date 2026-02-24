"use client";

import { CSSProperties } from "react";

interface GlitchTextProps {
  text: string;
  className?: string;
  speed?: number;
}

export default function GlitchText({
  text,
  className = "",
  speed = 0.7,
}: GlitchTextProps) {
  return (
    <>
      <style>{`
        .glitch-wrapper {
          position: relative;
          display: inline-block;
        }
        .glitch-wrapper::before,
        .glitch-wrapper::after {
          content: attr(data-text);
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          overflow: hidden;
        }
        .glitch-wrapper::before {
          color: #0ff;
          z-index: -1;
          animation: glitch-1 ${speed}s infinite linear alternate-reverse;
        }
        .glitch-wrapper::after {
          color: #f0f;
          z-index: -2;
          animation: glitch-2 ${speed * 1.2}s infinite linear alternate-reverse;
        }
        @keyframes glitch-1 {
          0% { clip-path: inset(20% 0 30% 0); transform: translate(-2px, 1px); }
          20% { clip-path: inset(50% 0 10% 0); transform: translate(2px, -1px); }
          40% { clip-path: inset(10% 0 60% 0); transform: translate(-1px, 2px); }
          60% { clip-path: inset(40% 0 20% 0); transform: translate(1px, -2px); }
          80% { clip-path: inset(70% 0 5% 0); transform: translate(-2px, 1px); }
          100% { clip-path: inset(30% 0 40% 0); transform: translate(2px, -1px); }
        }
        @keyframes glitch-2 {
          0% { clip-path: inset(60% 0 10% 0); transform: translate(2px, -1px); }
          20% { clip-path: inset(10% 0 50% 0); transform: translate(-2px, 2px); }
          40% { clip-path: inset(30% 0 30% 0); transform: translate(1px, -1px); }
          60% { clip-path: inset(5% 0 70% 0); transform: translate(-1px, 1px); }
          80% { clip-path: inset(40% 0 20% 0); transform: translate(2px, -2px); }
          100% { clip-path: inset(20% 0 50% 0); transform: translate(-2px, 1px); }
        }
      `}</style>
      <span className={`glitch-wrapper ${className}`} data-text={text}>
        {text}
      </span>
    </>
  );
}
