"use client";

import { CSSProperties } from "react";

interface ShinyTextProps {
  text: string;
  className?: string;
  speed?: number;
  shineColor?: string;
}

export default function ShinyText({
  text,
  className = "",
  speed = 3,
  shineColor = "rgba(255,255,255,0.6)",
}: ShinyTextProps) {
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(
      120deg,
      transparent 40%,
      ${shineColor} 50%,
      transparent 60%
    )`,
    backgroundSize: "200% 100%",
    WebkitBackgroundClip: "text",
    backgroundClip: "text",
    color: "transparent",
    animation: `shiny-text ${speed}s linear infinite`,
    display: "inline-block",
  };

  return (
    <>
      <style>{`
        @keyframes shiny-text {
          0% { background-position: 100% 50%; }
          100% { background-position: -100% 50%; }
        }
      `}</style>
      <span className={className} style={style}>
        {text}
      </span>
    </>
  );
}
