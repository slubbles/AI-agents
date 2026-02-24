"use client";

import { useEffect, useState } from "react";
import { api, SystemHealth, Domain, BudgetInfo } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import CountUp from "@/components/reactbits/CountUp";
import ShinyText from "@/components/reactbits/ShinyText";
import DecryptedText from "@/components/reactbits/DecryptedText";
import StarBorder from "@/components/reactbits/StarBorder";
import Squares from "@/components/reactbits/Squares";
import Link from "next/link";

function scoreColor(score: number): string {
  if (score >= 7) return "#00ff88";
  if (score >= 5) return "#ffb300";
  return "#ff4060";
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    active: "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20",
    trial: "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20",
    pending: "bg-[#7c4dff]/10 text-[#7c4dff] border-[#7c4dff]/20",
  };
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border ${colors[status] || "bg-white/5 text-white/50 border-white/10"}`}>
      {status}
    </span>
  );
}

export default function OverviewPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.domains(), api.budget()])
      .then(([h, d, b]) => {
        setHealth(h);
        setDomains(d);
        setBudget(b);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <DecryptedText text="Loading system data..." className="text-xl text-white/60" speed={40} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <p className="text-[#ff4060] text-lg">Connection Error</p>
        <p className="text-white/40 text-sm font-mono">{error}</p>
        <p className="text-white/30 text-xs">Start the API: <code className="text-[#00e5ff]">python dashboard/api.py</code></p>
      </div>
    );
  }

  const h = health!;
  const b = budget!;

  return (
    <div className="space-y-8 max-w-7xl">
      {/* Header */}
      <div className="relative">
        <div className="absolute inset-0 -z-10 opacity-30 rounded-2xl overflow-hidden">
          <Squares speed={0.3} squareSize={50} borderColor="rgba(0,229,255,0.04)" hoverFillColor="rgba(0,229,255,0.08)" />
        </div>
        <div className="py-6">
          <h1 className="text-3xl font-bold tracking-tight">
            <DecryptedText text="System Overview" speed={30} />
          </h1>
          <p className="text-white/40 text-sm mt-2">Autonomous self-improving multi-agent research system</p>
        </div>
      </div>

      {/* Health Score + Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StarBorder color="#00e5ff">
          <div className="p-5">
            <p className="text-white/40 text-xs uppercase tracking-wider mb-2">Health Score</p>
            <div className="flex items-end gap-2">
              <CountUp to={h.health_score} className="text-4xl font-bold text-[#00e5ff]" duration={1.5} />
              <span className="text-white/30 text-sm mb-1">/100</span>
            </div>
            <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#00e5ff] to-[#7c4dff] transition-all duration-1000"
                style={{ width: `${h.health_score}%` }}
              />
            </div>
          </div>
        </StarBorder>

        <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.12)">
          <p className="text-white/40 text-xs uppercase tracking-wider mb-2">Accepted</p>
          <div className="flex items-end gap-2">
            <CountUp to={h.total_accepted} className="text-3xl font-bold text-[#00ff88]" duration={1.2} />
            <span className="text-white/30 text-sm mb-1">/ {h.total_outputs}</span>
          </div>
          <p className="text-white/30 text-xs mt-2">
            {(h.acceptance_rate * 100).toFixed(0)}% acceptance rate
          </p>
        </SpotlightCard>

        <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.12)">
          <p className="text-white/40 text-xs uppercase tracking-wider mb-2">Avg Score</p>
          <CountUp to={h.avg_score} decimals={1} className="text-3xl font-bold" duration={1.2} />
          <p className="text-white/30 text-xs mt-2">
            Threshold: {6.0}/10
          </p>
        </SpotlightCard>

        <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.12)">
          <p className="text-white/40 text-xs uppercase tracking-wider mb-2">Budget Today</p>
          <CountUp to={b.today.remaining} decimals={2} prefix="$" className="text-3xl font-bold text-[#00e5ff]" duration={1.2} />
          <p className="text-white/30 text-xs mt-2">
            ${b.today.spent.toFixed(4)} spent / ${b.today.limit.toFixed(2)} limit
          </p>
        </SpotlightCard>
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: "Domains", value: h.domain_count, color: "#00e5ff" },
          { label: "Strategies", value: h.domains_with_strategy, color: "#7c4dff" },
          { label: "Knowledge Bases", value: h.domains_with_kb, color: "#00ff88" },
          { label: "In Trial", value: h.domains_in_trial, color: "#ffb300" },
          { label: "Pending", value: h.domains_with_pending, color: "#ff4060" },
          { label: "Principles", value: h.principle_count, color: "#00e5ff" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white/[0.02] border border-white/5 rounded-xl p-4 text-center">
            <CountUp to={value} className="text-2xl font-bold" duration={1} />
            <p className="text-[10px] text-white/30 mt-1 uppercase tracking-wider">{label}</p>
          </div>
        ))}
      </div>

      {/* Domain Cards */}
      <div>
        <h2 className="text-lg font-semibold mb-4 text-white/80">Domains</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {domains.map((d) => (
            <Link key={d.name} href={`/domain/${d.name}`}>
              <SpotlightCard
                className="cursor-pointer hover:border-white/20 transition-colors"
                spotlightColor={`${scoreColor(d.avg_score)}22`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold capitalize">{d.name}</h3>
                  {statusBadge(d.strategy_status)}
                </div>

                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <p className="text-white/30 text-[10px] uppercase">Outputs</p>
                    <p className="text-lg font-semibold">{d.outputs}</p>
                  </div>
                  <div>
                    <p className="text-white/30 text-[10px] uppercase">Accepted</p>
                    <p className="text-lg font-semibold text-[#00ff88]">{d.accepted}</p>
                  </div>
                  <div>
                    <p className="text-white/30 text-[10px] uppercase">Avg Score</p>
                    <p className="text-lg font-semibold" style={{ color: scoreColor(d.avg_score) }}>
                      {d.avg_score.toFixed(1)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-white/30">
                  <span className="font-mono">{d.strategy_version}</span>
                  <span>
                    {d.has_kb ? `${d.kb_claims} claims` : "No KB"}
                  </span>
                </div>
              </SpotlightCard>
            </Link>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <Link
          href="/loop"
          className="px-4 py-2.5 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/20 rounded-lg text-sm hover:bg-[#00e5ff]/20 transition-colors"
        >
          ⟳ Launch Loop
        </Link>
      </div>
    </div>
  );
}
