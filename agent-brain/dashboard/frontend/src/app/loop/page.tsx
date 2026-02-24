"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { startRun, startAuto, LoopEvent, api } from "@/lib/api";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import GlitchText from "@/components/reactbits/GlitchText";
import ShinyText from "@/components/reactbits/ShinyText";
import AnimatedList from "@/components/reactbits/AnimatedList";
import DecryptedText from "@/components/reactbits/DecryptedText";

type RunMode = "single" | "auto";

interface LogEntry {
  id: number;
  type: string;
  message: string;
  timestamp: string;
}

function eventIcon(type: string): string {
  switch (type) {
    case "researcher": return "🔍";
    case "critic": return "⚖️";
    case "quality_gate": return "✓";
    case "strategy": return "📋";
    case "memory": return "💾";
    case "meta_analyst": return "🧠";
    case "synthesizer": return "📚";
    case "budget": return "💰";
    case "run_start": return "▶";
    case "run_complete": return "✅";
    case "run_error": return "❌";
    case "run_end": return "⏹";
    case "auto_round": return "🔄";
    case "question_generated": return "❓";
    case "round_complete": return "🏁";
    default: return "•";
  }
}

function eventColor(type: string): string {
  switch (type) {
    case "researcher": return "text-[#00e5ff]";
    case "critic": return "text-[#ffb300]";
    case "quality_gate": return "text-[#00ff88]";
    case "run_error": return "text-[#ff4060]";
    case "run_complete": return "text-[#00ff88]";
    case "auto_round": return "text-[#7c4dff]";
    default: return "text-white/60";
  }
}

export default function LoopPage() {
  const [mode, setMode] = useState<RunMode>("auto");
  const [domain, setDomain] = useState("general");
  const [question, setQuestion] = useState("");
  const [rounds, setRounds] = useState(3);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>("idle");
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);
  const [domains, setDomains] = useState<string[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const idRef = useRef(0);

  useEffect(() => {
    api.domains().then(ds => setDomains(ds.map(d => d.name))).catch(() => {});
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const addLog = useCallback((type: string, message: string) => {
    setLogs(prev => [...prev, {
      id: idRef.current++,
      type,
      message,
      timestamp: new Date().toISOString(),
    }]);
  }, []);

  const handleEvent = useCallback((event: LoopEvent) => {
    const msg = (event.data?.message as string) || JSON.stringify(event.data);
    addLog(event.type, msg);

    // Update phase
    if (event.type === "researcher") setCurrentPhase("researching");
    else if (event.type === "critic") setCurrentPhase("critiquing");
    else if (event.type === "quality_gate") setCurrentPhase("evaluating");
    else if (event.type === "meta_analyst") setCurrentPhase("evolving");
    else if (event.type === "synthesizer") setCurrentPhase("synthesizing");
    else if (event.type === "run_complete") {
      setCurrentPhase("complete");
      setLastResult(event.data);
    }
    else if (event.type === "run_error") setCurrentPhase("error");
    else if (event.type === "auto_round") setCurrentPhase(`round ${event.data?.round}/${event.data?.total}`);
    else if (event.type === "question_generated") setCurrentPhase("researching");
  }, [addLog]);

  const handleStart = useCallback(() => {
    setRunning(true);
    setLogs([]);
    setLastResult(null);
    setCurrentPhase("starting");

    const onDone = () => {
      setRunning(false);
      setCurrentPhase("complete");
    };
    const onError = (err: string) => {
      addLog("run_error", err);
      setRunning(false);
      setCurrentPhase("error");
    };

    if (mode === "single") {
      if (!question.trim()) {
        addLog("run_error", "Enter a research question");
        setRunning(false);
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

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-3">
            {running ? (
              <GlitchText text="Live Loop" className="text-[#00e5ff]" speed={1.5} />
            ) : (
              <span>Live Loop</span>
            )}
            {running && <span className="w-2.5 h-2.5 rounded-full bg-[#00ff88] pulse-dot" />}
          </h1>
          <p className="text-white/40 text-sm mt-1">Watch the AI brain research, evaluate, and learn in real time</p>
        </div>
        {running && (
          <div className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-white/60">
            Phase: <ShinyText text={currentPhase} speed={2} shineColor="rgba(0,229,255,0.5)" className="text-[#00e5ff]" />
          </div>
        )}
      </div>

      {/* Controls */}
      <SpotlightCard spotlightColor="rgba(0, 229, 255, 0.1)">
        <div className="space-y-4">
          {/* Mode Toggle */}
          <div className="flex gap-2">
            <button
              onClick={() => setMode("single")}
              className={`px-4 py-2 rounded-lg text-sm transition-all ${
                mode === "single" ? "bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30" : "text-white/40 border border-white/10 hover:text-white/60"
              }`}
            >
              Single Question
            </button>
            <button
              onClick={() => setMode("auto")}
              className={`px-4 py-2 rounded-lg text-sm transition-all ${
                mode === "auto" ? "bg-[#7c4dff]/10 text-[#7c4dff] border border-[#7c4dff]/30" : "text-white/40 border border-white/10 hover:text-white/60"
              }`}
            >
              Autonomous Mode
            </button>
          </div>

          <div className="flex gap-3 items-end">
            {/* Domain Select */}
            <div className="flex-shrink-0">
              <label className="block text-[10px] uppercase tracking-wider text-white/30 mb-1.5">Domain</label>
              <select
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={running}
                className="bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:border-[#00e5ff]/30 focus:outline-none disabled:opacity-40"
              >
                {["general", ...domains.filter(d => d !== "general")].map(d => (
                  <option key={d} value={d} className="bg-[#0a0a0f]">{d}</option>
                ))}
              </select>
            </div>

            {mode === "single" ? (
              <div className="flex-1">
                <label className="block text-[10px] uppercase tracking-wider text-white/30 mb-1.5">Question</label>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={running}
                  placeholder="What do you want to research?"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder-white/20 focus:border-[#00e5ff]/30 focus:outline-none disabled:opacity-40"
                />
              </div>
            ) : (
              <div className="flex-shrink-0">
                <label className="block text-[10px] uppercase tracking-wider text-white/30 mb-1.5">Rounds</label>
                <input
                  type="number"
                  value={rounds}
                  onChange={(e) => setRounds(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
                  disabled={running}
                  min={1}
                  max={20}
                  className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:border-[#00e5ff]/30 focus:outline-none disabled:opacity-40"
                />
              </div>
            )}

            {!running ? (
              <button
                onClick={handleStart}
                className="px-6 py-2.5 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-lg text-sm font-medium hover:bg-[#00e5ff]/20 transition-all active:scale-95"
              >
                ▶ Start
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="px-6 py-2.5 bg-[#ff4060]/10 text-[#ff4060] border border-[#ff4060]/30 rounded-lg text-sm font-medium hover:bg-[#ff4060]/20 transition-all active:scale-95"
              >
                ⏹ Stop
              </button>
            )}
          </div>
        </div>
      </SpotlightCard>

      {/* Split view: Log Feed + Result */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Event Log */}
        <div className="lg:col-span-2 bg-white/[0.02] border border-white/5 rounded-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
            <h3 className="text-sm font-medium text-white/60">Event Log</h3>
            <span className="text-[10px] text-white/30 font-mono">{logs.length} events</span>
          </div>
          <div className="h-[500px] overflow-y-auto p-4 font-mono text-xs space-y-1">
            {logs.length === 0 ? (
              <p className="text-white/20 text-center py-20">
                {running ? "Waiting for events..." : "Start a run to see live events"}
              </p>
            ) : (
              logs.map((log) => (
                <div key={log.id} className={`flex gap-2 py-0.5 ${eventColor(log.type)}`}>
                  <span className="flex-shrink-0 w-4 text-center">{eventIcon(log.type)}</span>
                  <span className="text-white/20 flex-shrink-0">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="break-all">{log.message}</span>
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Status Panel */}
        <div className="space-y-4">
          {/* Phase Indicator */}
          <SpotlightCard spotlightColor="rgba(124, 77, 255, 0.12)">
            <h3 className="text-xs uppercase tracking-wider text-white/30 mb-3">Current Phase</h3>
            <div className="text-center py-4">
              {running ? (
                <div className="space-y-2">
                  <div className="text-4xl">
                    {currentPhase === "researching" && "🔍"}
                    {currentPhase === "critiquing" && "⚖️"}
                    {currentPhase === "evaluating" && "✓"}
                    {currentPhase === "evolving" && "🧠"}
                    {currentPhase === "synthesizing" && "📚"}
                    {currentPhase === "starting" && "⟳"}
                    {currentPhase.startsWith("round") && "🔄"}
                  </div>
                  <ShinyText
                    text={currentPhase.toUpperCase()}
                    className="text-sm font-bold"
                    speed={2}
                    shineColor="rgba(0,229,255,0.6)"
                  />
                </div>
              ) : currentPhase === "complete" ? (
                <div className="space-y-2">
                  <div className="text-4xl">✅</div>
                  <p className="text-sm text-[#00ff88]">Complete</p>
                </div>
              ) : currentPhase === "error" ? (
                <div className="space-y-2">
                  <div className="text-4xl">❌</div>
                  <p className="text-sm text-[#ff4060]">Error</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-4xl opacity-20">⏸</div>
                  <p className="text-sm text-white/30">Idle</p>
                </div>
              )}
            </div>
          </SpotlightCard>

          {/* Last Result */}
          {lastResult && (
            <SpotlightCard spotlightColor="rgba(0, 255, 136, 0.12)">
              <h3 className="text-xs uppercase tracking-wider text-white/30 mb-3">Last Result</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-white/40">Score</span>
                  <span className="font-bold" style={{
                    color: (lastResult.score as number) >= 7 ? "#00ff88" : (lastResult.score as number) >= 5 ? "#ffb300" : "#ff4060"
                  }}>
                    {lastResult.score as number}/10
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">Verdict</span>
                  <span className={lastResult.verdict === "accept" ? "text-[#00ff88]" : "text-[#ff4060]"}>
                    {lastResult.verdict as string}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">Strategy</span>
                  <span className="text-white/60 font-mono text-xs">{lastResult.strategy_version as string}</span>
                </div>
              </div>
            </SpotlightCard>
          )}

          {/* Pipeline Visualization */}
          <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-4">
            <h3 className="text-xs uppercase tracking-wider text-white/30 mb-4">Pipeline</h3>
            <div className="space-y-3">
              {[
                { phase: "researching", label: "Researcher", icon: "🔍", desc: "Web search + findings" },
                { phase: "critiquing", label: "Critic", icon: "⚖️", desc: "5-dimension scoring" },
                { phase: "evaluating", label: "Quality Gate", icon: "✓", desc: "Accept / Reject" },
                { phase: "evolving", label: "Meta-Analyst", icon: "🧠", desc: "Strategy rewrite" },
                { phase: "synthesizing", label: "Synthesizer", icon: "📚", desc: "Knowledge base" },
              ].map(({ phase, label, icon, desc }) => {
                const isActive = currentPhase === phase;
                const isPast = logs.some(l => l.type === phase.replace("ing", "").replace("critiqu", "critic").replace("evaluat", "quality_gate").replace("evolv", "meta_analyst").replace("synthesiz", "synthesizer"));
                return (
                  <div key={phase} className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
                    isActive ? "bg-[#00e5ff]/5 border border-[#00e5ff]/20" : "border border-transparent"
                  }`}>
                    <span className={`text-lg ${isActive ? "" : "opacity-30"}`}>{icon}</span>
                    <div className="flex-1">
                      <p className={`text-xs font-medium ${isActive ? "text-[#00e5ff]" : "text-white/40"}`}>{label}</p>
                      <p className="text-[10px] text-white/20">{desc}</p>
                    </div>
                    {isActive && <span className="w-1.5 h-1.5 rounded-full bg-[#00e5ff] pulse-dot" />}
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
