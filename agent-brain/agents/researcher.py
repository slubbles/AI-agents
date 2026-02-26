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
from config import ANTHROPIC_API_KEY, MODELS, MAX_TOOL_ROUNDS, MAX_SEARCHES, MAX_FETCHES, BROWSER_ENABLED
from tools.web_search import web_search, SEARCH_TOOL_DEFINITION
from tools.web_fetcher import fetch_page, search_and_fetch, FETCH_TOOL_DEFINITION, SEARCH_AND_FETCH_TOOL_DEFINITION
from cost_tracker import log_cost
from memory_store import retrieve_relevant, load_knowledge_base
from utils.retry import create_message
from utils.json_parser import extract_json

# Browser tools — optional, only loaded when BROWSER_ENABLED is True
_browser_tools_loaded = False
BROWSER_FETCH_TOOL = None
BROWSER_SEARCH_TOOL = None
_execute_browser_tool = None

def _load_browser_tools():
    """Lazily load browser tool definitions and executor."""
    global _browser_tools_loaded, BROWSER_FETCH_TOOL, BROWSER_SEARCH_TOOL, _execute_browser_tool
    if _browser_tools_loaded:
        return
    try:
        from browser.tools import BROWSER_FETCH_TOOL as _bft, BROWSER_SEARCH_TOOL as _bst, execute_browser_tool
        BROWSER_FETCH_TOOL = _bft
        BROWSER_SEARCH_TOOL = _bst
        _execute_browser_tool = execute_browser_tool
        _browser_tools_loaded = True
    except ImportError as e:
        print(f"  [BROWSER] Import failed: {e}")
        _browser_tools_loaded = False


client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _build_baseline() -> str:
    """Baseline instructions that ALWAYS apply, regardless of domain strategy."""
    today = date.today().isoformat()  # e.g. "2026-02-23"
    baseline = f"""\
You are a research agent with web search AND page reading capability.

TODAY'S DATE: {today}
Any source, event, or data dated AFTER {today} is FUTURE and cannot be verified.
Only report information dated on or before {today} as factual. If a search result references
a future date, flag it explicitly as unverified/projected and set confidence to "low".

ANTI-HALLUCINATION RULES (violating these WILL get your output rejected):
- NEVER fabricate URLs, CVE numbers, file paths, version numbers, or benchmark data.
  Every specific claim must trace to content you actually saw in search results or fetched pages.
- If you searched and didn't find the requested data, say "not found in available sources"
  rather than constructing plausible-sounding details from memory.
- An honest "I could not find X" scores HIGHER than a fabricated answer.
  The critic penalizes hallucination more severely than knowledge gaps.
- When reporting a URL, it MUST be a URL that appeared in your search results or fetched pages.
  Do NOT construct URLs from memory — they are often wrong.
- When citing file paths, function names, or code: ONLY cite what you read from a fetched page.
  If you haven't fetched the source, say "based on documentation" not "the code at path/to/file.js shows..."

WORKFLOW:
1. Use web_search 1-2 times to find relevant URLs.
2. Use fetch_page on the 2-3 most promising URLs to read full page content.
   This gives you 10-50x more information than search snippets alone.
3. OR use search_and_fetch for a combined search+read in one step.
4. After reading pages, compile your findings with SPECIFIC details from the actual content.
5. Respond with ONLY a JSON object. No preamble text, no explanation, no markdown fencing.

IMPORTANT: ALWAYS fetch pages when possible. Search snippets are 100 words; full pages are 3000-8000 words.
The quality difference is enormous. Prioritize fetch_page over multiple web_search calls.
"""
    # Add browser instructions when browser tools are available
    if BROWSER_ENABLED and _browser_tools_loaded:
        baseline += """
BROWSER TOOLS (for sites that need JavaScript or authentication):
- browser_fetch: Use for sites like LinkedIn, Indeed, Glassdoor, Cloudflare-protected, or JS-heavy pages.
  SLOWER than fetch_page — only use when regular fetch_page fails or the site is known to require JS.
- browser_search: Search within a specific site using Google + browser rendering.
  Use for site-specific searches like finding profiles on LinkedIn or jobs on Indeed.
Prefer fetch_page first. Only escalate to browser_fetch if fetch_page returns empty/blocked content.
"""
    baseline += """
RULES:
- Cite concrete facts, numbers, dates, URLs from search results
- Mark confidence: high (verified in multiple sources), medium (single source), low (inferred)
- When you find an important claim, search for corroboration from a second independent source
  before marking confidence as "high". Single-source claims are "medium" at best.
- Flag knowledge gaps honestly
- Keep it concise — quality over quantity
- NEVER present future-dated information as established fact

DEPTH PROTOCOL — every finding should answer at least 2 of these:
  - WHY does this work this way? (mechanism/rationale)
  - WHAT trade-offs does this involve? (cost/benefit)
  - HOW does this compare to alternatives? (context)
  - WHAT would break if this changed? (implications)
If your finding only states WHAT exists, you haven't gone deep enough.
Search for explanatory content, not just confirmatory content.

RESPOND WITH ONLY THIS JSON STRUCTURE:
{{"question": "...", "findings": [{{"claim": "...", "confidence": "high|medium|low", "reasoning": "...", "source": "URL"}}], "key_insights": ["..."], "knowledge_gaps": ["..."], "sources_used": ["url1"], "summary": "2-3 sentences"}}
"""
    return baseline


def _build_system_prompt(domain_strategy: str | None = None) -> str:
    """
    Build the full system prompt. ALWAYS includes baseline (date awareness, JSON
    format, core rules). If a domain strategy exists, it's layered ON TOP — it
    can adjust search approach, source priorities, and analysis depth, but cannot
    override the output format or temporal verification rules.
    """
    baseline = _build_baseline()
    if not domain_strategy:
        return baseline
    return f"""{baseline}

=== DOMAIN-SPECIFIC STRATEGY ===
The following strategy provides domain-specific guidance for your research.
Follow its search approach, source priorities, and analysis requirements.
However, you MUST still output ONLY the JSON structure defined above.
Do NOT output markdown, tables, or prose — ONLY the JSON object.

{domain_strategy}
=== END DOMAIN STRATEGY ===
"""

# MAX_TOOL_ROUNDS, MAX_SEARCHES, MAX_FETCHES imported from config

# Context compression threshold (chars of tool result content)
CONTEXT_COMPRESS_THRESHOLD = 30000


def _estimate_messages_size(messages: list) -> int:
    """Estimate total chars of tool result content in messages."""
    total = 0
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for item in msg["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    content = item.get("content", "")
                    total += len(content) if isinstance(content, str) else 0
    return total


def _compress_messages(messages: list) -> None:
    """
    Compress older tool results when context gets too large.
    Summarizes older tool results to key facts (URLs, titles, key data points)
    while keeping the most recent 2 tool result messages in full.
    """
    total_size = _estimate_messages_size(messages)
    if total_size <= CONTEXT_COMPRESS_THRESHOLD:
        return
    
    # Find all user messages with tool results (oldest first)
    tool_msg_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            has_tool = any(
                isinstance(item, dict) and item.get("type") == "tool_result"
                for item in msg["content"]
            )
            if has_tool:
                tool_msg_indices.append(i)
    
    # Keep the last 2 tool result messages intact, compress older ones
    to_compress = tool_msg_indices[:-2] if len(tool_msg_indices) > 2 else []
    
    for idx in to_compress:
        msg = messages[idx]
        compressed_content = []
        for item in msg["content"]:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                content = item.get("content", "")
                if isinstance(content, str) and len(content) > 500:
                    # Preserve ALL URLs before truncating (most valuable for citations)
                    urls = re.findall(r'https?://[^\s"\'>]+', content)
                    lines = content.split("\n")[:5]
                    summary = "\n".join(lines)[:400]
                    url_block = "\nPreserved URLs: " + " ".join(sorted(set(urls))) if urls else ""
                    item["content"] = f"[COMPRESSED] {summary}...{url_block}"
            compressed_content.append(item)
        msg["content"] = compressed_content


def research(question: str, strategy: str | None = None, critique: str | None = None, domain: str = "general") -> dict:
    """
    Run the researcher agent on a question with web search tool use.
    
    Now memory-informed: retrieves relevant past findings + synthesized knowledge
    before searching, so the researcher builds on existing knowledge instead of
    starting from zero.
    """
    system_prompt = _build_system_prompt(strategy)

    # --- Memory recall: inject prior knowledge ---
    prior_knowledge_block = ""
    
    # 1. Check for synthesized knowledge base
    kb = load_knowledge_base(domain)
    if kb and kb.get("claims"):
        active_claims = [c for c in kb["claims"] if c.get("status") == "active"]
        if active_claims:
            kb_summary = f"\nSYNTHESIZED KNOWLEDGE BASE ({len(active_claims)} active claims):\n"
            for claim in active_claims[:15]:  # Top 15 claims
                conf = claim.get("confidence", "?")
                kb_summary += f"  - [{conf}] {claim.get('claim', '')}\n"
            if kb.get("domain_summary"):
                kb_summary = f"\nDOMAIN SUMMARY: {kb['domain_summary']}\n" + kb_summary
            prior_knowledge_block += kb_summary
    
    # 2. Retrieve relevant past findings — include concrete claims with sources
    relevant = retrieve_relevant(domain, question, max_results=3)
    if relevant:
        recall_block = f"\nRELEVANT PAST FINDINGS ({len(relevant)} previous outputs):\n"
        for r in relevant:
            recall_block += f"\n  Previous question: \"{r['question']}\" (score: {r['score']}/10)\n"
            recall_block += f"  Summary: {r['summary']}\n"
            if r.get("key_insights"):
                recall_block += f"  Key insights: {'; '.join(r['key_insights'][:3])}\n"
            if r.get("knowledge_gaps"):
                recall_block += f"  Known gaps: {'; '.join(r['knowledge_gaps'][:3])}\n"
            # Include concrete claims with sources for building upon
            if r.get("findings"):
                recall_block += "  Key verified claims:\n"
                for finding in r["findings"][:3]:
                    conf = finding.get("confidence", "?")
                    source = finding.get("source", "no source")
                    claim_text = finding.get("claim", "")[:150]
                    recall_block += f"    [{conf}] {claim_text} (source: {source})\n"
        prior_knowledge_block += recall_block
    
    # Prior knowledge injected into user message (below), not system prompt,
    # so the static system prompt stays cacheable across tool-use rounds.

    user_message = f"Research question: {question}"
    
    # Inject prior knowledge into the user message (not system prompt) so the
    # static system prompt remains cacheable across tool-use rounds.
    if prior_knowledge_block:
        user_message = f"""=== PRIOR KNOWLEDGE (from your memory) ===
PRIOR KNOWLEDGE INSTRUCTIONS:
- Claims marked [high] are verified — don't re-search these unless the question specifically requires updated data.
- Claims marked [medium] may benefit from corroboration — search for a second source.
- If new findings CONTRADICT a prior claim, flag it explicitly as a contradiction.
- Focus searches on the KNOWLEDGE GAPS listed below, not on re-verifying known claims.
{prior_knowledge_block}
=== END PRIOR KNOWLEDGE ===

Research question: {question}"""

    if critique:
        user_message += f"\n\nPREVIOUS ATTEMPT REJECTED. Feedback:\n{critique}\n\nSearch for more specific information and improve."

    messages = [{"role": "user", "content": user_message}]
    tools = [SEARCH_TOOL_DEFINITION, FETCH_TOOL_DEFINITION, SEARCH_AND_FETCH_TOOL_DEFINITION]
    
    # Add browser tools when enabled (for JS-rendered / auth-required sites)
    browser_fetch_count = 0
    if BROWSER_ENABLED:
        _load_browser_tools()
        if _browser_tools_loaded and BROWSER_FETCH_TOOL and BROWSER_SEARCH_TOOL:
            tools.append(BROWSER_FETCH_TOOL)
            tools.append(BROWSER_SEARCH_TOOL)
    
    search_count = 0
    fetch_count = 0
    empty_search_count = 0  # Track searches that returned 0 results
    tool_log = []  # Track tool usage for critic + meta-analyst observability

    # Agentic tool-use loop
    for _ in range(MAX_TOOL_ROUNDS):
        response = create_message(
            client,
            model=MODELS["researcher"],
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Track cost
        log_cost(MODELS["researcher"], response.usage.input_tokens, response.usage.output_tokens, "researcher", domain)

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    
                    # Handle fetch_page tool
                    if tool_name == "fetch_page":
                        fetch_count += 1
                        if fetch_count > MAX_FETCHES:
                            print(f"  [FETCH #{fetch_count}] SKIPPED — hit max fetches ({MAX_FETCHES})")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": '{"error": "Fetch limit reached. Compile your findings now."}',
                            })
                            continue
                        url = block.input.get("url", "")
                        print(f"  [FETCH #{fetch_count}] {url[:80]}")
                        result = fetch_page(url)
                        if result:
                            # Format for researcher consumption — cap at 6K for rich content
                            page_content = result['content'][:6000]
                            content = f"PAGE: {result['title']}\nURL: {result['url']}\nContent ({result['content_length']} chars):\n{page_content}"
                            if result['headings']:
                                content += f"\nHeadings: {', '.join(result['headings'][:10])}"
                            if result['code_blocks']:
                                content += f"\nCode examples: {len(result['code_blocks'])} found"
                                for i, code in enumerate(result['code_blocks'][:3]):
                                    content += f"\n--- Code {i+1} ---\n{code[:500]}"
                            print(f"  [FETCH #{fetch_count}] Got {result['content_length']} chars")
                            tool_log.append({"tool": "fetch_page", "url": url, "success": True, "chars": result['content_length'], "title": result['title'][:80]})
                        else:
                            content = '{"error": "Failed to fetch page. Try a different URL."}'
                            print(f"  [FETCH #{fetch_count}] FAILED")
                            tool_log.append({"tool": "fetch_page", "url": url, "success": False, "chars": 0})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        })
                        continue
                    
                    # Handle search_and_fetch tool
                    if tool_name == "search_and_fetch":
                        search_count += 1
                        max_fetch = min(block.input.get("max_fetch", 3), 5)
                        fetch_count += max_fetch  # Account for actual pages fetched
                        if search_count > MAX_SEARCHES or fetch_count > MAX_FETCHES:
                            print(f"  [SEARCH+FETCH] SKIPPED — hit max searches ({MAX_SEARCHES})")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": '{"error": "Search limit reached. Compile your findings now."}',
                            })
                            continue
                        query = block.input.get("query", question)
                        print(f"  [SEARCH+FETCH] \"{query}\" (fetch top {max_fetch})")
                        result = search_and_fetch(query, max_results=5, max_fetch=max_fetch)
                        # Format combined results
                        content_parts = []
                        content_parts.append(f"Search results for: {query}")
                        for sr in result['search_results']:
                            content_parts.append(f"  - {sr['title']}: {sr['snippet'][:150]}")
                        for fp in result['fetched_pages']:
                            content_parts.append(f"\n=== FULL PAGE: {fp['title']} ===")
                            content_parts.append(f"URL: {fp['url']}")
                            content_parts.append(fp['content'])
                            if fp['code_blocks']:
                                for i, code in enumerate(fp['code_blocks'][:3]):
                                    content_parts.append(f"--- Code {i+1} ---\n{code[:500]}")
                        content = "\n".join(content_parts)
                        print(f"  [SEARCH+FETCH] {len(result['fetched_pages'])} pages, {result['total_content_chars']} chars")
                        tool_log.append({"tool": "search_and_fetch", "query": query, "success": True, "pages_fetched": len(result['fetched_pages']), "chars": result['total_content_chars']})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content[:12000],  # Cap at 12K chars to avoid context bloat
                        })
                        continue
                    
                    # Handle browser_fetch tool (Playwright stealth)
                    if tool_name == "browser_fetch" and _browser_tools_loaded and _execute_browser_tool:
                        from config import BROWSER_MAX_FETCHES
                        browser_fetch_count += 1
                        if browser_fetch_count > BROWSER_MAX_FETCHES:
                            print(f"  [BROWSER #{browser_fetch_count}] SKIPPED — hit max browser fetches ({BROWSER_MAX_FETCHES})")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": '{"error": "Browser fetch limit reached. Use regular fetch_page or compile findings."}',
                            })
                            continue
                        url = block.input.get("url", "")
                        mode = block.input.get("extract_mode", "text")
                        print(f"  [BROWSER #{browser_fetch_count}] {url[:80]} (mode={mode})")
                        import asyncio
                        try:
                            content = asyncio.run(_execute_browser_tool(tool_name, block.input))
                            print(f"  [BROWSER #{browser_fetch_count}] Got content ({len(content)} chars)")
                            tool_log.append({"tool": "browser_fetch", "url": url, "success": True, "chars": len(content)})
                        except Exception as e:
                            content = f'{{"error": "Browser fetch failed: {e}"}}'
                            print(f"  [BROWSER #{browser_fetch_count}] FAILED: {e}")
                            tool_log.append({"tool": "browser_fetch", "url": url, "success": False, "error": str(e)})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content[:15000],
                        })
                        continue

                    # Handle browser_search tool (Playwright stealth + Google)
                    if tool_name == "browser_search" and _browser_tools_loaded and _execute_browser_tool:
                        from config import BROWSER_MAX_FETCHES
                        browser_fetch_count += 1
                        search_count += 1
                        if browser_fetch_count > BROWSER_MAX_FETCHES or search_count > MAX_SEARCHES:
                            print(f"  [BROWSER SEARCH] SKIPPED — hit limits")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": '{"error": "Browser/search limit reached. Compile findings now."}',
                            })
                            continue
                        query = block.input.get("query", "")
                        site = block.input.get("site", "")
                        print(f"  [BROWSER SEARCH] \"{query}\" site={site}")
                        import asyncio
                        try:
                            content = asyncio.run(_execute_browser_tool(tool_name, block.input))
                            print(f"  [BROWSER SEARCH] Got results ({len(content)} chars)")
                            tool_log.append({"tool": "browser_search", "query": query, "site": site, "success": True, "chars": len(content)})
                        except Exception as e:
                            content = f'{{"error": "Browser search failed: {e}"}}'
                            print(f"  [BROWSER SEARCH] FAILED: {e}")
                            tool_log.append({"tool": "browser_search", "query": query, "success": False, "error": str(e)})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content[:12000],
                        })
                        continue

                    # Handle web_search tool (original)
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
                    
                    # Detect search failures (error marker in result)
                    search_failed = len(results) == 1 and results[0].get("error", False)
                    if search_failed:
                        print(f"  [SEARCH #{search_count}] FAILED: {results[0].get('snippet', 'unknown error')}")
                        empty_search_count += 1
                        tool_log.append({"tool": "web_search", "query": query, "success": False, "results": 0})
                    else:
                        print(f"  [SEARCH #{search_count}] Got {len(results)} results")
                        tool_log.append({"tool": "web_search", "query": query, "success": True, "results": len(results)})
                    
                    if len(results) == 0:
                        empty_search_count += 1
                    
                    # Smart recovery: if too many empty searches, inject guidance
                    if empty_search_count >= 3 and search_count <= MAX_SEARCHES - 2:
                        results_with_hint = results if results else []
                        hint = (
                            "\n\nNOTE: Multiple searches returned 0 results. Try BROADER, "
                            "SIMPLER search terms. Remove specific dates, names, or jargon. "
                            "Search for the general topic first, then narrow down."
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(results_with_hint) + hint,
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(results),
                        })
                    
                    # Fetch nudge: after search results, remind to fetch pages
                    if fetch_count == 0 and search_count >= 1 and not search_failed:
                        nudge = ("\n\nREMINDER: Use fetch_page on the 2-3 most relevant "
                                 "URLs above for much richer data. Search snippets are only "
                                 "~100 words; full pages give you 3000-8000 words of content.")
                        tool_results[-1]["content"] = tool_results[-1]["content"] + nudge

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            
            # Context compression: keep total tool result text under ~30K chars
            # to prevent quality degradation from context bloat.
            # Summarize older tool results, keep recent ones in full.
            _compress_messages(messages)
        else:
            break
    else:
        print(f"  [RESEARCHER] Hit max tool rounds ({MAX_TOOL_ROUNDS})")
        # Model wanted more tools but we cut it off — force a synthesis response
        # The last response was tool_use, so we need one more call to get JSON
        messages.append({"role": "assistant", "content": response.content})
        # Return empty results for the pending tool calls
        pending_results = []
        for block in response.content:
            if block.type == "tool_use":
                pending_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": '{"error": "Tool round limit reached. You MUST now compile your findings into the JSON response format. No more tools."}',
                })
        if pending_results:
            messages.append({"role": "user", "content": pending_results})
        # Final synthesis call — no tools available
        response = create_message(
            client,
            model=MODELS["researcher"],
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=[],  # No tools — force text output
        )
        log_cost(MODELS["researcher"], response.usage.input_tokens, response.usage.output_tokens, "researcher", domain)

    # Extract text from response
    raw_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw_text += block.text

    raw_text = raw_text.strip()

    # Robust JSON extraction
    EXPECTED_KEYS = {"question", "findings", "summary"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)
    if result:
        findings = result.get("findings", [])
        # Smart recovery: if structured output has 0 findings but we did searches,
        # something went wrong — flag it for the retry loop
        if not findings and search_count > 0:
            print(f"  [RESEARCHER] ⚠ Structured output but 0 findings from {search_count} searches")
            result["_zero_findings"] = True
        result["_searches_made"] = search_count
        result["_empty_searches"] = empty_search_count
        result["_tool_log"] = tool_log
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
        "_empty_searches": empty_search_count,
        "_tool_log": tool_log,
    }
