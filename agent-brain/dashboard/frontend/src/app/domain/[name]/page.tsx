"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, DomainDetail, ResearchOutput } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import CountUp from "@/components/reactbits/CountUp";
import DecryptedText from "@/components/reactbits/DecryptedText";
import StarBorder from "@/components/reactbits/StarBorder";
import AnimatedList from "@/components/reactbits/AnimatedList";
import Link from "next/link";

function scoreColor(score: number): string {
  if (score >= 7) return "#00ff88";
  if (score >= 5) return "#ffb300";
  return "#ff4060";
}

function ScoreBar({ score, max = 10 }: { score: number; max?: number }) {
  const pct = (score / max) * 100;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: scoreColor(score) }}
        />
      </div>
      <span className="text-xs font-mono w-6 text-right" style={{ color: scoreColor(score) }}>
        {score}
      </span>
    </div>
  );
}

export default function DomainPage() {
  const params = useParams();
  const name = params.name as string;
  const [detail, setDetail] = useState<DomainDetail | null>(null);
  const [outputs, setOutputs] = useState<ResearchOutput[]>([]);
  const [strategy, setStrategy] = useState<Record<string, unknown> | null>(null);
  const [kb, setKb] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"outputs" | "strategy" | "knowledge">("outputs");

  useEffect(() => {
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
    }).catch(() => setLoading(false));
  }, [name]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <DecryptedText text={`Loading ${name}...`} className="text-xl text-white/60" speed={40} />
      </div>
    );
  }

  if (!detail) {
    return <p className="text-white/40">Domain not found</p>;
  }

  const t = detail.trajectory;
  const d = detail.stats;

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-white/30 text-xs hover:text-white/50 transition-colors">← Overview</Link>
          <h1 className="text-2xl font-bold tracking-tight capitalize mt-1">
            <DecryptedText text={name} speed={30} />
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-3 py-1 rounded-full border ${
            detail.stats.accepted > detail.stats.rejected
              ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
              : "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20"
          }`}>
            {t.trend === "improving" ? "↗ Improving" : t.trend === "declining" ? "↘ Declining" : t.trend === "stable" ? "→ Stable" : "? Insufficient data"}
          </span>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StarBorder color="#00e5ff">
          <div className="p-4 text-center">
            <CountUp to={d.count || 0} className="text-2xl font-bold" duration={1} />
            <p className="text-[10px] text-white/30 uppercase mt-1">Total Outputs</p>
          </div>
        </StarBorder>
        <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.1)">
          <div className="text-center">
            <CountUp to={d.accepted || 0} className="text-2xl font-bold text-[#00ff88]" duration={1} />
            <p className="text-[10px] text-white/30 uppercase mt-1">Accepted</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(255, 64, 96, 0.1)">
          <div className="text-center">
            <CountUp to={d.rejected || 0} className="text-2xl font-bold text-[#ff4060]" duration={1} />
            <p className="text-[10px] text-white/30 uppercase mt-1">Rejected</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.1)">
          <div className="text-center">
            <CountUp to={d.avg_score || 0} decimals={1} className="text-2xl font-bold" duration={1} />
            <p className="text-[10px] text-white/30 uppercase mt-1">Avg Score</p>
          </div>
        </SpotlightCard>
        <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.1)">
          <div className="text-center">
            <p className="text-lg font-bold font-mono text-[#00e5ff]">
              {strategy ? (strategy.active_version as string) : "default"}
            </p>
            <p className="text-[10px] text-white/30 uppercase mt-1">Strategy</p>
          </div>
        </SpotlightCard>
      </div>

      {/* Score Trajectory Chart (text-based) */}
      {t.scores && t.scores.length > 0 && (
        <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
          <h3 className="text-sm font-medium text-white/60 mb-4">Score Trajectory</h3>
          <div className="flex items-end gap-1.5 h-32">
            {t.scores.map((s, i) => {
              const height = (s.score / 10) * 100;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                  <div className="absolute -top-6 opacity-0 group-hover:opacity-100 transition-opacity bg-black/80 px-2 py-1 rounded text-[10px] text-white whitespace-nowrap z-10">
                    Score: {s.score} | {s.accepted ? "✓" : "✗"} | {s.strategy}
                  </div>
                  <div
                    className="w-full rounded-t transition-all duration-300"
                    style={{
                      height: `${height}%`,
                      backgroundColor: s.accepted ? scoreColor(s.score) : `${scoreColor(s.score)}40`,
                      minHeight: "4px",
                    }}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[10px] text-white/20 mt-2">
            <span>First: {t.first_score}</span>
            <span>Best: {t.best_score}</span>
            <span>Last: {t.last_score}</span>
            <span>Δ {t.improvement > 0 ? "+" : ""}{t.improvement?.toFixed(1)}</span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/5 pb-0">
        {(["outputs", "strategy", "knowledge"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm transition-all border-b-2 -mb-[1px] ${
              tab === t
                ? "text-[#00e5ff] border-[#00e5ff]"
                : "text-white/40 border-transparent hover:text-white/60"
            }`}
          >
            {t === "outputs" ? `Outputs (${outputs.length})` : t === "strategy" ? "Strategy" : "Knowledge Base"}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "outputs" && (
        <div className="space-y-3">
          {outputs.map((o, i) => (
            <div key={i} className="bg-white/[0.02] border border-white/5 rounded-xl p-4 hover:border-white/10 transition-colors">
              <div className="flex items-start justify-between gap-4 mb-3">
                <p className="text-sm text-white/80 flex-1">{o.question}</p>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${
                    o.verdict === "accept"
                      ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                      : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
                  }`}>
                    {o.verdict}
                  </span>
                  <span className="text-lg font-bold font-mono" style={{ color: scoreColor(o.score || 0) }}>
                    {o.score}
                  </span>
                </div>
              </div>
              {o.critique_scores && Object.keys(o.critique_scores).length > 0 && (
                <div className="grid grid-cols-5 gap-3 mb-3">
                  {Object.entries(o.critique_scores).map(([dim, score]) => (
                    <div key={dim}>
                      <p className="text-[10px] text-white/30 capitalize mb-1">{dim}</p>
                      <ScoreBar score={score} />
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-4 text-[10px] text-white/20">
                <span>{o.findings_count} findings</span>
                <span>{o.searches_made} searches</span>
                <span className="font-mono">{o.strategy_version}</span>
                <span>{o.timestamp ? new Date(o.timestamp).toLocaleString() : ""}</span>
              </div>
            </div>
          ))}
          {outputs.length === 0 && (
            <p className="text-white/30 text-center py-8">No outputs yet</p>
          )}
        </div>
      )}

      {tab === "strategy" && (
        <div className="space-y-4">
          {strategy ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <SpotlightCard>
                  <p className="text-white/30 text-xs uppercase mb-2">Active Version</p>
                  <p className="text-xl font-mono font-bold text-[#00e5ff]">{strategy.active_version as string}</p>
                  <p className="text-xs text-white/30 mt-1">Status: {strategy.status as string}</p>
                </SpotlightCard>
                <SpotlightCard>
                  <p className="text-white/30 text-xs uppercase mb-2">Versions</p>
                  <p className="text-xl font-bold">{(strategy.all_versions as string[])?.length || 0}</p>
                  <p className="text-xs text-white/30 mt-1">
                    {(strategy.all_versions as string[])?.join(", ")}
                  </p>
                </SpotlightCard>
              </div>
              {strategy.strategy_text && (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5">
                  <h3 className="text-xs uppercase tracking-wider text-white/30 mb-3">Strategy Content</h3>
                  <pre className="text-sm text-white/70 whitespace-pre-wrap font-mono leading-relaxed">
                    {strategy.strategy_text as string}
                  </pre>
                </div>
              )}
              {(strategy.history as Array<Record<string, unknown>>)?.length > 0 && (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5">
                  <h3 className="text-xs uppercase tracking-wider text-white/30 mb-3">Version History</h3>
                  <div className="space-y-2">
                    {(strategy.history as Array<Record<string, string>>).map((h, i) => (
                      <div key={i} className="flex items-center gap-3 text-sm">
                        <span className="font-mono text-xs text-white/40">{h.version}</span>
                        <span className="text-[10px] text-white/20">{h.status}</span>
                        <span className="text-[10px] text-white/20">{h.replaced_at}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-white/30 text-center py-8">Using default strategy</p>
          )}
        </div>
      )}

      {tab === "knowledge" && (
        <div className="space-y-4">
          {kb ? (
            <>
              {kb.domain_summary && (
                <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.1)">
                  <h3 className="text-xs uppercase tracking-wider text-white/30 mb-3">Domain Summary</h3>
                  <p className="text-sm text-white/70 leading-relaxed">{kb.domain_summary as string}</p>
                </SpotlightCard>
              )}
              {(kb.claims as Array<Record<string, unknown>>)?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs uppercase tracking-wider text-white/30">
                    Verified Claims ({(kb.claims as Array<unknown>).length})
                  </h3>
                  {(kb.claims as Array<Record<string, string>>).map((claim, i) => (
                    <div key={i} className="bg-white/[0.02] border border-white/5 rounded-xl p-4">
                      <div className="flex items-start gap-3">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border flex-shrink-0 mt-0.5 ${
                          claim.confidence === "established"
                            ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                            : claim.confidence === "high"
                            ? "bg-[#00e5ff]/10 text-[#00e5ff] border-[#00e5ff]/20"
                            : "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20"
                        }`}>
                          {claim.confidence}
                        </span>
                        <p className="text-sm text-white/70">{claim.claim}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-white/30 text-center py-8">No knowledge base generated yet</p>
          )}
        </div>
      )}
    </div>
  );
}
