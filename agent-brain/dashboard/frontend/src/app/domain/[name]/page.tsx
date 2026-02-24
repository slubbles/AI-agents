"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { api, DomainDetail, ResearchOutput } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import CountUp from "@/components/reactbits/CountUp";
import DecryptedText from "@/components/reactbits/DecryptedText";
import StarBorder from "@/components/reactbits/StarBorder";
import Link from "next/link";

function scoreColor(score: number): string {
  if (score >= 7) return "#00ff88";
  if (score >= 5) return "#ffb300";
  return "#ff4060";
}

function ScoreBar({ label, score, max = 10 }: { label: string; score: number; max?: number }) {
  const pct = (score / max) * 100;
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-[10px] text-white/30 capitalize">{label}</span>
        <span className="text-[10px] font-mono" style={{ color: scoreColor(score) }}>{score}</span>
      </div>
      <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: pct + "%", backgroundColor: scoreColor(score) }}
        />
      </div>
    </div>
  );
}

const DOMAIN_ICONS: Record<string, string> = {
  crypto: "₿", ai: "⚡", cybersecurity: "🛡", geopolitics: "🌍", physics: "⚛", general: "◈",
};

export default function DomainPage() {
  const params = useParams();
  const name = params.name as string;
  const [detail, setDetail] = useState<DomainDetail | null>(null);
  const [outputs, setOutputs] = useState<ResearchOutput[]>([]);
  const [strategy, setStrategy] = useState<Record<string, unknown> | null>(null);
  const [kb, setKb] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"outputs" | "strategy" | "knowledge">("outputs");

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.domain(name),
      api.domainOutputs(name),
      api.domainStrategy(name).catch(() => null),
      api.domainKb(name).catch(() => null),
    ]).then(([d, o, s, k]) => {
      setDetail(d);
      setOutputs(o);
      setStrategy(s);
      setKb(k);
      setLoading(false);
    }).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, [name]);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading && !detail) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <DecryptedText text={"Loading " + name + "..."} className="text-xl text-white/60" speed={40} />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="text-4xl opacity-20">⚠️</div>
        <p className="text-[#ff4060]">Failed to load domain</p>
        <p className="text-white/30 text-sm font-mono">{error || "Domain not found"}</p>
        <button onClick={loadData} className="px-4 py-2 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-sm">↻ Retry</button>
        <Link href="/" className="text-white/30 text-xs hover:text-white/50">← Back to Overview</Link>
      </div>
    );
  }

  const t = detail.trajectory;
  const d = detail.stats;

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Link href="/" className="text-white/25 text-xs hover:text-white/50 transition-colors">← Overview</Link>
          <h1 className="text-2xl font-bold tracking-tight mt-1 flex items-center gap-3">
            <span className="text-2xl">{DOMAIN_ICONS[name] || "◈"}</span>
            <DecryptedText text={name.charAt(0).toUpperCase() + name.slice(1)} speed={30} />
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <span className={"text-xs px-3 py-1.5 rounded-full border font-medium " + (
            t.trend === "improving"
              ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
              : t.trend === "declining"
              ? "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
              : t.trend === "stable"
              ? "bg-[#00e5ff]/10 text-[#00e5ff] border-[#00e5ff]/20"
              : "bg-white/5 text-white/40 border-white/10"
          )}>
            {t.trend === "improving" ? "↗ Improving" : t.trend === "declining" ? "↘ Declining" : t.trend === "stable" ? "→ Stable" : "? Insufficient data"}
          </span>
          <Link
            href={"/loop?domain=" + name}
            className="px-4 py-1.5 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-xs font-medium hover:bg-[#00e5ff]/20 transition-all"
          >
            🔍 Research this domain
          </Link>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StarBorder color="#00e5ff">
          <div className="p-4 text-center">
            <CountUp to={d.count || 0} className="text-2xl font-bold" duration={1} />
            <p className="text-[10px] text-white/25 uppercase mt-1 tracking-wider">Total Outputs</p>
          </div>
        </StarBorder>
        <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.1)">
          <div className="text-center">
            <CountUp to={d.accepted || 0} className="text-2xl font-bold text-[#00ff88]" duration={1} />
            <p className="text-[10px] text-white/25 uppercase mt-1 tracking-wider">Accepted</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(255, 64, 96, 0.1)">
          <div className="text-center">
            <CountUp to={d.rejected || 0} className="text-2xl font-bold text-[#ff4060]" duration={1} />
            <p className="text-[10px] text-white/25 uppercase mt-1 tracking-wider">Rejected</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.1)">
          <div className="text-center">
            <CountUp to={d.avg_score || 0} decimals={1} className="text-2xl font-bold" duration={1} />
            <p className="text-[10px] text-white/25 uppercase mt-1 tracking-wider">Avg Score</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.1)">
          <div className="text-center">
            <p className="text-lg font-bold font-mono text-[#00e5ff]">
              {strategy ? (strategy.active_version as string) : "default"}
            </p>
            <p className="text-[10px] text-white/25 uppercase mt-1 tracking-wider">Strategy</p>
          </div>
        </SpotlightCard>
      </div>

      {/* Score Trajectory */}
      {t.scores && t.scores.length > 0 && (
        <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white/50">Score Trajectory</h3>
            <div className="flex gap-4 text-[10px] text-white/25 font-mono">
              <span>First: <span style={{ color: scoreColor(t.first_score) }}>{t.first_score}</span></span>
              <span>Best: <span className="text-[#00ff88]">{t.best_score}</span></span>
              <span>Last: <span style={{ color: scoreColor(t.last_score) }}>{t.last_score}</span></span>
              <span className={t.improvement > 0 ? "text-[#00ff88]" : "text-[#ff4060]"}>
                {t.improvement > 0 ? "+" : ""}{(t.improvement || 0).toFixed(1)}
              </span>
            </div>
          </div>
          {/* Chart */}
          <div className="flex items-end gap-1 h-36">
            {t.scores.map((s: { score: number; accepted: boolean; strategy: string }, i: number) => {
              const height = Math.max((s.score / 10) * 100, 5);
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/90 px-2.5 py-1.5 rounded-lg text-[10px] text-white whitespace-nowrap z-20 border border-white/10 pointer-events-none">
                    <span style={{ color: scoreColor(s.score) }}>{s.score}/10</span>
                    <span className="text-white/30 mx-1">|</span>
                    <span className={s.accepted ? "text-[#00ff88]" : "text-[#ff4060]"}>{s.accepted ? "✓" : "✗"}</span>
                    <span className="text-white/30 mx-1">|</span>
                    <span className="text-white/40">{s.strategy}</span>
                  </div>
                  <div
                    className="w-full rounded-t transition-all duration-300 hover:brightness-125 cursor-pointer"
                    style={{
                      height: height + "%",
                      backgroundColor: s.accepted ? scoreColor(s.score) : scoreColor(s.score) + "40",
                      minHeight: "4px",
                    }}
                  />
                </div>
              );
            })}
          </div>
          {/* Threshold line */}
          <div className="relative -mt-[60%] mb-[60%] pointer-events-none">
            <div className="border-t border-dashed border-white/10 w-full" style={{ position: "relative", top: "0" }} />
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/[0.05] pb-0">
        {(["outputs", "strategy", "knowledge"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={"px-5 py-2.5 text-sm transition-all border-b-2 -mb-[1px] rounded-t-lg " + (
              tab === t
                ? "text-[#00e5ff] border-[#00e5ff] bg-[#00e5ff]/[0.03]"
                : "text-white/30 border-transparent hover:text-white/50 hover:bg-white/[0.01]"
            )}
          >
            {t === "outputs" ? "Outputs (" + outputs.length + ")" : t === "strategy" ? "Strategy" : "Knowledge Base"}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "outputs" && (
        <div className="space-y-3">
          {outputs.length === 0 && (
            <div className="text-center py-16">
              <div className="text-4xl opacity-10 mb-3">📝</div>
              <p className="text-white/25">No outputs yet</p>
              <Link href={"/loop?domain=" + name} className="text-[#00e5ff]/60 text-xs hover:text-[#00e5ff] mt-2 inline-block">
                Start researching →
              </Link>
            </div>
          )}
          {outputs.map((o, i) => (
            <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-5 hover:border-white/10 transition-colors group">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/70 group-hover:text-white/90 transition-colors leading-relaxed">{o.question}</p>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className={"text-[10px] px-2.5 py-1 rounded-full border font-bold " + (
                    o.verdict === "accept"
                      ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                      : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
                  )}>
                    {o.verdict === "accept" ? "✓ accepted" : "✗ rejected"}
                  </span>
                  <div className="text-right">
                    <span className="text-2xl font-black" style={{ color: scoreColor(o.score || 0) }}>
                      {o.score}
                    </span>
                    <span className="text-white/15 text-xs">/10</span>
                  </div>
                </div>
              </div>

              {/* Critique breakdown */}
              {o.critique_scores && Object.keys(o.critique_scores).length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-x-4 gap-y-2 mb-4">
                  {Object.entries(o.critique_scores).map(([dim, score]) => (
                    <ScoreBar key={dim} label={dim} score={score} />
                  ))}
                </div>
              )}

              {/* Key insights */}
              {o.key_insights && o.key_insights.length > 0 && (
                <div className="mb-3">
                  <p className="text-[10px] text-white/25 uppercase tracking-wider mb-1.5 font-medium">Key Insights</p>
                  <div className="flex flex-wrap gap-1.5">
                    {o.key_insights.slice(0, 3).map((insight, j) => (
                      <span key={j} className="text-[10px] text-white/40 bg-white/[0.03] border border-white/[0.05] px-2.5 py-1 rounded-lg">
                        {insight.length > 60 ? insight.slice(0, 57) + "..." : insight}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-4 text-[10px] text-white/15 font-mono">
                <span>{o.findings_count} findings</span>
                <span>{o.searches_made} searches</span>
                <span>{o.strategy_version}</span>
                <span className="ml-auto">{o.timestamp ? new Date(o.timestamp).toLocaleDateString() : ""}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "strategy" && (
        <div className="space-y-4">
          {strategy ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.1)">
                  <p className="text-white/25 text-[10px] uppercase tracking-wider mb-2 font-medium">Active Version</p>
                  <p className="text-2xl font-mono font-bold text-[#00e5ff]">{strategy.active_version as string}</p>
                  <p className="text-xs text-white/25 mt-2">Status: <span className="text-white/50">{strategy.status as string}</span></p>
                </SpotlightCard>
                <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.1)">
                  <p className="text-white/25 text-[10px] uppercase tracking-wider mb-2 font-medium">Version Count</p>
                  <p className="text-2xl font-bold">{(strategy.all_versions as string[])?.length || 0}</p>
                  <p className="text-xs text-white/25 mt-2 font-mono">
                    {(strategy.all_versions as string[])?.join(" → ")}
                  </p>
                </SpotlightCard>
              </div>
              {strategy.strategy_text && (
                <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-5">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-3 font-medium">Strategy Content</h3>
                  <pre className="text-sm text-white/60 whitespace-pre-wrap font-mono leading-relaxed max-h-[500px] overflow-y-auto">
                    {strategy.strategy_text as string}
                  </pre>
                </div>
              )}
              {(strategy.history as Array<Record<string, unknown>>)?.length > 0 && (
                <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-5">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-3 font-medium">Version History</h3>
                  <div className="space-y-2">
                    {(strategy.history as Array<Record<string, string>>).map((h, i) => (
                      <div key={i} className="flex items-center gap-3 px-3 py-2 bg-white/[0.01] rounded-lg">
                        <span className="font-mono text-xs text-[#00e5ff]/70 w-12">{h.version}</span>
                        <span className={"text-[10px] px-2 py-0.5 rounded-full border " + (
                          h.status === "active" ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                          : h.status === "rolled_back" ? "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
                          : "bg-white/5 text-white/40 border-white/10"
                        )}>{h.status}</span>
                        <span className="text-[10px] text-white/15 ml-auto font-mono">{h.replaced_at || ""}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-16">
              <div className="text-4xl opacity-10 mb-3">📋</div>
              <p className="text-white/25">Using default strategy</p>
              <p className="text-white/15 text-xs mt-1">Strategy evolves after 3+ scored outputs</p>
            </div>
          )}
        </div>
      )}

      {tab === "knowledge" && (
        <div className="space-y-4">
          {kb ? (
            <>
              {kb.domain_summary && (
                <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.1)">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-3 font-medium">Domain Summary</h3>
                  <p className="text-sm text-white/60 leading-relaxed">{kb.domain_summary as string}</p>
                </SpotlightCard>
              )}
              {(kb.claims as Array<Record<string, unknown>>)?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium">
                    Verified Claims ({(kb.claims as Array<unknown>).length})
                  </h3>
                  {(kb.claims as Array<Record<string, string>>).map((claim, i) => (
                    <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 hover:border-white/10 transition-colors">
                      <div className="flex items-start gap-3">
                        <span className={"text-[10px] px-2 py-0.5 rounded-full border flex-shrink-0 mt-1 font-medium " + (
                          claim.confidence === "established"
                            ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                            : claim.confidence === "high"
                            ? "bg-[#00e5ff]/10 text-[#00e5ff] border-[#00e5ff]/20"
                            : "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20"
                        )}>
                          {claim.confidence}
                        </span>
                        <p className="text-sm text-white/60 leading-relaxed">{claim.claim}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-16">
              <div className="text-4xl opacity-10 mb-3">📚</div>
              <p className="text-white/25">No knowledge base yet</p>
              <p className="text-white/15 text-xs mt-1">Generated after enough accepted outputs</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
