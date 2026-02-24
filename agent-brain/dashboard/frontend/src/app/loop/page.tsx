"use client";

import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { startRun, startAuto, LoopEvent, api, Domain } from "@/lib/api";
import GlitchText from "@/components/reactbits/GlitchText";
import ShinyText from "@/components/reactbits/ShinyText";

type RunMode = "single" | "auto";
type Phase = "idle" | "starting" | "researching" | "critiquing" | "evaluating" | "evolving" | "synthesizing" | "complete" | "error" | "stopped" | string;

interface LogEntry {
  id: number;
  type: string;
  message: string;
  timestamp: string;
  raw?: Record<string, unknown>;
}

// ── Helpers ──────────────────────────────────────────────────────────────

const PHASE_META: Record<string, { icon: string; label: string; color: string }> = {
  idle:         { icon: "⏸", label: "Idle",         color: "rgba(255,255,255,0.3)" },
  starting:     { icon: "⟳", label: "Starting",     color: "#00e5ff" },
  researching:  { icon: "🔍", label: "Researching",  color: "#00e5ff" },
  critiquing:   { icon: "⚖️", label: "Critiquing",   color: "#ffb300" },
  evaluating:   { icon: "✓", label: "Evaluating",   color: "#7c4dff" },
  evolving:     { icon: "🧠", label: "Evolving",     color: "#ff6ec7" },
  synthesizing: { icon: "📚", label: "Synthesizing", color: "#00ff88" },
  complete:     { icon: "✅", label: "Complete",     color: "#00ff88" },
  error:        { icon: "❌", label: "Error",        color: "#ff4060" },
  stopped:      { icon: "⏹", label: "Stopped",      color: "#ffb300" },
};

function getEventDisplay(type: string, data: Record<string, unknown>): { icon: string; color: string; text: string } {
  const msg = (data?.message as string) || "";

  switch (type) {
    case "run_start":
      return { icon: "▶", color: "#00e5ff", text: `Starting research: "${data.question}" in ${data.domain}` };
    case "researcher":
      if (msg.includes("Generating")) return { icon: "🔍", color: "#00e5ff", text: "Researcher generating findings..." };
      if (msg.includes("Produced")) return { icon: "📄", color: "#00e5ff", text: msg.replace(/\[RESEARCHER\]\s*/, "") };
      if (msg.includes("searches returned 0")) return { icon: "⚠️", color: "#ffb300", text: msg.replace(/\[RESEARCHER\]\s*/, "") };
      return { icon: "🔍", color: "#00e5ff", text: msg.replace(/\[RESEARCHER\]\s*/, "") };
    case "critic":
      if (msg.includes("Evaluating")) return { icon: "⚖️", color: "#ffb300", text: "Critic evaluating findings..." };
      if (msg.includes("Score:")) {
        const scoreMatch = msg.match(/Score:\s*([\d.]+)/);
        const verdictMatch = msg.match(/Verdict:\s*(\w+)/);
        const score = scoreMatch ? scoreMatch[1] : "?";
        const verdict = verdictMatch ? verdictMatch[1] : "?";
        return { icon: verdict === "accept" ? "✅" : "❌", color: verdict === "accept" ? "#00ff88" : "#ff4060", text: `Score: ${score}/10 — ${verdict}` };
      }
      return { icon: "⚖️", color: "#ffb300", text: msg.replace(/\[CRITIC\]\s*/, "") };
    case "quality_gate":
      if (msg.includes("ACCEPTED")) return { icon: "✅", color: "#00ff88", text: msg.replace(/\[QUALITY GATE\]\s*/, "") };
      if (msg.includes("REJECTED")) return { icon: "🚫", color: "#ff4060", text: msg.replace(/\[QUALITY GATE\]\s*/, "") };
      return { icon: "✓", color: "#7c4dff", text: msg.replace(/\[QUALITY GATE\]\s*/, "") };
    case "strategy":
      return { icon: "📋", color: "#7c4dff", text: msg.replace(/\[STRATEGY\]\s*/, "") };
    case "memory":
      return { icon: "💾", color: "#00e5ff", text: msg.includes("Stored to:") ? "Output saved to memory" : msg.replace(/\[MEMORY\]\s*/, "") };
    case "meta_analyst":
      return { icon: "🧠", color: "#ff6ec7", text: msg.replace(/\[META-ANALYST\]\s*|\[META_ANALYST\]\s*/, "") };
    case "synthesizer":
      return { icon: "📚", color: "#00ff88", text: msg.replace(/\[SYNTHESIZER\]\s*/, "") };
    case "budget":
      return { icon: "💰", color: "#ffb300", text: msg.replace(/\[BUDGET\]\s*/, "") };
    case "attempt":
      if (msg.includes("---")) return { icon: "↻", color: "rgba(255,255,255,0.25)", text: msg.replace(/---\s*/g, "").trim() };
      return { icon: "↻", color: "rgba(255,255,255,0.25)", text: msg };
    case "run_complete":
      return { icon: "🏆", color: "#00ff88", text: `Complete — Score: ${data.score}/10, Verdict: ${data.verdict}` };
    case "run_error":
      return { icon: "❌", color: "#ff4060", text: `Error: ${data.error || data.message || "Unknown error"}` };
    case "run_end":
      return { icon: "⏹", color: "rgba(255,255,255,0.2)", text: "Run finished" };
    case "auto_round":
      return { icon: "🔄", color: "#7c4dff", text: `Round ${data.round}/${data.total}` };
    case "question_generated":
      return { icon: "❓", color: "#00e5ff", text: `Generated: "${data.question}"` };
    case "generating_question":
      return { icon: "💭", color: "#7c4dff", text: `Generating question for round ${data.round}...` };
    case "round_complete":
      return { icon: "🏁", color: "#00ff88", text: `Round ${data.round} — Score: ${data.score}/10, ${data.verdict}` };
    case "log":
      return { icon: "•", color: "rgba(255,255,255,0.2)", text: msg };
    default:
      return { icon: "•", color: "rgba(255,255,255,0.25)", text: msg || JSON.stringify(data) };
  }
}

const PIPELINE_STAGES = [
  { key: "researching",  label: "Researcher",    icon: "🔍", desc: "Web search + structured findings", eventType: "researcher" },
  { key: "critiquing",   label: "Critic",         icon: "⚖️", desc: "5-dimension quality scoring",      eventType: "critic" },
  { key: "evaluating",   label: "Quality Gate",   icon: "✓",  desc: "Accept ≥ 6 / Reject < 6",        eventType: "quality_gate" },
  { key: "evolving",     label: "Meta-Analyst",   icon: "🧠", desc: "Strategy evolution",              eventType: "meta_analyst" },
  { key: "synthesizing", label: "Synthesizer",    icon: "📚", desc: "Knowledge base update",           eventType: "synthesizer" },
];

// ── Component ────────────────────────────────────────────────────────────

export default function LoopPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-[60vh] text-white/30">Loading...</div>}>
      <LoopPageInner />
    </Suspense>
  );
}

function LoopPageInner() {
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<RunMode>("single");
  const [domain, setDomain] = useState(searchParams.get("domain") || "general");
  const [question, setQuestion] = useState("");
  const [rounds, setRounds] = useState(3);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentPhase, setCurrentPhase] = useState<Phase>("idle");
  const [lastResult, setLastResult] = useState<{ score: number; verdict: string; strategy: string; question: string } | null>(null);
  const [completedPipeline, setCompletedPipeline] = useState<Set<string>>(new Set());
  const [domains, setDomains] = useState<Domain[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const idRef = useRef(0);

  useEffect(() => {
    api.domains().then(setDomains).catch(() => {});
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const addLog = useCallback((type: string, message: string, raw?: Record<string, unknown>) => {
    setLogs(prev => [...prev, {
      id: idRef.current++,
      type,
      message,
      timestamp: new Date().toISOString(),
      raw,
    }]);
  }, []);

  const handleEvent = useCallback((event: LoopEvent) => {
    const data = event.data || {};
    const display = getEventDisplay(event.type, data);
    addLog(event.type, display.text, data);

    // Track pipeline progress
    const stageKey = PIPELINE_STAGES.find(s => s.eventType === event.type)?.key;
    if (stageKey) {
      setCompletedPipeline(prev => new Set([...prev, stageKey]));
    }

    // Update current phase
    switch (event.type) {
      case "researcher":   setCurrentPhase("researching"); break;
      case "critic":       setCurrentPhase("critiquing"); break;
      case "quality_gate": setCurrentPhase("evaluating"); break;
      case "meta_analyst": setCurrentPhase("evolving"); break;
      case "synthesizer":  setCurrentPhase("synthesizing"); break;
      case "run_complete":
        setCurrentPhase("complete");
        if (data.score != null) {
          setLastResult({
            score: data.score as number,
            verdict: data.verdict as string,
            strategy: (data.strategy_version as string) || "default",
            question: (data.question as string) || question,
          });
        }
        break;
      case "round_complete":
        if (data.score != null) {
          setLastResult({
            score: data.score as number,
            verdict: data.verdict as string,
            strategy: "auto",
            question: (data.question as string) || "",
          });
        }
        setCompletedPipeline(new Set());
        break;
      case "run_error": setCurrentPhase("error"); break;
      case "auto_round":
        setCurrentPhase("Round " + data.round + "/" + data.total);
        setCompletedPipeline(new Set());
        break;
      case "question_generated": setCurrentPhase("researching"); break;
    }
  }, [addLog, question]);

  const handleStart = useCallback(() => {
    setRunning(true);
    setLogs([]);
    setLastResult(null);
    setCurrentPhase("starting");
    setCompletedPipeline(new Set());

    const onDone = () => {
      setRunning(false);
    };
    const onError = (err: string) => {
      addLog("run_error", "Error: " + err);
      setRunning(false);
      setCurrentPhase("error");
    };

    if (mode === "single") {
      if (!question.trim()) {
        addLog("run_error", "Enter a research question first");
        setRunning(false);
        setCurrentPhase("idle");
        return;
      }
      cancelRef.current = startRun(question, domain, handleEvent, onDone, onError);
    } else {
      cancelRef.current = startAuto(domain, rounds, handleEvent, onDone, onError);
    }
  }, [mode, domain, question, rounds, handleEvent, addLog]);

  const handleStop = useCallback(() => {
    cancelRef.current?.();
    setRunning(false);
    setCurrentPhase("stopped");
    addLog("run_end", "Stopped by user");
  }, [addLog]);

  const phaseMeta = PHASE_META[currentPhase] || { icon: "🔄", label: currentPhase, color: "#7c4dff" };

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-3">
            {running ? (
              <GlitchText text="Live Loop" className="text-[#00e5ff]" speed={1.5} />
            ) : (
              <span className="text-white/90">Live Loop</span>
            )}
            {running && <span className="w-2.5 h-2.5 rounded-full bg-[#00ff88] pulse-dot" />}
          </h1>
          <p className="text-white/30 text-sm mt-1">Watch the AI brain research, evaluate, and learn in real time</p>
        </div>
        {running && (
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10">
            <span className="text-lg">{phaseMeta.icon}</span>
            <ShinyText text={phaseMeta.label.toUpperCase()} speed={2} shineColor={phaseMeta.color + "80"} className="text-sm font-bold tracking-wider" />
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5">
        {/* Mode Toggle */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode("single")}
            disabled={running}
            className={"px-5 py-2.5 rounded-xl text-sm font-medium transition-all " + (
              mode === "single"
                ? "bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 shadow-[0_0_20px_rgba(0,229,255,0.1)]"
                : "text-white/40 border border-white/10 hover:text-white/60 hover:border-white/20"
            )}
          >
            🔍 Single Question
          </button>
          <button
            onClick={() => setMode("auto")}
            disabled={running}
            className={"px-5 py-2.5 rounded-xl text-sm font-medium transition-all " + (
              mode === "auto"
                ? "bg-[#7c4dff]/10 text-[#7c4dff] border border-[#7c4dff]/30 shadow-[0_0_20px_rgba(124,77,255,0.1)]"
                : "text-white/40 border border-white/10 hover:text-white/60 hover:border-white/20"
            )}
          >
            🤖 Autonomous Mode
          </button>
        </div>

        <div className="flex gap-3 items-end flex-wrap">
          {/* Domain */}
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-white/30 mb-1.5 font-medium">Domain</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              disabled={running}
              className="bg-white/[0.04] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white/80 focus:border-[#00e5ff]/40 focus:outline-none disabled:opacity-40 min-w-[140px] cursor-pointer"
            >
              <option value="general" className="bg-[#0a0a0f]">general</option>
              {domains.filter(d => d.name !== "general").map(d => (
                <option key={d.name} value={d.name} className="bg-[#0a0a0f]">{d.name}</option>
              ))}
            </select>
          </div>

          {mode === "single" ? (
            <div className="flex-1 min-w-[200px]">
              <label className="block text-[10px] uppercase tracking-widest text-white/30 mb-1.5 font-medium">Question</label>
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !running) handleStart(); }}
                disabled={running}
                placeholder="What do you want to research?"
                className="w-full bg-white/[0.04] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white/80 placeholder-white/15 focus:border-[#00e5ff]/40 focus:outline-none disabled:opacity-40"
              />
            </div>
          ) : (
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-white/30 mb-1.5 font-medium">Rounds</label>
              <input
                type="number"
                value={rounds}
                onChange={(e) => setRounds(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
                disabled={running}
                min={1}
                max={20}
                className="w-24 bg-white/[0.04] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white/80 focus:border-[#00e5ff]/40 focus:outline-none disabled:opacity-40"
              />
            </div>
          )}

          {!running ? (
            <button
              onClick={handleStart}
              className="px-8 py-2.5 bg-gradient-to-r from-[#00e5ff]/20 to-[#7c4dff]/20 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-sm font-bold hover:from-[#00e5ff]/30 hover:to-[#7c4dff]/30 transition-all active:scale-95 shadow-[0_0_30px_rgba(0,229,255,0.1)]"
            >
              ▶ Start
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="px-8 py-2.5 bg-[#ff4060]/10 text-[#ff4060] border border-[#ff4060]/30 rounded-xl text-sm font-bold hover:bg-[#ff4060]/20 transition-all active:scale-95"
            >
              ⏹ Stop
            </button>
          )}
        </div>
      </div>

      {/* Split: Event Log + Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Event Log */}
        <div className="lg:col-span-2 bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col">
          <div className="px-5 py-3 border-b border-white/[0.06] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/50">Event Log</h3>
            <div className="flex items-center gap-3">
              {running && <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] pulse-dot" />}
              <span className="text-[10px] text-white/25 font-mono">{logs.length} events</span>
            </div>
          </div>
          <div className="flex-1 min-h-[400px] max-h-[600px] overflow-y-auto p-3 space-y-0.5">
            {logs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full py-20 gap-3">
                <span className="text-4xl opacity-10">🔍</span>
                <p className="text-white/15 text-sm">
                  {running ? "Waiting for events..." : "Start a run to see live events"}
                </p>
              </div>
            ) : (
              logs.map((log) => {
                const display = getEventDisplay(log.type, log.raw || {});
                return (
                  <div
                    key={log.id}
                    className={"flex items-start gap-2 px-3 py-1.5 rounded-lg transition-colors hover:bg-white/[0.02] " + (
                      log.type === "run_complete" || log.type === "round_complete"
                        ? "bg-[#00ff88]/[0.03] border border-[#00ff88]/10"
                        : log.type === "run_error"
                        ? "bg-[#ff4060]/[0.03] border border-[#ff4060]/10"
                        : "border border-transparent"
                    )}
                  >
                    <span className="flex-shrink-0 w-5 text-center text-sm leading-6">{display.icon}</span>
                    <span className="flex-shrink-0 text-[10px] text-white/15 font-mono leading-6 w-[68px]">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                    <span
                      className="text-xs leading-6 break-words min-w-0"
                      style={{ color: display.color }}
                    >
                      {display.text}
                    </span>
                  </div>
                );
              })
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Right Sidebar */}
        <div className="space-y-4">
          {/* Phase Indicator */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5">
            <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-4 font-medium">Current Phase</h3>
            <div className="text-center py-3">
              <div className="text-5xl mb-3">{phaseMeta.icon}</div>
              <p className="text-sm font-bold tracking-wider" style={{ color: phaseMeta.color }}>{phaseMeta.label}</p>
            </div>
          </div>

          {/* Last Result */}
          {lastResult && (
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5 space-y-3">
              <h3 className="text-[10px] uppercase tracking-widest text-white/25 font-medium">Last Result</h3>
              <div className="text-center py-2">
                <span
                  className="text-5xl font-black"
                  style={{
                    color: lastResult.score >= 7 ? "#00ff88" : lastResult.score >= 5 ? "#ffb300" : "#ff4060"
                  }}
                >
                  {lastResult.score}
                </span>
                <span className="text-white/20 text-lg">/10</span>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-white/30">Verdict</span>
                  <span className={"px-3 py-1 rounded-full text-xs font-bold border " + (
                    lastResult.verdict === "accept"
                      ? "bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20"
                      : "bg-[#ff4060]/10 text-[#ff4060] border-[#ff4060]/20"
                  )}>
                    {lastResult.verdict === "accept" ? "✓ Accepted" : "✗ Rejected"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-white/30">Strategy</span>
                  <span className="text-white/50 font-mono text-xs">{lastResult.strategy}</span>
                </div>
              </div>

              <div className="h-2 bg-white/[0.04] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-1000"
                  style={{
                    width: (lastResult.score / 10) * 100 + "%",
                    backgroundColor: lastResult.score >= 7 ? "#00ff88" : lastResult.score >= 5 ? "#ffb300" : "#ff4060",
                  }}
                />
              </div>
            </div>
          )}

          {/* Pipeline */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5">
            <h3 className="text-[10px] uppercase tracking-widest text-white/25 mb-4 font-medium">Pipeline</h3>
            <div className="space-y-1">
              {PIPELINE_STAGES.map(({ key, label, icon, desc }, idx) => {
                const isActive = currentPhase === key;
                const isCompleted = completedPipeline.has(key);
                return (
                  <div key={key}>
                    <div className={"flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all " + (
                      isActive
                        ? "bg-[#00e5ff]/[0.06] border border-[#00e5ff]/20"
                        : isCompleted
                        ? "bg-[#00ff88]/[0.03] border border-[#00ff88]/10"
                        : "border border-transparent"
                    )}>
                      <span className={"text-lg transition-opacity " + (isActive || isCompleted ? "opacity-100" : "opacity-20")}>
                        {isCompleted && !isActive ? "✅" : icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className={"text-xs font-medium transition-colors " + (
                          isActive ? "text-[#00e5ff]" : isCompleted ? "text-[#00ff88]/70" : "text-white/30"
                        )}>
                          {label}
                        </p>
                        <p className="text-[10px] text-white/15 truncate">{desc}</p>
                      </div>
                      {isActive && <span className="w-2 h-2 rounded-full bg-[#00e5ff] pulse-dot flex-shrink-0" />}
                      {isCompleted && !isActive && (
                        <span className="text-[10px] text-[#00ff88]/50 flex-shrink-0">done</span>
                      )}
                    </div>
                    {idx < PIPELINE_STAGES.length - 1 && (
                      <div className="flex justify-center">
                        <div className={"w-px h-2 transition-colors " + (
                          isCompleted ? "bg-[#00ff88]/20" : "bg-white/[0.04]"
                        )} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
