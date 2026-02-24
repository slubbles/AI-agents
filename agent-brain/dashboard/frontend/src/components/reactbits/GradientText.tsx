"use client";

import { CSSProperties } from "react";

interface GradientTextProps {
  children: string;
  className?: string;
  colors?: string[];
  speed?: number;
}

export default function GradientText({
  children,
  className = "",
  colors = ["#00e5ff", "#7c4dff", "#ff4081", "#00e5ff"],
  speed = 4,
}: GradientTextProps) {
  const gradient = colors.join(", ");
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(90deg, ${gradient})`,
    backgroundSize: "300% 100%",
    WebkitBackgroundClip: "text",
    backgroundClip: "text",
    color: "transparent",
    animation: `gradient-text ${speed}s ease infinite`,
    display: "inline-block",
  };

  return (
    <>
      <style>{`
        @keyframes gradient-text {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
      `}</style>
      <span className={className} style={style}>
        {children}
      </span>
    </>
  );
}
