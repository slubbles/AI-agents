# Lessons Learned

Rules extracted from corrections. Reviewed at session start. Updated after every mistake.

## Codebase-Specific

- **atomic_json_write everywhere**: Never use raw `json.dump()` in production code. The hardening test (`test_no_raw_json_dump_in_production`) scans all .py files and fails if it finds bare json.dump calls. Always use `utils.atomic_write.atomic_json_write()`.
- **Test from the right directory**: Tests live in `agent-brain/tests/`. Run from `agent-brain/`, not the repo root.
- **Function names in cli/ don't always match the flag name**: e.g., `cli/tools_cmd.py` has `crawl()` not `crawl_site()`, `fetch()` not `fetch_url()`. Always read the actual function before wiring.
- **Return types vary across cli/ functions**: `list_pending()` returns `list[dict]` not `list[str]`. `approve_strategy()` returns `{"action": "approved"}` not `{"approved": true}`. Never assume — read the return.
- **System prompt honesty**: When describing what the system can do, distinguish "proven and tested" from "code exists but unproven." The user corrected this pattern — don't regress.
- **Resource cleanup on all exit paths**: When a function creates resources (subprocesses, browser sessions), verify cleanup runs on ALL exit paths: normal return, early return (_abort), exceptions. The executor `_abort` handler returned without calling `visual_gate.cleanup()`, leaking dev servers. Always audit every `return` statement in functions that own resources.
- **New features must be wired to all callers**: When adding params to a function (e.g., `page_type` to `execute_plan`), grep ALL call sites and update them. The CLI's `execute_plan()` call was missing `page_type`, `research_context`, `visual_context` — making Obj 4/5 features unreachable from CLI.
- **Code tool paths must be workspace-relative**: The executor auto-injects `cwd` for terminal but NOT for code tool. Relative paths in code tool resolve against the process cwd (agent-brain/), not workspace_dir. Always prepend workspace_dir for relative code paths in executor.
- **OpenRouter message converter must handle dataclass blocks**: When the executor appends `response.content` (list of ToolUseBlock/TextBlock dataclasses) to the conversation, the OpenRouter message converter must recognize these alongside plain dicts. Without this, assistant tool_calls are silently dropped and the next tool_result becomes orphaned, breaking the multi-turn loop.
- **API provider fallback**: When Anthropic direct balance is $0, route PREMIUM_MODEL through OpenRouter using `anthropic/claude-sonnet-4` (not the dated version string). The `create_message` function checks `model.startswith("claude-")` — OpenRouter model IDs like `anthropic/claude-sonnet-4` bypass this check and route correctly through `call_llm`.
- **get_daily_spend() returns dict not float**: The cost tracker returns `{"total_usd": ..., "by_provider": ...}`. Don't format it directly with `:.4f` — extract `total_usd` first.

- **Patch local imports at source module**: When a function uses local imports (e.g., `from hands.planner import plan` inside `pipeline()`), patch the source module (`hands.planner.plan`) not the consuming module (`agents.cortex.plan`). Local imports don't create module-level attributes, so patching the consumer fails silently.

- **Don't oversell features**: If code exists but hasn't been run in production, say "code exists, not battle-tested." Don't claim it "works."
- **Check the actual implementation before claiming behavior**: Don't describe what you think a function does. Read it. Then describe it.
- **Conversation window sizes affect cost**: Larger windows = more tokens per call. 40 messages is the current balance — don't increase without thinking about cost.
- **Watch for circular imports / recursive calls between modules**: The `memory_store.retrieve_relevant` → `rag.retrieval.retrieve_relevant_rag` → `memory_store.retrieve_relevant` infinite recursion was caused by fallback paths calling the dispatch function instead of the implementation function. When module A dispatches to module B, module B's fallback must call A's implementation directly (e.g., `retrieve_relevant_tfidf`), NOT A's dispatch function (e.g., `retrieve_relevant`).
- **Run full test suite after every change session**: The recursion bug was pre-existing but only caught when running tests. Always verify before declaring done.
- **Use simple words in user-facing writeups**: The user asked to avoid complicated words like "corpus". Prefer plain language in reports and suggestions unless a technical term is necessary.
