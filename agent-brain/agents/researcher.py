"""
Researcher Agent
Takes a question + strategy → uses web search tool → produces structured findings.
Uses Claude tool_use to call web_search during reasoning.
"""

import json
import re
import sys
import os
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from tools.web_search import web_search, SEARCH_TOOL_DEFINITION


client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _build_default_strategy() -> str:
    today = date.today().isoformat()  # e.g. "2026-02-23"
    return f"""\
You are a research agent with web search capability.

TODAY'S DATE: {today}
Any source, event, or data dated AFTER {today} is FUTURE and cannot be verified.
Only report information dated on or before {today} as factual. If a search result references
a future date, flag it explicitly as unverified/projected and set confidence to "low".

WORKFLOW:
1. Use web_search 2-4 times to gather current information. Be targeted — don't over-search.
2. After searching, compile your findings.
3. Respond with ONLY a JSON object. No preamble text, no explanation, no markdown fencing.

RULES:
- Cite concrete facts, numbers, dates, URLs from search results
- Mark confidence: high (verified in multiple sources), medium (single source), low (inferred)
- Flag knowledge gaps honestly
- Keep it concise — quality over quantity
- NEVER present future-dated information as established fact

RESPOND WITH ONLY THIS JSON STRUCTURE:
{{"question": "...", "findings": [{{"claim": "...", "confidence": "high|medium|low", "reasoning": "...", "source": "URL"}}], "key_insights": ["..."], "knowledge_gaps": ["..."], "sources_used": ["url1"], "summary": "2-3 sentences"}}
"""


DEFAULT_STRATEGY = _build_default_strategy()

MAX_TOOL_ROUNDS = 5   # max rounds of tool use
MAX_SEARCHES = 10     # hard cap on total searches per run (prevents strategy-driven explosion)


def _extract_json(text: str) -> dict | None:
    """
    Extract a JSON object from text that may contain preamble or markdown fencing.
    Handles the common case where the model writes text before/after the JSON,
    or nests JSON inside markdown code fences within its output.
    """
    # Strip ALL markdown code fences (including nested ones)
    text = re.sub(r'```(?:json)?\s*\n?', '', text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy: find all balanced JSON objects and pick the best one
    # "Best" = the one with expected keys (question, findings, summary)
    EXPECTED_KEYS = {"question", "findings", "summary"}
    candidates = []

    # Find all top-level '{' positions
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Track depth to find the matching '}'
            depth = 0
            in_string = False
            escape_next = False
            for j in range(i, len(text)):
                c = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        fragment = text[i:j + 1]
                        try:
                            obj = json.loads(fragment)
                            if isinstance(obj, dict):
                                candidates.append(obj)
                        except json.JSONDecodeError:
                            pass
                        break
            i = j + 1 if depth == 0 else i + 1
        else:
            i += 1

    # Pick the candidate with the most expected keys
    if candidates:
        scored = [(len(EXPECTED_KEYS & set(c.keys())), len(c), c) for c in candidates]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return scored[0][2]

    # Last resort: try from first { to end with manual closing
    brace_start = text.find('{')
    if brace_start == -1:
        return None

    fragment = text[brace_start:]
    for suffix in ['"}]}', '"}]', '"}', '}']:
        try:
            return json.loads(fragment + suffix)
        except json.JSONDecodeError:
            continue

    return None


def research(question: str, strategy: str | None = None, critique: str | None = None) -> dict:
    """
    Run the researcher agent on a question with web search tool use.
    """
    system_prompt = strategy or DEFAULT_STRATEGY

    user_message = f"Research question: {question}"
    if critique:
        user_message += f"\n\nPREVIOUS ATTEMPT REJECTED. Feedback:\n{critique}\n\nSearch for more specific information and improve."

    messages = [{"role": "user", "content": user_message}]
    tools = [SEARCH_TOOL_DEFINITION]
    search_count = 0

    # Agentic tool-use loop
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODELS["researcher"],
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    search_count += 1
                    if search_count > MAX_SEARCHES:
                        print(f"  [SEARCH #{search_count}] SKIPPED — hit max searches ({MAX_SEARCHES})")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": '{"error": "Search limit reached. Compile your findings now."}',
                        })
                        continue
                    query = block.input.get("query", question)
                    max_res = min(block.input.get("max_results", 5), 8)
                    print(f"  [SEARCH #{search_count}] \"{query}\"")
                    results = web_search(query, max_results=max_res)
                    print(f"  [SEARCH #{search_count}] Got {len(results)} results")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(results),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break
    else:
        print(f"  [RESEARCHER] Hit max tool rounds ({MAX_TOOL_ROUNDS})")

    # Extract text from response
    raw_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw_text += block.text

    raw_text = raw_text.strip()

    # Robust JSON extraction
    result = _extract_json(raw_text)
    if result:
        result["_searches_made"] = search_count
        return result

    # Fallback: wrap raw text as a finding
    return {
        "question": question,
        "findings": [{"claim": raw_text[:2000], "confidence": "low", "reasoning": "Raw output, failed to parse structured response", "source": ""}],
        "key_insights": [],
        "knowledge_gaps": ["Response was not structured — may need strategy adjustment"],
        "sources_used": [],
        "summary": raw_text[:500],
        "_parse_error": True,
        "_searches_made": search_count,
    }
