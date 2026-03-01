"""Agent Hands execution CLI commands — execute, auto-build, exec status/evolve/principles/lessons."""

import os
import sys

from config import DEFAULT_DOMAIN
from cost_tracker import check_budget, get_daily_spend
from strategy_store import get_strategy


def show_next_task(domain: str):
    """Show the next AI-generated coding task for a domain."""
    from hands.task_generator import generate_tasks

    print(f"\n{'='*60}")
    print(f"  NEXT CODING TASKS — Domain: {domain}")
    print(f"{'='*60}\n")

    tasks = generate_tasks(domain)
    if not tasks:
        print("  Failed to generate tasks. Need more KB data?")
        print(f"  Run some research first: python main.py --auto --domain {domain}")
        return

    for i, task in enumerate(tasks):
        priority = task.get("priority", i + 1)
        complexity = task.get("expected_complexity", "?")
        print(f"  [{priority}] ({complexity}) {task.get('task', '?')}")
        print(f"      Reasoning: {task.get('reasoning', '?')[:100]}")
        if task.get("applies_claims"):
            print(f"      Applies KB: {', '.join(str(c)[:50] for c in task['applies_claims'][:3])}")
        if task.get("builds_on"):
            print(f"      Builds on: {task['builds_on'][:80]}")
        print()

    print(f"  Execute the top task:")
    top = tasks[0].get("task", "")
    print(f"    python main.py --domain {domain} --execute --goal \"{top[:80]}\"")
    print(f"\n  Or run auto-build to generate + execute automatically:")
    print(f"    python main.py --domain {domain} --auto-build")


def get_seed_build_task(domain: str) -> str:
    """Generate a reasonable seed task for a domain with no history."""
    seed_tasks = {
        "nextjs-react": (
            "Build a TypeScript React component library with: a reusable Button component "
            "with variants (primary, secondary, outline), a Card component with header/body/footer slots, "
            "and a Modal component with open/close animation. Include comprehensive unit tests with Jest "
            "and React Testing Library. Export all components with proper TypeScript types."
        ),
        "saas-building": (
            "Build a TypeScript REST API authentication module with: user registration with email validation, "
            "login with JWT token generation, token refresh endpoint, and middleware for protected routes. "
            "Include comprehensive tests. Use proper error handling and input validation."
        ),
        "python-backend": (
            "Build a Python async task queue library with: task registration decorators, "
            "priority-based scheduling, retry with exponential backoff, dead letter queue for failed tasks, "
            "and a simple in-memory broker. Include comprehensive pytest tests."
        ),
        "growth-hacking": (
            "Build a TypeScript analytics event tracking library with: typed event definitions, "
            "batch processing for network efficiency, local storage queue for offline support, "
            "automatic page view and click tracking, and a debug mode. Include comprehensive tests."
        ),
    }

    return seed_tasks.get(domain, (
        f"Build a well-structured TypeScript utility library for the {domain} domain "
        f"with clean exports, comprehensive error handling, full unit tests, "
        f"and proper TypeScript types. Include at least 3 core functions and 20+ test cases."
    ))


def run_execute(domain: str, goal: str, workspace_dir: str = ""):
    """
    Execute a task using Agent Hands.

    Pipeline: Plan → Execute → Validate → (retry if needed) → Store
    """
    from hands.planner import plan as create_plan_hands
    from hands.executor import execute_plan
    from hands.validator import validate_execution, identify_failing_steps
    from hands.exec_memory import save_exec_output, get_exec_stats
    from hands.tools.registry import create_default_registry
    from hands.workspace_diff import snapshot_workspace, compute_diff, format_diff_summary
    from hands.plan_cache import PlanCache
    from hands.checkpoint import ExecutionCheckpoint
    from hands.pattern_learner import PatternLearner
    from hands.planner import plan_repair
    from hands.artifact_tracker import ArtifactQualityDB, score_artifacts
    from hands.code_exemplars import CodeExemplarStore
    from hands.output_polisher import polish_artifacts, format_polish_log
    from hands.feedback_cache import FeedbackCache
    from hands.file_repair import identify_weak_artifacts, repair_files
    from hands.retry_advisor import recommend_strategy, should_skip_strategy, RetryRecommendation
    import config as _cfg

    # Budget check
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"\n[BUDGET] Blocked — daily limit reached")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AGENT HANDS — Execution Mode")
    print(f"  Domain: {domain}")
    print(f"  Goal: {goal}")
    print(f"  Budget: ${budget['remaining']:.4f} remaining")
    print(f"{'='*60}\n")

    # Set up workspace
    if not workspace_dir:
        workspace_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", domain)
    workspace_dir = os.path.realpath(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)
    print(f"[WORKSPACE] {workspace_dir}")

    # Dynamically allow the workspace dir for file operations
    if _cfg.EXEC_ALLOWED_DIRS is None:
        _cfg.EXEC_ALLOWED_DIRS = [workspace_dir]
    elif workspace_dir not in _cfg.EXEC_ALLOWED_DIRS:
        _cfg.EXEC_ALLOWED_DIRS = list(_cfg.EXEC_ALLOWED_DIRS) + [workspace_dir]

    # Detect if workspace is an existing repo
    is_repo = os.path.isdir(os.path.join(workspace_dir, ".git"))
    if is_repo:
        print(f"[WORKSPACE] Detected existing git repository")

    # Create tool registry
    registry = create_default_registry()
    tools_desc = registry.get_tool_descriptions()
    print(f"[TOOLS] {', '.join(registry.list_tools())}")

    # Load execution strategy (if exists)
    strategy, strategy_version = get_strategy("executor", domain)
    if strategy:
        print(f"[EXEC-STRATEGY] Loaded: {strategy_version}")
    else:
        # Use template as seed strategy
        from hands.exec_templates import get_template
        strategy = get_template(domain)
        strategy_version = "template"
        print(f"[EXEC-STRATEGY] Using template for '{domain}' (no evolved strategy yet)")

    # Collect strategy context sources (assembled with budget later)
    _raw_base_strategy = strategy or ""
    _raw_principles = ""
    _raw_lessons = ""
    _raw_quality_warnings = ""

    # Initialize pattern learner early for lesson collection
    learner_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exec_memory", "_patterns.json")
    pattern_learner = PatternLearner(learner_path)

    # Cross-domain execution principles (if available)
    try:
        from hands.exec_cross_domain import get_principles_for_domain
        _raw_principles = get_principles_for_domain(domain) or ""
        if _raw_principles:
            print(f"[EXEC-PRINCIPLES] Loaded cross-domain execution principles")
    except Exception:
        pass  # Cross-domain learning is optional

    # Learned execution lessons (from pattern_learner)
    _raw_lessons = pattern_learner.format_lessons_for_prompt(domain=domain) or ""
    if _raw_lessons:
        lesson_count = len(pattern_learner.get_lessons(domain=domain))
        print(f"[LESSONS] Loaded {lesson_count} learned execution lessons")

    # Load domain knowledge from Brain (if available)
    domain_knowledge = ""
    try:
        from memory_store import load_knowledge_base
        kb = load_knowledge_base(domain)
        if kb and kb.get("claims"):
            claims_text = []
            for claim in kb["claims"][:15]:
                claims_text.append(f"- {claim.get('claim', '')}")
            domain_knowledge = "\n".join(claims_text)
            print(f"[KB] Loaded {len(kb['claims'])} claims from Brain's knowledge base")
    except Exception:
        pass

    from config import EXEC_MAX_RETRIES, EXEC_QUALITY_THRESHOLD

    # Initialize plan cache, checkpoint, and pattern learner
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cache_path = os.path.join(base_dir, "exec_memory", "_plan_cache.json")
    plan_cache = PlanCache(cache_path)
    cp_dir = os.path.join(base_dir, "exec_memory", "_checkpoints")
    checkpoint = ExecutionCheckpoint(cp_dir)

    # Initialize artifact quality tracker and exemplar store
    quality_db_path = os.path.join(base_dir, "exec_memory", "_artifact_quality.json")
    artifact_quality_db = ArtifactQualityDB(quality_db_path)
    exemplar_path = os.path.join(base_dir, "exec_memory", "_exemplars.json")
    exemplar_store = CodeExemplarStore(exemplar_path)

    # Initialize feedback cache (persistent per-dimension failure signals)
    feedback_cache_path = os.path.join(base_dir, "exec_memory", "_feedback_cache.json")
    feedback_cache = FeedbackCache(feedback_cache_path)

    # Artifact quality warnings (collected for assembler)
    _raw_quality_warnings = artifact_quality_db.format_for_prompt(domain) or ""
    if _raw_quality_warnings:
        print(f"[ARTIFACT-QUALITY] Loaded quality warnings for weak archetypes")

    # Check for resumable checkpoint
    resume_info = checkpoint.get_resume_info(domain)
    if resume_info and resume_info["goal"] == goal:
        print(f"[CHECKPOINT] Found resumable execution ({resume_info['completed_step_count']} steps done)")
        print(f"  Started: {resume_info['started_at']}")

    attempt = 0
    previous_feedback = None
    final_plan = None
    final_report = None
    final_validation = None
    _use_surgical_retry = False
    _resume_data = None

    while attempt <= EXEC_MAX_RETRIES:
        attempt += 1
        print(f"\n--- Attempt {attempt}/{EXEC_MAX_RETRIES + 1} ---\n")

        # Step 1: Plan (with cache)
        cached_plan = None
        if attempt == 1 and not previous_feedback:
            cached_plan = plan_cache.get(goal, domain)
            if cached_plan:
                print(f"[PLAN-CACHE] Hit! Reusing plan from previous score {cached_plan.get('score', '?')}/10")
                plan_data = cached_plan["plan"]
            else:
                print("[PLANNER] Decomposing task into steps...")
        else:
            print("[PLANNER] Decomposing task into steps (retry — no cache)...")

        if not cached_plan:
            context = ""
            if previous_feedback:
                context = f"PREVIOUS ATTEMPT FEEDBACK (fix these issues):\n{previous_feedback}"

            # Inject persistent feedback from previous executions
            feedback_text = feedback_cache.get_for_planner(domain) or ""
            if feedback_text:
                print(f"[FEEDBACK] Injected recurring quality issue warnings")

            # Assemble strategy with budget-aware deduplication (planner gets 4000 chars)
            from hands.strategy_assembler import assemble as assemble_strategy, PLANNER_BUDGET
            planner_assembly = assemble_strategy(
                budget=PLANNER_BUDGET,
                base_strategy=_raw_base_strategy,
                principles=_raw_principles,
                lessons=_raw_lessons,
                quality_warnings=_raw_quality_warnings,
                feedback=feedback_text,
            )
            if planner_assembly.dropped:
                print(f"[STRATEGY] Budget: {planner_assembly.used}/{planner_assembly.budget} chars, dropped: {', '.join(planner_assembly.dropped)}")
            if planner_assembly.was_deduped:
                print(f"[STRATEGY] Deduplicated overlapping advice across sources")

            plan_data = create_plan_hands(
                goal=goal,
                tools_description=tools_desc,
                domain=domain,
                domain_knowledge=domain_knowledge,
                execution_strategy=planner_assembly.text,
                context=context,
                workspace_dir=workspace_dir,
                available_tools=registry.list_tools(),
            )

        if not plan_data:
            print("[PLANNER] Failed to generate plan")
            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = "Planning failed. Simplify the approach."
                continue
            break

        steps_count = len(plan_data.get("steps", []))
        complexity = plan_data.get("estimated_complexity", "?")
        print(f"[PLANNER] Generated {steps_count}-step plan (complexity: {complexity})")
        for step in plan_data.get("steps", []):
            crit = "!" if step.get("criticality", "required") == "required" else "?"
            print(f"  {step.get('step_number', '?')}{crit} [{step.get('tool', '?')}] {step.get('description', '')[:80]}")

        final_plan = plan_data

        # Step 1.5: Pre-flight validation (zero-cost structural checks)
        from hands.plan_preflight import preflight_check
        preflight = preflight_check(
            plan=plan_data,
            domain=domain,
            pattern_learner=pattern_learner,
            artifact_quality_db=artifact_quality_db,
            cost_ceiling=float(os.environ.get("MAX_EXECUTION_COST", "0.50")),
        )
        if preflight.issues:
            for issue in preflight.blockers:
                print(f"  [PREFLIGHT] BLOCKER: {issue.message}")
            for issue in preflight.warnings:
                print(f"  [PREFLIGHT] WARNING: {issue.message}")
        if not preflight.passed:
            print(f"  [PREFLIGHT] Plan blocked — {len(preflight.blockers)} blocker(s)")
            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = f"Plan pre-flight check failed:\n{preflight.format()}\nFix these issues."
                continue
            break
        elif preflight.warnings:
            print(f"  [PREFLIGHT] {len(preflight.warnings)} warning(s) — proceeding")
        else:
            print(f"  [PREFLIGHT] All checks passed")

        # Assemble executor strategy with exemplars (3000 char budget)
        from hands.strategy_assembler import assemble as assemble_strategy, EXECUTOR_BUDGET
        _raw_exemplars = ""
        predicted_archetypes = exemplar_store.predict_archetypes(plan_data)
        if predicted_archetypes:
            exemplars = exemplar_store.get_exemplars(domain, archetypes=predicted_archetypes)
            if exemplars:
                _raw_exemplars = exemplar_store.format_for_prompt(exemplars) or ""
                if _raw_exemplars:
                    print(f"[EXEMPLARS] {len(exemplars)} code examples for archetypes: {', '.join(e['archetype'] for e in exemplars)}")

        executor_assembly = assemble_strategy(
            budget=EXECUTOR_BUDGET,
            base_strategy=_raw_base_strategy,
            principles=_raw_principles,
            lessons=_raw_lessons,
            quality_warnings=_raw_quality_warnings,
            exemplars=_raw_exemplars,
        )
        strategy_with_exemplars = executor_assembly.text
        if executor_assembly.dropped:
            print(f"[EXEC-STRATEGY] Budget: {executor_assembly.used}/{executor_assembly.budget} chars, dropped: {', '.join(executor_assembly.dropped)}")

        # Snapshot workspace before execution
        ws_before = snapshot_workspace(workspace_dir) if workspace_dir else {}

        # Create checkpoint for crash recovery
        checkpoint.create(domain, goal, plan_data)

        # Step 2: Execute
        report = execute_plan(
            plan=plan_data,
            registry=registry,
            domain=domain,
            execution_strategy=strategy_with_exemplars,
            workspace_dir=workspace_dir,
            resume_from=_resume_data if _use_surgical_retry else None,
        )
        # Reset surgical retry state after use
        _use_surgical_retry = False
        _resume_data = None

        final_report = report

        # Compute workspace diff
        workspace_changes = {}
        if workspace_dir and ws_before:
            ws_after = snapshot_workspace(workspace_dir)
            workspace_changes = compute_diff(ws_before, ws_after)
            diff_summary = format_diff_summary(workspace_changes)
            print(f"\n[DIFF] {diff_summary}")
            report["workspace_changes"] = workspace_changes

        completed = report.get("completed_steps", 0)
        failed = report.get("failed_steps", 0)
        artifacts = report.get("artifacts", [])
        print(f"\n[EXECUTOR] Steps: {completed} completed, {failed} failed")
        if artifacts:
            print(f"[EXECUTOR] Artifacts: {', '.join(artifacts[:10])}")

        # Step 2.5: Polish artifacts before validation (zero-cost rule-based fixes)
        if artifacts:
            polish_result = polish_artifacts(artifacts, domain=domain)
            polish_log = format_polish_log(polish_result)
            if polish_log:
                print(f"\n{polish_log}")

        # Step 3: Validate
        print("\n[VALIDATOR] Evaluating execution quality...")
        validation = validate_execution(
            goal=goal,
            plan=plan_data,
            execution_report=report,
            domain=domain,
            domain_knowledge=domain_knowledge,
        )

        final_validation = validation

        score = validation.get("overall_score", 0)
        verdict = validation.get("verdict", "unknown")
        print(f"[VALIDATOR] Score: {score}/10 — Verdict: {verdict}")

        scores = validation.get("scores", {})
        if scores:
            for dim, val in scores.items():
                print(f"           {dim}: {val}/10")

        for s in validation.get("strengths", []):
            print(f"  + {s}")
        for w in validation.get("weaknesses", []):
            print(f"  - {w}")
        for ci in validation.get("critical_issues", []):
            print(f"  ! CRITICAL: {ci}")

        # Quality gate
        if score >= EXEC_QUALITY_THRESHOLD:
            print(f"\n[QUALITY] Accepted (score {score} >= threshold {EXEC_QUALITY_THRESHOLD})")
            # Cache the successful plan
            plan_cache.put(goal, domain, plan_data, score)
            # Clear checkpoint — execution complete
            checkpoint.mark_complete(domain, True)
            checkpoint.clear(domain)
            # Record positive feedback + auto-clear improved dimensions
            feedback_cache.auto_clear(domain, validation)
            break
        else:
            print(f"\n[QUALITY] Rejected (score {score} < threshold {EXEC_QUALITY_THRESHOLD})")

            # Record dimension-level failure feedback for future planners
            recorded_dims = feedback_cache.record(domain, validation)
            if recorded_dims:
                print(f"  [FEEDBACK] Recorded weak dimensions: {', '.join(recorded_dims)}")

            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = validation.get("actionable_feedback", "Improve quality.")
                if validation.get("critical_issues"):
                    previous_feedback += " CRITICAL: " + "; ".join(validation["critical_issues"])

                # Classify failure and get retry recommendation
                weak_artifacts = identify_weak_artifacts(
                    validation, report.get("artifacts", []), threshold=EXEC_QUALITY_THRESHOLD
                )
                strong_count = len(report.get("artifacts", [])) - len(weak_artifacts)

                failing = identify_failing_steps(
                    validation,
                    report.get("step_results", []),
                    plan_data.get("steps", []),
                )

                recommendation = recommend_strategy(
                    validation,
                    attempt=attempt,
                    max_retries=EXEC_MAX_RETRIES,
                    has_weak_artifacts=bool(weak_artifacts) and strong_count > len(weak_artifacts),
                    has_failing_steps=bool(failing) and len(failing) < len(plan_data.get("steps", [])),
                )
                print(f"  [RETRY ADVISOR] {recommendation.failure_class} failure → {recommendation.strategy} (confidence={recommendation.confidence:.0%})")
                if recommendation.skip_strategies:
                    print(f"  [RETRY ADVISOR] Skipping: {', '.join(recommendation.skip_strategies)}")

                # Strategy 1: Targeted file repair (cheapest — single Haiku call ~$0.003)
                if not should_skip_strategy(recommendation, RetryRecommendation.FILE_REPAIR):
                    if weak_artifacts and strong_count > len(weak_artifacts):
                        print(f"  [FILE REPAIR] {len(weak_artifacts)} file(s) need fixes, {strong_count} are good")
                        repair_result = repair_files(
                            files_to_fix=weak_artifacts,
                            goal=goal,
                            plan=plan_data,
                            domain=domain,
                            workspace_dir=workspace_dir,
                        )
                        if repair_result.get("files_fixed", 0) > 0:
                            print(f"  [FILE REPAIR] Fixed {repair_result['files_fixed']} file(s) (${repair_result.get('cost', 0):.4f})")
                            for d in repair_result.get("details", []):
                                if d.get("fixed"):
                                    print(f"    ✓ {d['path']}: {', '.join(d.get('changes', []))[:80]}")
                            # Re-validate with fixed files (skip re-execution)
                            continue
                        else:
                            print(f"  [FILE REPAIR] Could not fix files — trying next strategy")

                # Strategy 2: Surgical retry — only redo failing steps
                if not should_skip_strategy(recommendation, RetryRecommendation.SURGICAL):
                    if failing and len(failing) < len(plan_data.get("steps", [])):
                        print(f"  [SURGICAL RETRY] {len(failing)} steps need repair: {failing}")
                        repair = plan_repair(
                            original_plan=plan_data,
                            failing_steps=failing,
                            feedback=previous_feedback,
                            tools_description=tools_desc,
                            completed_steps=report.get("step_results", []),
                            domain=domain,
                            workspace_dir=workspace_dir,
                        )
                        if repair:
                            # Use repair plan + pass successful steps as resume_from
                            plan_data = repair
                            _use_surgical_retry = True
                            _resume_data = {
                                "completed_steps": [
                                    sr for sr in report.get("step_results", [])
                                    if sr.get("success") and sr.get("step") not in failing
                                ],
                                "artifacts": [
                                    a for sr in report.get("step_results", [])
                                    if sr.get("success") and sr.get("step") not in failing
                                    for a in sr.get("artifacts", [])
                                ],
                            }
                            print(f"  [SURGICAL RETRY] Repair plan: {len(repair.get('steps', []))} steps")
                            continue
                        else:
                            print(f"  [SURGICAL RETRY] Repair plan failed — falling back to full replan")

                print(f"  Retrying with feedback...")
            else:
                print(f"  Max retries reached. Storing as-is.")
                checkpoint.mark_complete(domain, False)
                checkpoint.clear(domain)

    # Step 4: Store result
    if final_plan and final_report and final_validation:
        filepath = save_exec_output(
            domain=domain,
            goal=goal,
            plan=final_plan,
            execution_report=final_report,
            validation=final_validation,
            attempt=attempt,
            strategy_version=strategy_version,
        )
        print(f"\n[MEMORY] Saved execution output: {filepath}")

    # Step 4.5: Track artifact quality and extract exemplars
    if final_plan and final_report and final_validation:
        try:
            scored_arts = score_artifacts(
                final_validation,
                final_report.get("step_results", []),
                final_report.get("artifacts", []),
            )
            if scored_arts:
                artifact_quality_db.update(domain, scored_arts)
                weak = artifact_quality_db.get_weak_archetypes(domain)
                if weak:
                    weak_info = ", ".join(
                        w["archetype"] + "(" + str(w["avg_score"]) + ")"
                        for w in weak[:3]
                    )
                    print(f"[ARTIFACT-QUALITY] Weak archetypes: {weak_info}")

                # Extract exemplars from accepted executions
                if final_validation.get("verdict") == "accept":
                    stored = exemplar_store.extract_and_store(domain, scored_arts)
                    if stored:
                        print(f"[EXEMPLARS] Stored {stored} new code exemplars from this execution")
        except Exception as e:
            print(f"[ARTIFACT-QUALITY] Error: {e}")

    # Step 5: Learn patterns from this execution
    if final_plan and final_report and final_validation:
        exec_output_for_learning = {
            "domain": domain,
            "goal": goal,
            "overall_score": final_validation.get("overall_score", 0),
            "accepted": final_validation.get("verdict") == "accept",
            "execution_report": final_report,
            "plan": final_plan,
            "validation": final_validation,
        }
        new_lessons = pattern_learner.analyze_execution(exec_output_for_learning)
        # Also extract plan-level patterns from successful executions
        plan_lessons = pattern_learner.analyze_plan_structure(exec_output_for_learning)
        all_new = new_lessons + plan_lessons
        if all_new:
            print(f"[PATTERN-LEARNER] Extracted {len(all_new)} new patterns:")
            for lesson in all_new[:5]:
                print(f"  • {lesson[:100]}")

    # Check if exec strategy evolution is due
    from hands.exec_memory import get_exec_stats
    stats = get_exec_stats(domain)
    from config import EXEC_EVOLVE_EVERY_N, EXEC_QUALITY_THRESHOLD
    if stats["count"] > 0 and stats["count"] % EXEC_EVOLVE_EVERY_N == 0:
        print(f"\n[EXEC-META] Evolution due ({stats['count']} outputs, every {EXEC_EVOLVE_EVERY_N})")
        run_exec_evolve(domain)

    # Extract cross-domain principles from high-scoring executions
    if final_validation and final_validation.get("overall_score", 0) >= EXEC_QUALITY_THRESHOLD:
        try:
            from hands.exec_cross_domain import extract_exec_principles
            new_p = extract_exec_principles(domain, min_outputs=3)
            if new_p:
                print(f"[EXEC-PRINCIPLES] Extracted {len(new_p)} new execution principles from '{domain}'")
        except Exception:
            pass  # Non-critical

    # Summary
    daily = get_daily_spend()
    print(f"\n{'='*60}")
    print(f"  EXECUTION COMPLETE")
    print(f"  Score: {final_validation.get('overall_score', 0) if final_validation else 0}/10")
    print(f"  Artifacts: {len(final_report.get('artifacts', [])) if final_report else 0}")
    print(f"  Domain '{domain}': {stats['count']} total executions, avg {stats['avg_score']:.1f}")
    print(f"  Daily spend: ${daily:.4f}")
    print(f"{'='*60}\n")


def run_auto_build(domain: str, rounds: int = 1, workspace_dir: str = ""):
    """
    Brain→Hands automated pipeline.

    The system:
    1. Reads domain KB + execution history
    2. Generates the best next coding task (from task_generator)
    3. Executes it via Hands (plan → execute → validate → store)
    4. Feeds results back into the learning loop
    5. Repeats for N rounds
    """
    from hands.task_generator import get_next_task
    from hands.exec_memory import get_exec_stats

    print(f"\n{'='*60}")
    print(f"  BRAIN→HANDS AUTO-BUILD PIPELINE")
    print(f"  Domain: {domain}")
    print(f"  Rounds: {rounds}")
    print(f"{'='*60}\n")

    round_results = []

    for round_num in range(1, rounds + 1):
        print(f"\n{'─'*50}")
        print(f"  BUILD ROUND {round_num}/{rounds}")
        print(f"{'─'*50}\n")

        # Budget check
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"[BUDGET] ✗ BLOCKED — daily limit reached after {round_num - 1} rounds")
            break
        print(f"[BUDGET] ${budget['remaining']:.4f} remaining")

        # Step 1: Generate coding task from KB
        print(f"\n[TASK-GEN] Generating coding task from domain knowledge...")
        task = get_next_task(domain)

        if not task:
            # Fallback: if no KB, use a domain-appropriate seed task
            stats = get_exec_stats(domain)
            if stats["count"] == 0:
                task = get_seed_build_task(domain)
                print(f"[TASK-GEN] Using seed task for new domain")
            else:
                print(f"[TASK-GEN] Failed to generate task. Stopping.")
                break

        print(f"\n[TASK] → {task}")

        # Step 2: Execute via Hands
        print(f"\n[EXECUTE] Running Hands pipeline...")
        run_execute(domain, task, workspace_dir=workspace_dir)

        # Track result
        stats = get_exec_stats(domain)
        round_results.append({
            "round": round_num,
            "task": task[:200],
            "total_executions": stats["count"],
            "avg_score": stats["avg_score"],
        })

        print(f"\n[ROUND {round_num}] Complete — {stats['count']} total executions, avg {stats['avg_score']:.1f}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  AUTO-BUILD COMPLETE")
    print(f"  Rounds completed: {len(round_results)}/{rounds}")
    if round_results:
        from hands.exec_memory import get_exec_stats
        final_stats = get_exec_stats(domain)
        print(f"  Total executions: {final_stats['count']}")
        print(f"  Average score: {final_stats['avg_score']:.1f}")
        print(f"  Accepted: {final_stats['accepted']}, Rejected: {final_stats['rejected']}")
    daily = get_daily_spend()
    print(f"  Daily spend: ${daily:.4f}")
    print(f"{'='*60}\n")


def show_exec_status(domain: str):
    """Show execution memory stats with full analytics."""
    from hands.exec_memory import get_exec_stats, load_exec_outputs
    from hands.exec_analytics import analyze_executions, format_analytics_report

    print(f"\n{'='*60}")
    print(f"  EXECUTION STATUS — Domain: {domain}")
    print(f"{'='*60}\n")

    stats = get_exec_stats(domain)
    if stats["count"] == 0:
        print(f"  No execution outputs yet for domain '{domain}'.")
        print(f"  Run: python main.py --domain {domain} --execute --goal 'Your task here'")
        return

    # Full analytics
    analytics = analyze_executions(domain)
    print(format_analytics_report(analytics))

    # Show recent outputs
    outputs = load_exec_outputs(domain)
    print(f"\n  Recent executions:")
    for o in outputs[-5:]:
        score = o.get("overall_score", 0)
        goal = o.get("goal", "?")[:60]
        verdict = o.get("verdict", "?")
        ts = o.get("timestamp", "?")[:10]
        print(f"    {ts} | {score}/10 ({verdict}) | {goal}")

    print(f"\n{'='*60}\n")


def run_exec_evolve(domain: str):
    """Force execution strategy evolution."""
    from hands.exec_meta import analyze_and_evolve_exec

    print(f"\n{'='*60}")
    print(f"  EXEC META-ANALYST — Strategy Evolution")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")

    result = analyze_and_evolve_exec(domain)
    if not result:
        print("  Not enough data or evolution failed.")
        return

    print(f"\n  New version: {result['new_version']} (pending approval)")
    print(f"  Run: python main.py --domain {domain} --approve {result['new_version']}")


def show_exec_principles():
    """Show learned execution principles."""
    from hands.exec_cross_domain import load_exec_principles

    print(f"\n{'='*60}")
    print(f"  LEARNED EXECUTION PRINCIPLES")
    print(f"{'='*60}\n")

    principles = load_exec_principles()
    if not principles:
        print("  No execution principles extracted yet.")
        print("  Principles are extracted after 3+ high-scoring executions in a domain.")
        return

    for i, p in enumerate(principles, 1):
        domains = ", ".join(p.get("domains_observed", ["general"]))
        evidence = p.get("evidence_count", 1)
        category = p.get("category", "general")
        print(f"  {i}. [{category}] {p.get('principle', '?')}")
        print(f"     Evidence: {evidence} | Domains: {domains}")
        if p.get("evidence"):
            print(f"     Detail: {p['evidence'][:120]}")
        print()

    print(f"  Total: {len(principles)} principles")


def show_exec_lessons(domain: str):
    """Show learned execution patterns/lessons."""
    from hands.pattern_learner import PatternLearner

    print(f"\n{'='*60}")
    print(f"  EXECUTION LESSONS — Domain: {domain or 'all'}")
    print(f"{'='*60}\n")

    learner_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exec_memory", "_patterns.json")
    learner = PatternLearner(learner_path)

    # Get all lessons (not just high-evidence ones)
    all_lessons = learner._lessons
    domain_lessons = [l for l in all_lessons if l.domain == domain or not domain]

    if not domain_lessons:
        print("  No execution lessons learned yet.")
        print("  Lessons are extracted after each execution.")
        return

    # Group by category
    by_category = {}
    for lesson in domain_lessons:
        cat = lesson.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(lesson)

    for cat, lessons in sorted(by_category.items()):
        print(f"  [{cat.upper()}]")
        for lesson in sorted(lessons, key=lambda l: l.evidence_count, reverse=True):
            impact = "+" if lesson.success_impact > 0 else "-" if lesson.success_impact < 0 else "~"
            print(f"    {impact} {lesson.lesson[:100]}")
            print(f"      Evidence: {lesson.evidence_count}x | Impact: {lesson.success_impact:+.1f}")
        print()

    stats = learner.stats()
    print(f"  Total: {stats['total_lessons']} lessons, {stats['high_evidence']} with strong evidence")
