// API base: use Next.js rewrites proxy (same-origin) to avoid CORS/auth issues.
// Falls back to direct URL only for local dev without Next.js proxy.
function getApiBase(): string {
  if (typeof window !== "undefined") {
    // In browser: use same-origin (Next.js rewrites proxy handles /api/* → FastAPI)
    return "";
  }
  // Server-side: direct connection
  return process.env.API_URL || "http://localhost:8000";
}

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const base = getApiBase();
  const res = await fetch(`${base}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Types ────────────────────────────────────────────────────────────────

export interface SystemHealth {
  health_score: number;
  total_outputs: number;
  total_accepted: number;
  total_rejected: number;
  acceptance_rate: number;
  avg_score: number;
  domain_count: number;
  domains_with_strategy: number;
  domains_with_kb: number;
  domains_in_trial: number;
  domains_with_pending: number;
  principle_count: number;
  budget_remaining: number;
  budget_spent_today: number;
  api_calls_today: number;
}

export interface Domain {
  name: string;
  outputs: number;
  accepted: number;
  rejected: number;
  avg_score: number;
  strategy_version: string;
  strategy_status: string;
  has_kb: boolean;
  kb_claims: number;
}

export interface BudgetInfo {
  today: {
    spent: number;
    limit: number;
    remaining: number;
    within_budget: boolean;
    calls: number;
  };
  alltime: Record<string, number>;
}

export interface ResearchOutput {
  question: string;
  score: number | null;
  verdict: string;
  timestamp: string;
  strategy_version: string;
  searches_made: number;
  findings_count: number;
  key_insights: string[];
  knowledge_gaps: string[];
  critique_scores: Record<string, number>;
}

export interface DomainDetail {
  domain: string;
  stats: Record<string, number>;
  trajectory: {
    domain: string;
    total_outputs: number;
    scores: Array<{ score: number; timestamp: string; strategy: string; accepted: boolean }>;
    rolling_avg: number[];
    trend: string;
    improvement: number;
    first_score: number;
    last_score: number;
    best_score: number;
    worst_score: number;
  };
  distribution: Record<string, number>;
  strategies: Array<Record<string, unknown>>;
  critic: Record<string, unknown>;
  research: Record<string, unknown>;
  velocity: Record<string, unknown>;
}

export interface LoopEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp?: string;
}

// ── API functions ────────────────────────────────────────────────────────

export const api = {
  health: () => fetchApi<SystemHealth>("/api/health"),
  domains: () => fetchApi<Domain[]>("/api/domains"),
  domain: (name: string) => fetchApi<DomainDetail>(`/api/domains/${name}`),
  domainOutputs: (name: string) => fetchApi<ResearchOutput[]>(`/api/domains/${name}/outputs`),
  domainKb: (name: string) => fetchApi<Record<string, unknown>>(`/api/domains/${name}/kb`),
  domainStrategy: (name: string) => fetchApi<Record<string, unknown>>(`/api/domains/${name}/strategy`),
  budget: () => fetchApi<BudgetInfo>("/api/budget"),
  cost: () => fetchApi<Record<string, unknown>>("/api/cost"),
  comparison: () => fetchApi<Array<Record<string, unknown>>>("/api/comparison"),
  validate: () => fetchApi<Record<string, unknown>>("/api/validate"),
  runStatus: () => fetchApi<{ running: boolean }>("/api/run/status"),
};

// ── SSE Stream ───────────────────────────────────────────────────────────

export function startRun(
  question: string,
  domain: string,
  onEvent: (event: LoopEvent) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const base = getApiBase();
  const url = `${base}/api/run?question=${encodeURIComponent(question)}&domain=${encodeURIComponent(domain)}`;
  
  const controller = new AbortController();
  
  fetch(url, { method: "POST", signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text();
        onError(`API error ${res.status}: ${text}`);
        return;
      }
      
      const reader = res.body?.getReader();
      if (!reader) return;
      
      const decoder = new TextDecoder();
      let buffer = "";
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              onEvent(event);
              if (event.type === "run_end") {
                onDone();
                return;
              }
            } catch {
              // Skip malformed events
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError") onError(err.message);
    });
  
  return () => controller.abort();
}

export function startAuto(
  domain: string,
  rounds: number,
  onEvent: (event: LoopEvent) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const base = getApiBase();
  const url = `${base}/api/auto?domain=${encodeURIComponent(domain)}&rounds=${rounds}`;
  
  const controller = new AbortController();
  
  fetch(url, { method: "POST", signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text();
        onError(`API error ${res.status}: ${text}`);
        return;
      }
      
      const reader = res.body?.getReader();
      if (!reader) return;
      
      const decoder = new TextDecoder();
      let buffer = "";
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              onEvent(event);
              if (event.type === "run_end") {
                onDone();
                return;
              }
            } catch {
              // Skip
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError") onError(err.message);
    });
  
  return () => controller.abort();
}
