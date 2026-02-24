"use client";

import { useEffect, useState, useCallback } from "react";
import { api, SystemHealth, Domain, BudgetInfo, DomainComparison, ValidationResult, CostInfo } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import CountUp from "@/components/reactbits/CountUp";
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
    active:  "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20",
    trial:   "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20",
    pending: "bg-[#7c4dff]/10 text-[#7c4dff] border-[#7c4dff]/20",
  };
  return (
    <span className={"text-[10px] px-2 py-0.5 rounded-full border font-medium " + (colors[status] || "bg-white/5 text-white/40 border-white/10")}>
      {status}
    </span>
  );
}

const DOMAIN_ICONS: Record<string, string> = {
  crypto: "₿", ai: "⚡", cybersecurity: "🛡", geopolitics: "🌍", physics: "⚛", general: "◈",
};

export default function OverviewPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const [comparison, setComparison] = useState<DomainComparison[]>([]);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [costInfo, setCostInfo] = useState<CostInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.health(),
      api.domains(),
      api.budget(),
      api.comparison().catch(() => []),
      api.validate().catch(() => null),
      api.cost().catch(() => null),
    ])
      .then(([h, d, b, comp, val, cost]) => {
        setHealth(h);
        setDomains(d);
        setBudget(b);
        setComparison(comp);
        setValidation(val);
        setCostInfo(cost);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Auto-refresh every 30s
  useEffect(() => {
    if (error) return;
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData, error]);

  if (loading && !health) {
    return (
      <div className="space-y-6 max-w-7xl animate-pulse">
        {/* Header skeleton */}
        <div className="flex items-center justify-between">
          <div className="h-8 w-48 bg-white/[0.04] rounded-lg" />
          <div className="h-6 w-24 bg-white/[0.04] rounded-full" />
        </div>
        {/* Metric cards skeleton */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5 h-24">
              <div className="h-4 w-16 bg-white/[0.04] rounded mb-3" />
              <div className="h-7 w-12 bg-white/[0.04] rounded" />
            </div>
          ))}
        </div>
        {/* Secondary metrics skeleton */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 h-16" />
          ))}
        </div>
        {/* Domain cards skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5 h-40" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-5">
        <div className="text-5xl opacity-20">⚠️</div>
        <p className="text-[#ff4060] text-lg font-medium">Connection Error</p>
        <p className="text-white/30 text-sm font-mono max-w-md text-center">{error}</p>
        <div className="flex gap-3 mt-2">
          <button
            onClick={loadData}
            className="px-5 py-2.5 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-sm font-medium hover:bg-[#00e5ff]/20 transition-all"
          >
            ↻ Retry
          </button>
        </div>
        <p className="text-white/20 text-xs mt-4">
          Start the API: <code className="text-[#00e5ff]/60 bg-white/[0.03] px-2 py-0.5 rounded">python dashboard/api.py</code>
        </p>
      </div>
    );
  }

  const h = health!;
  const b = budget!;

  return (
    <div className="space-y-8 max-w-7xl">
      {/* Header */}
      <div className="relative">
        <div className="absolute inset-0 -z-10 opacity-20 rounded-2xl overflow-hidden">
          <Squares speed={0.3} squareSize={50} borderColor="rgba(0,229,255,0.03)" hoverFillColor="rgba(0,229,255,0.06)" />
        </div>
        <div className="py-6">
          <h1 className="text-3xl font-bold tracking-tight">
            <DecryptedText text="System Overview" speed={30} />
          </h1>
          <p className="text-white/30 text-sm mt-2">Autonomous self-improving multi-agent research system</p>
        </div>
      </div>

      {/* Health + Key Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Health Score */}
        <StarBorder color="#00e5ff">
          <div className="p-5">
            <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2 font-medium">Health Score</p>
            <div className="flex items-end gap-2">
              <CountUp to={h.health_score} className="text-4xl font-black text-[#00e5ff]" duration={1.5} />
              <span className="text-white/20 text-sm mb-1">/100</span>
            </div>
            <div className="mt-3 h-2 bg-white/[0.04] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#00e5ff] to-[#7c4dff] transition-all duration-1000"
                style={{ width: h.health_score + "%" }}
              />
            </div>
          </div>
        </StarBorder>

        {/* Accepted */}
        <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.12)">
          <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2 font-medium">Accepted</p>
          <div className="flex items-end gap-2">
            <CountUp to={h.total_accepted} className="text-3xl font-bold text-[#00ff88]" duration={1.2} />
            <span className="text-white/20 text-sm mb-1">/ {h.total_outputs}</span>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-[#00ff88]/60" style={{ width: (h.acceptance_rate * 100) + "%" }} />
            </div>
            <span className="text-[10px] text-white/30 font-mono">{(h.acceptance_rate * 100).toFixed(0)}%</span>
          </div>
        </SpotlightCard>

        {/* Avg Score */}
        <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.12)">
          <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2 font-medium">Avg Score</p>
          <div className="flex items-end gap-1">
            <CountUp to={h.avg_score} decimals={1} className="text-3xl font-bold" duration={1.2} />
            <span className="text-white/20 text-sm mb-1">/10</span>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: (h.avg_score / 10) * 100 + "%", backgroundColor: scoreColor(h.avg_score) }}
              />
            </div>
            <span className="text-[10px] text-white/30">threshold: 6</span>
          </div>
        </SpotlightCard>

        {/* Budget */}
        <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.12)">
          <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2 font-medium">Budget</p>
          <CountUp to={b.today.remaining} decimals={2} prefix="$" className="text-3xl font-bold text-[#00e5ff]" duration={1.2} />
          <p className="text-white/20 text-xs mt-2 font-mono">
            ${b.today.spent.toFixed(4)} spent / ${b.today.limit.toFixed(2)} limit
          </p>
        </SpotlightCard>
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: "Domains",         value: h.domain_count,          color: "#00e5ff", icon: "🌐" },
          { label: "Strategies",      value: h.domains_with_strategy, color: "#7c4dff", icon: "📋" },
          { label: "Knowledge Bases", value: h.domains_with_kb,       color: "#00ff88", icon: "📚" },
          { label: "In Trial",        value: h.domains_in_trial,      color: "#ffb300", icon: "🧪" },
          { label: "Pending",         value: h.domains_with_pending,  color: "#ff6ec7", icon: "⏳" },
          { label: "Principles",      value: h.principle_count,       color: "#00e5ff", icon: "💡" },
        ].map(({ label, value, icon }) => (
          <div key={label} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 text-center hover:border-white/10 transition-colors">
            <div className="text-lg mb-1">{icon}</div>
            <CountUp to={value} className="text-xl font-bold" duration={0.8} />
            <p className="text-[10px] text-white/25 mt-1 uppercase tracking-wider font-medium">{label}</p>
          </div>
        ))}
      </div>

      {/* Domain Cards */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white/70">Domains</h2>
          <Link href="/loop" className="text-xs text-[#00e5ff]/60 hover:text-[#00e5ff] transition-colors">
            Launch Loop →
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {domains.map((d) => (
            <Link key={d.name} href={"/domain/" + d.name}>
              <SpotlightCard
                className="cursor-pointer hover:border-white/15 transition-all group"
                spotlightColor={scoreColor(d.avg_score) + "18"}
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <span className="text-xl">{DOMAIN_ICONS[d.name] || "◈"}</span>
                    <h3 className="font-semibold capitalize text-white/80 group-hover:text-white transition-colors">{d.name}</h3>
                  </div>
                  {statusBadge(d.strategy_status)}
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <p className="text-white/25 text-[10px] uppercase font-medium">Outputs</p>
                    <p className="text-xl font-bold mt-0.5">{d.outputs}</p>
                  </div>
                  <div>
                    <p className="text-white/25 text-[10px] uppercase font-medium">Accepted</p>
                    <p className="text-xl font-bold text-[#00ff88] mt-0.5">{d.accepted}</p>
                  </div>
                  <div>
                    <p className="text-white/25 text-[10px] uppercase font-medium">Avg Score</p>
                    <p className="text-xl font-bold mt-0.5" style={{ color: scoreColor(d.avg_score) }}>
                      {d.avg_score.toFixed(1)}
                    </p>
                  </div>
                </div>

                {/* Score bar */}
                <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden mb-3">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: (d.avg_score / 10) * 100 + "%", backgroundColor: scoreColor(d.avg_score) }}
                  />
                </div>

                <div className="flex items-center justify-between text-[10px] text-white/20">
                  <span className="font-mono">{d.strategy_version}</span>
                  <span>{d.has_kb ? d.kb_claims + " claims" : "No KB yet"}</span>
                </div>
              </SpotlightCard>
            </Link>
          ))}
        </div>
      </div>

      {/* Domain Comparison Table */}
      {comparison.length > 0 && (
        <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5 overflow-x-auto">
          <h2 className="text-sm font-semibold text-white/50 mb-4">Domain Comparison</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] text-white/25 uppercase tracking-wider">
                <th className="text-left pb-3 font-medium">Domain</th>
                <th className="text-center pb-3 font-medium">Outputs</th>
                <th className="text-center pb-3 font-medium">Accepted</th>
                <th className="text-center pb-3 font-medium">Avg Score</th>
                <th className="text-center pb-3 font-medium">Trend</th>
              </tr>
            </thead>
            <tbody>
              {comparison.map((c) => (
                <tr key={c.domain} className="border-t border-white/[0.03] hover:bg-white/[0.01] transition-colors">
                  <td className="py-2.5">
                    <Link href={"/domain/" + c.domain} className="flex items-center gap-2 text-white/70 hover:text-[#00e5ff] transition-colors">
                      <span>{DOMAIN_ICONS[c.domain] || "◈"}</span>
                      <span className="capitalize">{c.domain}</span>
                    </Link>
                  </td>
                  <td className="text-center text-white/40 font-mono">{c.outputs}</td>
                  <td className="text-center text-[#00ff88]/70 font-mono">{c.accepted}</td>
                  <td className="text-center font-mono" style={{ color: scoreColor(c.avg_score) }}>{c.avg_score.toFixed(1)}</td>
                  <td className="text-center">
                    <span className={"text-[10px] px-2 py-0.5 rounded-full " + (
                      c.trend === "improving" ? "text-[#00ff88] bg-[#00ff88]/10"
                      : c.trend === "declining" ? "text-[#ff4060] bg-[#ff4060]/10"
                      : c.trend === "stable" ? "text-[#00e5ff] bg-[#00e5ff]/10"
                      : "text-white/30 bg-white/5"
                    )}>
                      {c.trend === "improving" ? "↗" : c.trend === "declining" ? "↘" : c.trend === "stable" ? "→" : "—"} {c.trend}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Validation + Cost Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Validation */}
        {validation && (
          <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white/50">System Checks</h2>
              <span className={"text-[10px] px-2.5 py-1 rounded-full border font-medium " + (
                validation.valid
                  ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                  : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
              )}>
                {validation.valid ? "✓ All clear" : `⚠ ${validation.issues.length} issue${validation.issues.length !== 1 ? "s" : ""}`}
              </span>
            </div>
            {validation.issues.length > 0 ? (
              <ul className="space-y-1.5">
                {validation.issues.map((issue, i) => (
                  <li key={i} className="text-xs text-[#ffb300]/70 flex items-start gap-2">
                    <span className="text-[#ffb300] mt-0.5">•</span>
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-white/25">No data integrity issues detected.</p>
            )}
          </div>
        )}

        {/* Cost */}
        {costInfo && (
          <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-white/50 mb-3">Cost Efficiency</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-[10px] text-white/25 uppercase tracking-wider font-medium">Today</p>
                <p className="text-lg font-bold text-[#00e5ff] font-mono">${costInfo.today_spend?.toFixed(4) || "0.00"}</p>
              </div>
              <div>
                <p className="text-[10px] text-white/25 uppercase tracking-wider font-medium">All Time</p>
                <p className="text-lg font-bold font-mono">${costInfo.total_all_time?.toFixed(4) || "0.00"}</p>
              </div>
              <div>
                <p className="text-[10px] text-white/25 uppercase tracking-wider font-medium">Budget Left</p>
                <p className="text-lg font-bold text-[#00ff88] font-mono">${costInfo.remaining?.toFixed(2) || "0.00"}</p>
              </div>
              <div>
                <p className="text-[10px] text-white/25 uppercase tracking-wider font-medium">Daily Limit</p>
                <p className="text-lg font-bold font-mono text-white/50">${costInfo.daily_budget?.toFixed(2) || "2.00"}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3 flex-wrap">
        <Link
          href="/loop"
          className="px-5 py-2.5 bg-gradient-to-r from-[#00e5ff]/10 to-[#7c4dff]/10 text-[#00e5ff] border border-[#00e5ff]/20 rounded-xl text-sm font-medium hover:from-[#00e5ff]/20 hover:to-[#7c4dff]/20 transition-all"
        >
          ⟳ Launch Loop
        </Link>
        <button
          onClick={loadData}
          className="px-5 py-2.5 text-white/40 border border-white/10 rounded-xl text-sm hover:text-white/60 hover:border-white/20 transition-all"
        >
          ↻ Refresh
        </button>
      </div>
    </div>
  );
}
