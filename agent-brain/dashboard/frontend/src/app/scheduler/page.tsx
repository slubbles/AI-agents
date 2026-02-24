"use client";

import { useEffect, useState, useCallback } from "react";
import { api, DaemonStatus, ConsensusConfig } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import CountUp from "@/components/reactbits/CountUp";
import DecryptedText from "@/components/reactbits/DecryptedText";
import StarBorder from "@/components/reactbits/StarBorder";
import Link from "next/link";

export default function SchedulerPage() {
  const [daemon, setDaemon] = useState<DaemonStatus | null>(null);
  const [consensus, setConsensus] = useState<ConsensusConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Start form state
  const [interval, setInterval_] = useState(60);
  const [rounds, setRounds] = useState(3);
  const [maxCycles, setMaxCycles] = useState(0);

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.daemonStatus().catch(() => null),
      api.consensusConfig().catch(() => null),
    ]).then(([d, c]) => {
      setDaemon(d);
      setConsensus(c);
      setLoading(false);
    }).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Auto-refresh every 10s
  useEffect(() => {
    if (error) return;
    const iv = window.setInterval(loadData, 10000);
    return () => window.clearInterval(iv);
  }, [loadData, error]);

  // Auto-clear action messages
  useEffect(() => {
    if (!actionMsg) return;
    const t = setTimeout(() => setActionMsg(null), 5000);
    return () => clearTimeout(t);
  }, [actionMsg]);

  const handleStart = async () => {
    try {
      await api.daemonStart(interval, rounds, maxCycles);
      setActionMsg({ type: "success", text: `Daemon started — ${rounds} rounds every ${interval}min` });
      loadData();
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  const handleStop = async () => {
    try {
      await api.daemonStop();
      setActionMsg({ type: "success", text: "Daemon stopped" });
      loadData();
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  const handleConsensusToggle = async () => {
    if (!consensus) return;
    try {
      const result = await api.setConsensus(!consensus.enabled, consensus.researchers);
      setConsensus(result);
      setActionMsg({ type: "success", text: `Consensus ${result.enabled ? "enabled" : "disabled"}` });
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  const handleResearchersChange = async (n: number) => {
    if (!consensus) return;
    try {
      const result = await api.setConsensus(consensus.enabled, n);
      setConsensus(result);
    } catch (e) { setActionMsg({ type: "error", text: (e as Error).message }); }
  };

  if (loading && !daemon) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <DecryptedText text="Loading scheduler..." className="text-xl text-white/60" speed={40} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="text-4xl opacity-20">⚠️</div>
        <p className="text-[#ff4060]">Failed to load scheduler</p>
        <p className="text-white/30 text-sm font-mono">{error}</p>
        <button onClick={loadData} className="px-4 py-2 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-sm">↻ Retry</button>
        <Link href="/" className="text-white/30 text-xs hover:text-white/50">← Back to Overview</Link>
      </div>
    );
  }

  const isRunning = daemon?.running ?? false;
  const state = daemon?.state;
  const logs = daemon?.recent_log || [];

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Link href="/" className="text-white/25 text-xs hover:text-white/50 transition-colors">← Overview</Link>
          <h1 className="text-2xl font-bold tracking-tight mt-1 flex items-center gap-3">
            <span className="text-2xl">⏱</span>
            <DecryptedText text="Scheduler" speed={30} />
          </h1>
          <p className="text-white/25 text-xs mt-1">Autonomous research daemon — runs the loop on a schedule</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={"text-xs px-3 py-1.5 rounded-full border font-medium " + (
            isRunning
              ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20 animate-pulse"
              : "bg-white/5 text-white/40 border-white/10"
          )}>
            {isRunning ? "● Running" : "○ Stopped"}
          </span>
        </div>
      </div>

      {/* Action toast */}
      {actionMsg && (
        <div className={"px-4 py-3 rounded-xl border text-sm " + (
          actionMsg.type === "success"
            ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
            : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
        )}>
          {actionMsg.type === "success" ? "✓ " : "✗ "}{actionMsg.text}
        </div>
      )}

      {/* Status + Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Daemon Status */}
        <StarBorder color={isRunning ? "#00ff88" : "#00e5ff"}>
          <div className="p-5 space-y-4">
            <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium">Daemon Status</h3>
            {isRunning && state ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] text-white/25 uppercase">Cycles</p>
                    <p className="text-lg font-bold font-mono text-[#00e5ff]">
                      <CountUp to={typeof state.cycles_completed === "number" ? state.cycles_completed : 0} duration={0.5} />
                      {state.max_cycles ? <span className="text-white/20 text-sm">/{String(state.max_cycles)}</span> : null}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-white/25 uppercase">Total Runs</p>
                    <p className="text-lg font-bold font-mono text-[#00ff88]">
                      <CountUp to={typeof state.total_runs === "number" ? state.total_runs : 0} duration={0.5} />
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] text-white/25 uppercase">Interval</p>
                    <p className="text-sm font-mono text-white/60">{String(state.interval_minutes ?? "?")}min</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-white/25 uppercase">Rounds/Cycle</p>
                    <p className="text-sm font-mono text-white/60">{String(state.rounds_per_cycle ?? "?")}</p>
                  </div>
                </div>
                {typeof state.started_at === "string" && (
                  <p className="text-[10px] text-white/15 font-mono">
                    Started: {new Date(state.started_at).toLocaleString()}
                  </p>
                )}
                <button
                  onClick={handleStop}
                  className="w-full px-4 py-2.5 bg-[#ff4060]/10 text-[#ff4060] border border-[#ff4060]/30 rounded-xl text-sm font-medium hover:bg-[#ff4060]/20 transition-all"
                >
                  ⏹ Stop Daemon
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-white/30 text-sm">Daemon is not running. Configure and start below.</p>
                <div className="space-y-3">
                  <div>
                    <label className="text-[10px] text-white/25 uppercase tracking-wider block mb-1">Interval (minutes)</label>
                    <input
                      type="number"
                      value={interval}
                      onChange={(e) => setInterval_(Math.max(1, parseInt(e.target.value) || 1))}
                      className="w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70 font-mono focus:outline-none focus:border-[#00e5ff]/40"
                      min={1}
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-white/25 uppercase tracking-wider block mb-1">Rounds per Cycle</label>
                    <input
                      type="number"
                      value={rounds}
                      onChange={(e) => setRounds(Math.max(1, parseInt(e.target.value) || 1))}
                      className="w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70 font-mono focus:outline-none focus:border-[#00e5ff]/40"
                      min={1} max={20}
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-white/25 uppercase tracking-wider block mb-1">Max Cycles (0 = unlimited)</label>
                    <input
                      type="number"
                      value={maxCycles}
                      onChange={(e) => setMaxCycles(Math.max(0, parseInt(e.target.value) || 0))}
                      className="w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70 font-mono focus:outline-none focus:border-[#00e5ff]/40"
                      min={0}
                    />
                  </div>
                </div>
                <button
                  onClick={handleStart}
                  className="w-full px-4 py-2.5 bg-[#00ff88]/10 text-[#00ff88] border border-[#00ff88]/30 rounded-xl text-sm font-medium hover:bg-[#00ff88]/20 transition-all"
                >
                  ▶ Start Daemon
                </button>
              </div>
            )}
          </div>
        </StarBorder>

        {/* Consensus Config */}
        <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.1)">
          <div className="space-y-4">
            <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium">Consensus Mode</h3>
            <p className="text-white/30 text-xs">
              When enabled, runs {consensus?.researchers || 3} independent researchers in parallel and merges their findings for higher accuracy.
            </p>
            <div className="flex items-center justify-between">
              <span className="text-sm text-white/50">Status</span>
              <button
                onClick={handleConsensusToggle}
                className={"px-4 py-1.5 rounded-full border text-xs font-medium transition-all " + (
                  consensus?.enabled
                    ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20 hover:bg-[#00ff88]/20"
                    : "bg-white/5 text-white/40 border-white/10 hover:bg-white/10"
                )}
              >
                {consensus?.enabled ? "● Enabled" : "○ Disabled"}
              </button>
            </div>
            <div>
              <label className="text-[10px] text-white/25 uppercase tracking-wider block mb-1">Researchers</label>
              <div className="flex gap-2">
                {[2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => handleResearchersChange(n)}
                    className={"flex-1 py-2 rounded-lg border text-sm font-mono transition-all " + (
                      consensus?.researchers === n
                        ? "bg-[#7c4dff]/10 text-[#7c4dff] border-[#7c4dff]/30"
                        : "bg-white/[0.02] text-white/30 border-white/[0.06] hover:bg-white/[0.04]"
                    )}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-white/15 mt-1">
                Cost multiplier: ~{consensus?.researchers || 3}x per research run
              </p>
            </div>
          </div>
        </SpotlightCard>
      </div>

      {/* Daemon Log */}
      <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white/50">Recent Activity</h3>
          <span className="text-[10px] text-white/20 font-mono">{logs.length} entries</span>
        </div>
        {logs.length === 0 ? (
          <div className="text-center py-10">
            <div className="text-3xl opacity-10 mb-2">📋</div>
            <p className="text-white/20 text-sm">No activity yet</p>
            <p className="text-white/10 text-xs mt-1">Start the daemon to begin autonomous research</p>
          </div>
        ) : (
          <div className="space-y-1 max-h-[400px] overflow-y-auto">
            {logs.slice().reverse().map((log, i) => {
              const levelColor = log.level === "error" ? "#ff4060" :
                log.level === "warning" ? "#ffb300" :
                log.level === "info" ? "#00e5ff" : "rgba(255,255,255,0.3)";
              return (
                <div key={i} className="flex gap-3 px-3 py-2 bg-white/[0.01] rounded-lg hover:bg-white/[0.03] transition-colors">
                  <span className="text-[10px] text-white/15 font-mono whitespace-nowrap flex-shrink-0">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span
                    className="text-[10px] uppercase font-bold flex-shrink-0 w-12"
                    style={{ color: levelColor }}
                  >
                    {log.level}
                  </span>
                  <span className="text-xs text-white/50 break-all">{log.message}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Safety note */}
      <div className="bg-[#ffb300]/[0.04] border border-[#ffb300]/15 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <span className="text-lg">⚠️</span>
          <div>
            <p className="text-[#ffb300]/70 text-sm font-medium">Human Control</p>
            <p className="text-white/30 text-xs mt-1 leading-relaxed">
              The daemon respects your daily budget limit and will pause if the budget is exhausted.
              Strategy changes generated during daemon runs are saved as &quot;pending&quot; and require your explicit approval.
              Use the stop button or the CLI (<code className="text-white/40">python main.py --daemon-stop</code>) to halt at any time.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
