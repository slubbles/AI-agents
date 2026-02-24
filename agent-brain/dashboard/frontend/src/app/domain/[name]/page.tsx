"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { api, DomainDetail, ResearchOutput, KnowledgeBase, Strategy, PendingStrategy, KnowledgeGraph } from "@/lib/api";
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
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"outputs" | "strategy" | "knowledge" | "graph">("outputs");
  const [pending, setPending] = useState<PendingStrategy[]>([]);
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.domain(name),
      api.domainOutputs(name),
      api.domainStrategy(name).catch(() => null),
      api.domainKb(name).catch(() => null),
      api.strategyPending(name).catch(() => ({ pending: [] })),
      api.domainGraph(name).catch(() => null),
    ]).then(([d, o, s, k, p, g]) => {
      setDetail(d);
      setOutputs(o);
      setStrategy(s);
      setKb(k);
      setPending(p.pending || []);
      setGraph(g);
      setLoading(false);
    }).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, [name]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleApprove = async (version: string) => {
    try {
      await api.strategyApprove(name, version);
      setActionMsg({ type: "success", text: `Strategy ${version} approved → entering trial` });
      loadData();
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  const handleReject = async (version: string) => {
    try {
      await api.strategyReject(name, version);
      setActionMsg({ type: "success", text: `Strategy ${version} rejected` });
      loadData();
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  const handleRollback = async () => {
    try {
      const result = await api.strategyRollback(name);
      setActionMsg({ type: "success", text: `Rolled back to ${result.rolled_back_to}` });
      loadData();
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  // Auto-clear action messages
  useEffect(() => {
    if (!actionMsg) return;
    const t = setTimeout(() => setActionMsg(null), 5000);
    return () => clearTimeout(t);
  }, [actionMsg]);

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
              {strategy ? strategy.active_version : "default"}
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
        {(["outputs", "strategy", "knowledge", "graph"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={"px-5 py-2.5 text-sm transition-all border-b-2 -mb-[1px] rounded-t-lg " + (
              tab === t
                ? "text-[#00e5ff] border-[#00e5ff] bg-[#00e5ff]/[0.03]"
                : "text-white/30 border-transparent hover:text-white/50 hover:bg-white/[0.01]"
            )}
          >
            {t === "outputs" ? "Outputs (" + outputs.length + ")" : t === "strategy" ? "Strategy" : t === "knowledge" ? "Knowledge Base" : "Graph"}
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
          {/* Action message toast */}
          {actionMsg && (
            <div className={"px-4 py-3 rounded-xl border text-sm " + (
              actionMsg.type === "success"
                ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
            )}>
              {actionMsg.type === "success" ? "✓ " : "✗ "}{actionMsg.text}
            </div>
          )}

          {/* Pending strategies */}
          {pending.length > 0 && (
            <div className="bg-[#7c4dff]/[0.04] border border-[#7c4dff]/20 rounded-xl p-5">
              <h3 className="text-[10px] uppercase tracking-widest text-[#7c4dff]/60 mb-3 font-medium">
                Pending Approval ({pending.length})
              </h3>
              <div className="space-y-3">
                {pending.map((p) => (
                  <div key={p.version} className="bg-white/[0.02] border border-white/[0.05] rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-sm text-[#7c4dff]">{p.version}</span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApprove(p.version)}
                          className="px-3 py-1.5 bg-[#00ff88]/10 text-[#00ff88] border border-[#00ff88]/20 rounded-lg text-xs font-medium hover:bg-[#00ff88]/20 transition-all"
                        >
                          ✓ Approve
                        </button>
                        <button
                          onClick={() => handleReject(p.version)}
                          className="px-3 py-1.5 bg-[#ff4060]/10 text-[#ff4060] border border-[#ff4060]/20 rounded-lg text-xs font-medium hover:bg-[#ff4060]/20 transition-all"
                        >
                          ✗ Reject
                        </button>
                      </div>
                    </div>
                    {p.strategy_text && (
                      <pre className="text-xs text-white/40 whitespace-pre-wrap font-mono mt-2 max-h-32 overflow-y-auto leading-relaxed">
                        {p.strategy_text}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {strategy ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.1)">
                  <p className="text-white/25 text-[10px] uppercase tracking-wider mb-2 font-medium">Active Version</p>
                  <p className="text-2xl font-mono font-bold text-[#00e5ff]">{strategy.active_version}</p>
                  <p className="text-xs text-white/25 mt-2">Status: <span className="text-white/50">{strategy.status}</span></p>
                </SpotlightCard>
                <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.1)">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-white/25 text-[10px] uppercase tracking-wider mb-2 font-medium">Version Count</p>
                      <p className="text-2xl font-bold">{strategy.all_versions?.length || 0}</p>
                    </div>
                    {strategy.all_versions && strategy.all_versions.length > 1 && (
                      <button
                        onClick={handleRollback}
                        className="px-3 py-1.5 bg-[#ffb300]/10 text-[#ffb300] border border-[#ffb300]/20 rounded-lg text-[10px] font-medium hover:bg-[#ffb300]/20 transition-all"
                      >
                        ↩ Rollback
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-white/25 mt-2 font-mono">
                    {strategy.all_versions?.join(" → ")}
                  </p>
                </SpotlightCard>
              </div>
              {strategy.strategy_text && (
                <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-5">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-3 font-medium">Strategy Content</h3>
                  <pre className="text-sm text-white/60 whitespace-pre-wrap font-mono leading-relaxed max-h-[500px] overflow-y-auto">
                    {strategy.strategy_text}
                  </pre>
                </div>
              )}
              {strategy.history && strategy.history.length > 0 && (
                <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-5">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-3 font-medium">Version History</h3>
                  <div className="space-y-2">
                    {strategy.history.map((h, i) => (
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
                  <p className="text-sm text-white/60 leading-relaxed">{kb.domain_summary}</p>
                </SpotlightCard>
              )}
              {kb.claims && kb.claims.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium">
                    Verified Claims ({kb.claims.length})
                  </h3>
                  {kb.claims.map((claim, i) => (
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

      {tab === "graph" && (
        <div className="space-y-4">
          {graph && graph.nodes && graph.nodes.length > 0 ? (
            <>
              {/* Graph Stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Nodes", value: graph.summary?.total_nodes ?? graph.nodes.length, icon: "◉" },
                  { label: "Edges", value: graph.summary?.total_edges ?? graph.edges.length, icon: "⟷" },
                  { label: "Clusters", value: graph.summary?.total_clusters ?? 0, icon: "◈" },
                  { label: "Contradictions", value: graph.contradictions?.length ?? 0, icon: "⚡" },
                ].map(({ label, value, icon }) => (
                  <div key={label} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 text-center">
                    <div className="text-lg opacity-20 mb-1">{icon}</div>
                    <div className="text-lg font-mono text-white/80">{value}</div>
                    <div className="text-[10px] text-white/25 mt-0.5">{label}</div>
                  </div>
                ))}
              </div>

              {/* Nodes List */}
              <div>
                <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium mb-3">Concept Nodes ({graph.nodes.length})</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {graph.nodes.slice(0, 30).map((node, i) => (
                    <div key={i} className="bg-white/[0.02] border border-white/[0.05] rounded-lg p-3 hover:border-white/10 transition-colors">
                      <div className="flex items-center gap-2">
                        <span className={"text-[9px] px-1.5 py-0.5 rounded border font-mono " + (
                          node.type === "concept" ? "bg-[#00e5ff]/10 text-[#00e5ff] border-[#00e5ff]/20"
                          : node.type === "entity" ? "bg-[#ff6b6b]/10 text-[#ff6b6b] border-[#ff6b6b]/20"
                          : node.type === "finding" ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                          : "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20"
                        )}>{node.type}</span>
                        <span className="text-sm text-white/60 truncate">{node.label}</span>
                        <span className="ml-auto text-[9px] font-mono text-white/20">{node.source_count ?? 0} sources</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Edges Sample */}
              {graph.edges.length > 0 && (
                <div>
                  <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium mb-3">Relationships ({graph.edges.length})</h3>
                  <div className="space-y-1.5">
                    {graph.edges.slice(0, 20).map((edge, i) => (
                      <div key={i} className="bg-white/[0.015] border border-white/[0.04] rounded-lg px-3 py-2 flex items-center gap-2 text-xs">
                        <span className="text-white/50 truncate max-w-[30%]">{edge.source}</span>
                        <span className={"px-1.5 py-0.5 rounded text-[9px] font-mono border flex-shrink-0 " + (
                          edge.type === "contradicts" ? "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
                          : edge.type === "supports" ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                          : edge.type === "supersedes" ? "bg-[#ffb300]/10 text-[#ffb300] border-[#ffb300]/20"
                          : "bg-white/5 text-white/40 border-white/10"
                        )}>{edge.type}</span>
                        <span className="text-white/50 truncate max-w-[30%]">{edge.target}</span>
                        <span className="ml-auto text-white/15 font-mono">{((edge.weight ?? 1) * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Build/Rebuild Button */}
              <button
                onClick={async () => {
                  setGraphLoading(true);
                  try {
                    await api.buildGraph(name);
                    const g = await api.domainGraph(name);
                    setGraph(g);
                    setActionMsg({ type: "success", text: "Knowledge graph rebuilt" });
                  } catch (e) {
                    setActionMsg({ type: "error", text: (e as Error).message });
                  } finally { setGraphLoading(false); }
                }}
                disabled={graphLoading}
                className="w-full py-2.5 rounded-lg text-xs border border-white/[0.06] bg-white/[0.02] text-white/40 hover:text-white/60 hover:bg-white/[0.04] transition-all disabled:opacity-30"
              >
                {graphLoading ? "Rebuilding…" : "🔄 Rebuild Graph from KB"}
              </button>
            </>
          ) : (
            <div className="text-center py-16">
              <div className="text-4xl opacity-10 mb-3">🕸</div>
              <p className="text-white/25">No knowledge graph yet</p>
              <p className="text-white/15 text-xs mt-1 mb-4">Build from your knowledge base claims</p>
              <button
                onClick={async () => {
                  setGraphLoading(true);
                  try {
                    await api.buildGraph(name);
                    const g = await api.domainGraph(name);
                    setGraph(g);
                    setActionMsg({ type: "success", text: "Knowledge graph built" });
                  } catch (e) {
                    setActionMsg({ type: "error", text: (e as Error).message });
                  } finally { setGraphLoading(false); }
                }}
                disabled={graphLoading}
                className="px-6 py-2.5 rounded-xl text-xs border border-[#00e5ff]/20 bg-[#00e5ff]/5 text-[#00e5ff]/70 hover:text-[#00e5ff] hover:bg-[#00e5ff]/10 transition-all disabled:opacity-30"
              >
                {graphLoading ? "Building…" : "⚡ Build Knowledge Graph"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
