"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import GradientText from "./reactbits/GradientText";

const links = [
  { href: "/", label: "Overview", icon: "◈" },
  { href: "/loop", label: "Live Loop", icon: "⟳" },
  { href: "/domain/crypto", label: "Crypto", icon: "₿" },
  { href: "/domain/ai", label: "AI", icon: "⚡" },
  { href: "/domain/cybersecurity", label: "Cybersecurity", icon: "🛡" },
  { href: "/domain/geopolitics", label: "Geopolitics", icon: "🌍" },
  { href: "/domain/physics", label: "Physics", icon: "⚛" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 border-r border-white/5 bg-[#08080c] flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 border-b border-white/5">
        <GradientText className="text-xl font-bold tracking-tight" colors={["#00e5ff", "#7c4dff", "#00e5ff"]}>
          Agent Brain
        </GradientText>
        <p className="text-xs text-white/30 mt-1 font-mono">autonomous research system</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {links.map(({ href, label, icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                active
                  ? "bg-white/5 text-[#00e5ff] border border-[#00e5ff]/20"
                  : "text-white/50 hover:text-white/80 hover:bg-white/[0.03] border border-transparent"
              }`}
            >
              <span className="text-base">{icon}</span>
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-white/5">
        <div className="flex items-center gap-2 text-xs text-white/30">
          <span className="w-2 h-2 rounded-full bg-[#00ff88] pulse-dot" />
          <span>System Online</span>
        </div>
      </div>
    </aside>
  );
}
