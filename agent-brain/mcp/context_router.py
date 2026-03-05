"""
Context Router — Intelligent tool filtering for context efficiency.

Problem: MCP servers can expose dozens or hundreds of tools. Stuffing all of
them into Claude's context window wastes tokens and confuses the model.

Solution: The context router selects only the tools relevant to the current
task/question, based on:
  1. Category matching (task about "files" → filesystem tools)
  2. Keyword matching (task mentions "github" → github tools)
  3. Tool description similarity (semantic matching via RAG if available)
  4. Usage history (tools that succeeded on similar tasks before)
  5. Hard limit (max N tools regardless, to cap context usage)

The router produces a *tool budget* — a filtered subset of available tools
that gets merged with the agent's native tools before each Claude call.
"""

import logging
import re
from typing import Any

logger = logging.getLogger("mcp.context_router")

# Maximum MCP tools to surface in a single Claude call
DEFAULT_MAX_MCP_TOOLS = 15

# Keyword → category mappings for automatic routing
KEYWORD_CATEGORIES: dict[str, list[str]] = {
    # File system
    r"\b(file|read|write|directory|folder|path|create file|delete file)\b": ["filesystem"],
    # Git/GitHub
    r"\b(git|github|commit|branch|pull request|issue|repo|repository)\b": ["git", "github"],
    # Database
    r"\b(database|sql|query|table|postgres|mysql|sqlite|mongo)\b": ["database"],
    # Web/API
    r"\b(http|api|rest|graphql|endpoint|url|fetch|request)\b": ["web", "api"],
    # Docker/containers
    r"\b(docker|container|image|kubernetes|k8s|pod)\b": ["docker", "container"],
    # Search
    r"\b(search|find|grep|locate|look for)\b": ["search"],
    # Code analysis
    r"\b(lint|format|analyze|ast|syntax|parse|refactor)\b": ["code-analysis"],
    # Testing
    r"\b(test|assert|mock|fixture|pytest|jest|coverage)\b": ["testing"],
    # Build/deploy
    r"\b(build|compile|deploy|ci|cd|pipeline|npm|pip|cargo)\b": ["build", "deploy"],
    # Documentation
    r"\b(docs|documentation|readme|changelog|markdown)\b": ["documentation"],
    # Validation / reality check
    r"\b(validate|reality.?check|idea.?check|already.?exists|competition|competitors|"
    r"saturated|market.?research|pre.?build|existing.?solutions)\b": ["validation", "research"],
    # Payments / billing
    r"\b(stripe|payment|billing|subscription|checkout|invoice|price|charge|refund)\b": ["payments", "billing", "stripe"],
    # Supabase / auth / storage
    r"\b(supabase|auth|signup|login|session|storage|bucket|edge.?function|rls|row.?level)\b": ["database", "auth", "storage", "supabase"],
    # Messaging / Slack
    r"\b(slack|channel|message|notification|webhook|bot.?message)\b": ["messaging", "slack", "communication"],
    # Hosting / Vercel
    r"\b(vercel|deploy|hosting|domain|preview|production.?deploy|environment.?var)\b": ["deploy", "hosting", "vercel"],
}


class ContextRouter:
    """
    Routes tasks to relevant MCP tools based on context analysis.

    Usage:
        router = ContextRouter(gateway)
        relevant_tools = router.select_tools(
            task="Read the package.json and check for outdated deps",
            max_tools=10,
        )
        # Returns only filesystem + npm-related tools
    """

    def __init__(self, gateway: Any = None):
        """
        Initialize with a reference to the MCP gateway.

        Args:
            gateway: McpGateway instance (or None for lazy init)
        """
        self._gateway = gateway
        self._usage_history: list[dict] = []  # Track which tools succeeded
        self._max_history = 200

    @property
    def gateway(self):
        if self._gateway is None:
            from mcp.gateway import get_gateway
            self._gateway = get_gateway()
        return self._gateway

    def select_tools(
        self,
        task: str,
        domain: str = "",
        max_tools: int = DEFAULT_MAX_MCP_TOOLS,
        required_categories: list[str] | None = None,
        excluded_categories: list[str] | None = None,
    ) -> list[dict]:
        """
        Select the most relevant MCP tools for a given task.

        Args:
            task: The task description or question
            domain: The current domain (e.g., "nextjs-react")
            max_tools: Maximum number of MCP tools to return
            required_categories: Force-include these categories
            excluded_categories: Force-exclude these categories

        Returns:
            List of tool definitions (Claude tool_use format), filtered
            and ranked by relevance. Highest relevance first.
        """
        all_tools = self.gateway.get_all_tools()
        if not all_tools:
            return []

        # Score each tool
        scored: list[tuple[dict, float]] = []
        for tool in all_tools:
            score = self._score_tool(tool, task, domain, required_categories, excluded_categories)
            if score > 0:
                scored.append((tool, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        # Apply max_tools limit
        selected = [tool for tool, _ in scored[:max_tools]]

        logger.debug(
            f"Context router selected {len(selected)}/{len(all_tools)} tools "
            f"for task: {task[:80]}..."
        )

        return selected

    def record_usage(
        self,
        tool_name: str,
        task: str,
        success: bool,
        domain: str = "",
    ) -> None:
        """Record that a tool was used for a task (for history-based routing)."""
        self._usage_history.append({
            "tool": tool_name,
            "task_keywords": self._extract_keywords(task),
            "success": success,
            "domain": domain,
        })
        # Keep history bounded
        if len(self._usage_history) > self._max_history:
            self._usage_history = self._usage_history[-self._max_history:]

    def get_categories_for_task(self, task: str) -> set[str]:
        """
        Analyze a task description and return matching tool categories.
        Uses keyword pattern matching.
        """
        task_lower = task.lower()
        matched = set()

        for pattern, categories in KEYWORD_CATEGORIES.items():
            if re.search(pattern, task_lower):
                matched.update(categories)

        return matched

    # -------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------

    def _score_tool(
        self,
        tool: dict,
        task: str,
        domain: str,
        required_categories: list[str] | None,
        excluded_categories: list[str] | None,
    ) -> float:
        """
        Score a tool's relevance to a task. Higher = more relevant.

        Scoring components:
          - Category match:    0.4 (tool's server category matches task)
          - Keyword match:     0.3 (tool name/description matches task words)
          - History match:     0.2 (tool succeeded on similar tasks before)
          - Always-include:    0.1 (base score for required categories)

        Returns 0.0 if the tool should be excluded.
        """
        # Extract server name from prefixed tool name
        server_name = tool["name"].split("__")[0] if "__" in tool["name"] else ""

        # Check exclusions first
        if excluded_categories:
            tool_categories = self._get_tool_categories(server_name)
            if tool_categories & set(excluded_categories):
                return 0.0

        score = 0.0

        # 1. Category matching (0.4)
        task_categories = self.get_categories_for_task(task)
        if required_categories:
            task_categories.update(required_categories)

        tool_categories = self._get_tool_categories(server_name)
        if task_categories and tool_categories:
            overlap = task_categories & tool_categories
            if overlap:
                score += 0.4 * (len(overlap) / len(task_categories))

        # If required_categories were specified and matched, give a base boost
        if required_categories:
            if tool_categories & set(required_categories):
                score += 0.1

        # 2. Keyword matching (0.3)
        score += 0.3 * self._keyword_score(tool, task)

        # 3. History matching (0.2)
        score += 0.2 * self._history_score(tool["name"], task, domain)

        return score

    def _keyword_score(self, tool: dict, task: str) -> float:
        """
        Score based on keyword overlap between tool and task.

        Checks tool name, description, and parameter names against
        the task text. Returns 0.0 to 1.0.
        """
        task_words = set(self._extract_keywords(task))
        if not task_words:
            return 0.0

        tool_words = set()

        # Tool name (split on __ and _)
        raw_name = tool.get("name", "")
        for part in re.split(r"[_]{1,2}", raw_name):
            if len(part) > 2:
                tool_words.add(part.lower())

        # Description words
        desc = tool.get("description", "")
        tool_words.update(self._extract_keywords(desc))

        # Parameter names
        schema = tool.get("input_schema", {})
        for prop_name in schema.get("properties", {}).keys():
            for part in prop_name.split("_"):
                if len(part) > 2:
                    tool_words.add(part.lower())

        if not tool_words:
            return 0.0

        overlap = task_words & tool_words
        if not overlap:
            return 0.0

        # Jaccard-ish score — weight more toward task coverage
        return len(overlap) / len(task_words)

    def _history_score(self, tool_name: str, task: str, domain: str) -> float:
        """
        Score based on historical success of this tool on similar tasks.

        Returns 0.0 to 1.0.
        """
        if not self._usage_history:
            return 0.0

        task_keywords = set(self._extract_keywords(task))
        if not task_keywords:
            return 0.0

        # Find history entries for this tool
        relevant = [
            h for h in self._usage_history
            if h["tool"] == tool_name and h["success"]
        ]
        if not relevant:
            return 0.0

        # Score based on keyword overlap with successful past tasks
        best_overlap = 0.0
        for entry in relevant[-20:]:  # Only check last 20
            past_keywords = set(entry.get("task_keywords", []))
            if past_keywords:
                overlap = len(task_keywords & past_keywords) / len(task_keywords)
                best_overlap = max(best_overlap, overlap)

        return best_overlap

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _get_tool_categories(self, server_name: str) -> set[str]:
        """Get categories for a server from the gateway."""
        if not server_name:
            return set()
        container = self.gateway._containers.get(server_name)
        if container:
            return set(container.config.categories)
        return set()

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text."""
        # Remove common stop words and extract words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how",
            "all", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so",
            "than", "too", "very", "just", "about", "and", "but", "or",
            "if", "while", "that", "this", "what", "which", "who",
        }

        words = re.findall(r"[a-z]{2,}", text.lower())
        return [w for w in words if w not in stop_words and len(w) > 2]

    def get_routing_stats(self) -> dict:
        """Get statistics about routing decisions."""
        tool_counts: dict[str, int] = {}
        tool_successes: dict[str, int] = {}

        for entry in self._usage_history:
            tool = entry["tool"]
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            if entry["success"]:
                tool_successes[tool] = tool_successes.get(tool, 0) + 1

        return {
            "total_routings": len(self._usage_history),
            "unique_tools_used": len(tool_counts),
            "tool_usage": tool_counts,
            "tool_success_rates": {
                tool: tool_successes.get(tool, 0) / count
                for tool, count in tool_counts.items()
            },
        }
