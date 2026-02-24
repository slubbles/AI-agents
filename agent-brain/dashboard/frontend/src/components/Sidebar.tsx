"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import GradientText from "./reactbits/GradientText";
import { api } from "@/lib/api";

const DOMAIN_ICONS: Record<string, string> = {
  crypto: "₿", ai: "⚡", cybersecurity: "🛡", geopolitics: "🌍",
  physics: "⚛", biology: "🧬", economics: "📈", general: "◈",
};

const staticLinks = [
  { href: "/", label: "Overview", icon: "◈" },
  { href: "/loop", label: "Live Loop", icon: "⟳" },
  { href: "/scheduler", label: "Scheduler", icon: "⏱" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [domains, setDomains] = useState<string[]>([]);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    api.domains().then((d) => setDomains(d.map((x) => x.name))).catch(() => {});
    const interval = setInterval(() => {
      api.domains().then((d) => setDomains(d.map((x) => x.name))).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const domainLinks = domains.map((d) => ({
    href: "/domain/" + d,
    label: d.charAt(0).toUpperCase() + d.slice(1),
    icon: DOMAIN_ICONS[d] || "◈",
  }));

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed top-4 left-4 z-[60] lg:hidden w-10 h-10 flex items-center justify-center bg-[#08080c] border border-white/10 rounded-xl text-white/60"
      >
        {mobileOpen ? "✕" : "☰"}
      </button>

      {/* Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      <aside className={`fixed left-0 top-0 h-screen w-64 border-r border-white/5 bg-[#08080c] flex flex-col z-50 transition-transform duration-200 ${
        mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      }`}>
        {/* Logo */}
        <div className="p-6 border-b border-white/5">
          <GradientText className="text-xl font-bold tracking-tight" colors={["#00e5ff", "#7c4dff", "#00e5ff"]}>
            Agent Brain
          </GradientText>
          <p className="text-xs text-white/30 mt-1 font-mono">autonomous research system</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {staticLinks.map(({ href, label, icon }) => {
            const active = pathname === href;
            return (
              <Link key={href} href={href} onClick={() => setMobileOpen(false)}
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

          {domainLinks.length > 0 && (
            <>
              <div className="pt-4 pb-1.5 px-3">
                <p className="text-[10px] text-white/20 uppercase tracking-widest font-medium">Domains</p>
              </div>
              {domainLinks.map(({ href, label, icon }) => {
                const active = pathname === href;
                return (
                  <Link key={href} href={href} onClick={() => setMobileOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
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
            </>
          )}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-white/5">
          <div className="flex items-center gap-2 text-xs text-white/30">
            <span className="w-2 h-2 rounded-full bg-[#00ff88] pulse-dot" />
            <span>System Online</span>
          </div>
        </div>
      </aside>
    </>
  );
}
