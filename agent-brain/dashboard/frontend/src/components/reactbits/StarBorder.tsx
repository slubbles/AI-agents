"use client";

import { ReactNode, CSSProperties } from "react";

interface StarBorderProps {
  children: ReactNode;
  className?: string;
  color?: string;
  speed?: number;
}

export default function StarBorder({
  children,
  className = "",
  color = "#00e5ff",
  speed = 6,
}: StarBorderProps) {
  const containerStyle: CSSProperties = {
    position: "relative",
    borderRadius: "1rem",
    overflow: "hidden",
    padding: "1px",
  };

  const borderStyle: CSSProperties = {
    position: "absolute",
    inset: "-50%",
    background: `conic-gradient(from 0deg, transparent 0%, ${color} 10%, transparent 20%)`,
    animation: `star-border-spin ${speed}s linear infinite`,
  };

  const innerStyle: CSSProperties = {
    position: "relative",
    borderRadius: "calc(1rem - 1px)",
    background: "rgb(15, 15, 15)",
    zIndex: 1,
  };

  return (
    <>
      <style>{`
        @keyframes star-border-spin {
          100% { transform: rotate(360deg); }
        }
      `}</style>
      <div style={containerStyle} className={className}>
        <div style={borderStyle} />
        <div style={innerStyle}>{children}</div>
      </div>
    </>
  );
}
