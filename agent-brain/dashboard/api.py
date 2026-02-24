"""
Agent Brain — Dashboard API

FastAPI backend exposing system data and real-time loop monitoring via SSE.
"""

import asyncio
import json
import os
import sys
import threading
import queue
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Add parent to path so we can import agent-brain modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import (
    full_report, score_trajectory, strategy_comparison,
    cost_efficiency, critic_analysis, research_patterns,
    knowledge_velocity, domain_comparison, score_distribution,
)
from agents.orchestrator import discover_domains, get_system_health
from memory_store import load_outputs, get_stats, load_knowledge_base
from strategy_store import (
    get_active_version, get_strategy_status, get_strategy,
    list_versions, get_version_history, load_strategy_file,
)
from cost_tracker import get_daily_spend, get_all_time_spend, check_budget
from validator import validate_all
from agents.question_generator import get_next_question
from config import MEMORY_DIR, QUALITY_THRESHOLD


# ── Global event bus for SSE ──────────────────────────────────────────────

_event_queues: list[queue.Queue] = []
_event_lock = threading.Lock()


def broadcast_event(event_type: str, data: dict):
    """Push an event to all connected SSE clients."""
    event = {"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
    with _event_lock:
        dead = []
        for q in _event_queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _event_queues.remove(q)


# ── App ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="Agent Brain Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health & Overview ─────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    """System health metrics."""
    return get_system_health()


@app.get("/api/overview")
def api_overview():
    """Full analytics report."""
    return full_report()


@app.get("/api/budget")
def api_budget():
    """Budget and cost information."""
    budget = check_budget()
    daily = get_daily_spend()
    alltime = get_all_time_spend()
    return {
        "today": {
            "spent": budget["spent"],
            "limit": budget["limit"],
            "remaining": budget["remaining"],
            "within_budget": budget["within_budget"],
            "calls": daily["calls"],
        },
        "alltime": alltime,
    }


# ── Domains ───────────────────────────────────────────────────────────────

@app.get("/api/domains")
def api_domains():
    """List all domains with summary stats."""
    domains = discover_domains()
    result = []
    for d in domains:
        stats = get_stats(d)
        sv = get_active_version("researcher", d)
        status = get_strategy_status("researcher", d)
        kb = load_knowledge_base(d)
        result.append({
            "name": d,
            "outputs": stats["count"],
            "accepted": stats["accepted"],
            "rejected": stats["rejected"],
            "avg_score": round(stats["avg_score"], 1),
            "strategy_version": sv,
            "strategy_status": status,
            "has_kb": kb is not None,
            "kb_claims": len(kb.get("claims", [])) if kb else 0,
        })
    return result


@app.get("/api/domains/{domain}")
def api_domain_detail(domain: str):
    """Detailed analytics for a single domain."""
    domains = discover_domains()
    if domain not in domains:
        raise HTTPException(404, f"Domain '{domain}' not found")
    
    return {
        "domain": domain,
        "stats": get_stats(domain),
        "trajectory": score_trajectory(domain),
        "distribution": score_distribution(domain),
        "strategies": strategy_comparison(domain),
        "critic": critic_analysis(domain),
        "research": research_patterns(domain),
        "velocity": knowledge_velocity(domain),
    }


@app.get("/api/domains/{domain}/outputs")
def api_domain_outputs(domain: str, limit: int = Query(50, ge=1, le=500)):
    """List research outputs for a domain."""
    outputs = load_outputs(domain)
    # Sort by timestamp descending
    outputs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    results = []
    for o in outputs[:limit]:
        results.append({
            "question": o.get("question", ""),
            "score": o.get("score", o.get("overall_score")),
            "verdict": o.get("verdict", "unknown"),
            "timestamp": o.get("timestamp", ""),
            "strategy_version": o.get("strategy_version", "default"),
            "searches_made": o.get("_searches_made", 0),
            "findings_count": len(o.get("findings", [])),
            "key_insights": o.get("key_insights", []),
            "knowledge_gaps": o.get("knowledge_gaps", []),
            "critique_scores": o.get("critique", {}).get("scores", {}),
        })
    return results


@app.get("/api/domains/{domain}/kb")
def api_domain_kb(domain: str):
    """Knowledge base for a domain."""
    kb = load_knowledge_base(domain)
    if not kb:
        raise HTTPException(404, f"No knowledge base for '{domain}'")
    return kb


# ── Strategies ────────────────────────────────────────────────────────────

@app.get("/api/domains/{domain}/strategy")
def api_domain_strategy(domain: str):
    """Current strategy and version history for a domain."""
    strategy_text, version = get_strategy("researcher", domain)
    status = get_strategy_status("researcher", domain)
    history = get_version_history("researcher", domain)
    versions = list_versions("researcher", domain)
    
    return {
        "domain": domain,
        "active_version": version,
        "status": status,
        "strategy_text": strategy_text,
        "history": history,
        "all_versions": versions,
    }


# ── Cost Efficiency ──────────────────────────────────────────────────────

@app.get("/api/cost")
def api_cost():
    """Cost efficiency breakdown."""
    return cost_efficiency()


# ── Validation ────────────────────────────────────────────────────────────

@app.get("/api/validate")
def api_validate():
    """Run data validation."""
    return validate_all()


# ── Domain Comparison ─────────────────────────────────────────────────────

@app.get("/api/comparison")
def api_comparison():
    """Cross-domain comparison table."""
    return domain_comparison()


# ── Run Loop (with SSE streaming) ─────────────────────────────────────────

_run_lock = threading.Lock()
_is_running = False


def _run_loop_thread(question: str, domain: str, event_q: queue.Queue):
    """Run the research loop in a background thread, pushing events."""
    global _is_running
    
    try:
        from main import run_loop
        
        event_q.put({"type": "run_start", "data": {
            "question": question, "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }})
        
        # Monkey-patch print to capture output
        import builtins
        original_print = builtins.print
        
        def capturing_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            original_print(*args, **kwargs)
            # Parse important events from the print output
            if "[RESEARCHER]" in text:
                event_q.put({"type": "researcher", "data": {"message": text.strip()}})
            elif "[CRITIC]" in text:
                event_q.put({"type": "critic", "data": {"message": text.strip()}})
            elif "[QUALITY GATE]" in text:
                event_q.put({"type": "quality_gate", "data": {"message": text.strip()}})
            elif "[STRATEGY]" in text:
                event_q.put({"type": "strategy", "data": {"message": text.strip()}})
            elif "[MEMORY]" in text:
                event_q.put({"type": "memory", "data": {"message": text.strip()}})
            elif "[META-ANALYST]" in text or "[META_ANALYST]" in text:
                event_q.put({"type": "meta_analyst", "data": {"message": text.strip()}})
            elif "[SYNTHESIZER]" in text:
                event_q.put({"type": "synthesizer", "data": {"message": text.strip()}})
            elif "[BUDGET]" in text:
                event_q.put({"type": "budget", "data": {"message": text.strip()}})
            elif "Attempt" in text or "---" in text:
                event_q.put({"type": "attempt", "data": {"message": text.strip()}})
        
        builtins.print = capturing_print
        
        try:
            result = run_loop(question, domain)
            event_q.put({"type": "run_complete", "data": {
                "question": question,
                "domain": domain,
                "score": result.get("score"),
                "verdict": result.get("verdict"),
                "strategy_version": result.get("strategy_version"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }})
        except SystemExit:
            event_q.put({"type": "run_error", "data": {"error": "Budget exceeded or system exit"}})
        except Exception as e:
            event_q.put({"type": "run_error", "data": {"error": str(e)}})
        finally:
            builtins.print = original_print
    finally:
        _is_running = False
        event_q.put({"type": "run_end", "data": {}})


@app.post("/api/run")
async def api_run(
    question: str = Query(..., description="Research question"),
    domain: str = Query("general", description="Domain"),
):
    """Start a research loop. Returns SSE stream of events."""
    global _is_running
    
    if _is_running:
        raise HTTPException(409, "A run is already in progress")
    
    _is_running = True
    event_q: queue.Queue = queue.Queue(maxsize=500)
    
    thread = threading.Thread(target=_run_loop_thread, args=(question, domain, event_q), daemon=True)
    thread.start()
    
    async def event_stream():
        while True:
            try:
                event = event_q.get(timeout=0.5)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "run_end":
                    break
            except queue.Empty:
                yield f": keepalive\n\n"
                if not thread.is_alive():
                    break
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/run/status")
def api_run_status():
    """Check if a run is currently in progress."""
    return {"running": _is_running}


# ── Auto-mode (SSE) ──────────────────────────────────────────────────────

def _auto_loop_thread(domain: str, rounds: int, event_q: queue.Queue):
    """Run auto mode in a background thread."""
    global _is_running
    
    try:
        import builtins
        original_print = builtins.print
        
        def capturing_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            original_print(*args, **kwargs)
            event_q.put({"type": "log", "data": {"message": text.strip()}})
            if "[RESEARCHER]" in text:
                event_q.put({"type": "researcher", "data": {"message": text.strip()}})
            elif "[CRITIC]" in text:
                event_q.put({"type": "critic", "data": {"message": text.strip()}})
            elif "[QUALITY GATE]" in text:
                event_q.put({"type": "quality_gate", "data": {"message": text.strip()}})
        
        builtins.print = capturing_print
        
        try:
            from main import run_loop
            from agents.question_generator import get_next_question
            
            for round_num in range(1, rounds + 1):
                event_q.put({"type": "auto_round", "data": {
                    "round": round_num, "total": rounds, "domain": domain,
                }})
                
                # Generate question
                event_q.put({"type": "generating_question", "data": {"round": round_num}})
                question_data = get_next_question(domain)
                if not question_data or not question_data.get("questions"):
                    event_q.put({"type": "run_error", "data": {
                        "error": "Failed to generate question",
                    }})
                    break
                
                question = question_data["questions"][0].get("question", "")
                event_q.put({"type": "question_generated", "data": {
                    "question": question, "round": round_num,
                }})
                
                # Run research loop
                result = run_loop(question, domain)
                
                event_q.put({"type": "round_complete", "data": {
                    "round": round_num,
                    "question": question,
                    "score": result.get("score"),
                    "verdict": result.get("verdict"),
                }})
                
        except SystemExit:
            event_q.put({"type": "run_error", "data": {"error": "Budget exceeded"}})
        except Exception as e:
            event_q.put({"type": "run_error", "data": {"error": str(e)}})
        finally:
            builtins.print = original_print
    finally:
        _is_running = False
        event_q.put({"type": "run_end", "data": {}})


@app.post("/api/auto")
async def api_auto(
    domain: str = Query("general", description="Domain"),
    rounds: int = Query(1, ge=1, le=20, description="Number of rounds"),
):
    """Start autonomous research mode. Returns SSE stream."""
    global _is_running
    
    if _is_running:
        raise HTTPException(409, "A run is already in progress")
    
    _is_running = True
    event_q: queue.Queue = queue.Queue(maxsize=1000)
    
    thread = threading.Thread(target=_auto_loop_thread, args=(domain, rounds, event_q), daemon=True)
    thread.start()
    
    async def event_stream():
        while True:
            try:
                event = event_q.get(timeout=0.5)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "run_end":
                    break
            except queue.Empty:
                yield f": keepalive\n\n"
                if not thread.is_alive():
                    break
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
