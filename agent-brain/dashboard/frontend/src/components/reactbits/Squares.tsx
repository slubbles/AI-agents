"use client";

import { useEffect, useRef, useCallback } from "react";

interface SquaresProps {
  className?: string;
  speed?: number;
  squareSize?: number;
  borderColor?: string;
  hoverFillColor?: string;
}

export default function Squares({
  className = "",
  speed = 0.5,
  squareSize = 40,
  borderColor = "rgba(255,255,255,0.06)",
  hoverFillColor = "rgba(0, 229, 255, 0.1)",
}: SquaresProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const mouseRef = useRef({ x: -1, y: -1 });

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = width;
    canvas.height = height;

    const cols = Math.ceil(width / squareSize);
    const rows = Math.ceil(height / squareSize);
    const time = Date.now() * speed * 0.001;
    const mx = mouseRef.current.x;
    const my = mouseRef.current.y;

    ctx.clearRect(0, 0, width, height);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = c * squareSize;
        const y = r * squareSize;

        // Check proximity to mouse
        const cx = x + squareSize / 2;
        const cy = y + squareSize / 2;
        const dist = Math.sqrt((cx - mx) ** 2 + (cy - my) ** 2);
        const maxDist = squareSize * 4;

        if (dist < maxDist && mx >= 0) {
          const alpha = (1 - dist / maxDist) * 0.3;
          ctx.fillStyle = hoverFillColor.replace(/[\d.]+\)$/, `${alpha})`);
          ctx.fillRect(x, y, squareSize, squareSize);
        }

        // Animate opacity based on wave
        const wave = Math.sin(time + c * 0.3 + r * 0.3);
        const alpha = 0.03 + wave * 0.03;
        ctx.strokeStyle = borderColor.replace(/[\d.]+\)$/, `${Math.max(0.02, alpha)})`);
        ctx.strokeRect(x + 0.5, y + 0.5, squareSize - 1, squareSize - 1);
      }
    }

    animRef.current = requestAnimationFrame(draw);
  }, [squareSize, borderColor, hoverFillColor, speed]);

  useEffect(() => {
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [draw]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) {
      mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
  };

  return (
    <canvas
      ref={canvasRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => (mouseRef.current = { x: -1, y: -1 })}
      className={`absolute inset-0 w-full h-full ${className}`}
      style={{ pointerEvents: "auto" }}
    />
  );
}
