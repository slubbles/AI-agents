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

MAX_TOOL_ROUNDS = 5  # max search calls per research run


def _extract_json(text: str) -> dict | None:
    """
    Extract a JSON object from text that may contain preamble or markdown fencing.
    Handles the common case where the model writes text before/after the JSON.
    """
    # Strip markdown code fences
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first { and try to parse from there
    brace_start = text.find('{')
    if brace_start == -1:
        return None

    # Try progressively from the first { to find valid JSON
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start:i + 1])
                except json.JSONDecodeError:
                    continue

    # Last resort: try parsing from first { to end (truncated JSON)
    # Attempt to close it manually
    fragment = text[brace_start:]
    # Try adding closing braces/brackets
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
