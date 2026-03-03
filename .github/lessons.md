# Lessons Learned

Rules extracted from corrections. Reviewed at session start. Updated after every mistake.

## Codebase-Specific

- **atomic_json_write everywhere**: Never use raw `json.dump()` in production code. The hardening test (`test_no_raw_json_dump_in_production`) scans all .py files and fails if it finds bare json.dump calls. Always use `utils.atomic_write.atomic_json_write()`.
- **Test from the right directory**: Tests live in `agent-brain/tests/`. Run from `agent-brain/`, not the repo root.
- **Function names in cli/ don't always match the flag name**: e.g., `cli/tools_cmd.py` has `crawl()` not `crawl_site()`, `fetch()` not `fetch_url()`. Always read the actual function before wiring.
- **Return types vary across cli/ functions**: `list_pending()` returns `list[dict]` not `list[str]`. `approve_strategy()` returns `{"action": "approved"}` not `{"approved": true}`. Never assume — read the return.
- **System prompt honesty**: When describing what the system can do, distinguish "proven and tested" from "code exists but unproven." The user corrected this pattern — don't regress.

## General Patterns

- **Don't oversell features**: If code exists but hasn't been run in production, say "code exists, not battle-tested." Don't claim it "works."
- **Check the actual implementation before claiming behavior**: Don't describe what you think a function does. Read it. Then describe it.
- **Conversation window sizes affect cost**: Larger windows = more tokens per call. 40 messages is the current balance — don't increase without thinking about cost.
- **Watch for circular imports / recursive calls between modules**: The `memory_store.retrieve_relevant` → `rag.retrieval.retrieve_relevant_rag` → `memory_store.retrieve_relevant` infinite recursion was caused by fallback paths calling the dispatch function instead of the implementation function. When module A dispatches to module B, module B's fallback must call A's implementation directly (e.g., `retrieve_relevant_tfidf`), NOT A's dispatch function (e.g., `retrieve_relevant`).
- **Run full test suite after every change session**: The recursion bug was pre-existing but only caught when running tests. Always verify before declaring done.
