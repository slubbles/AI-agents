"""
Data Validator — Integrity Checks for Memory, Strategies, and Costs

Verifies:
- Memory file JSON structure and required fields
- Strategy file consistency and meta integrity
- Cost log format and date consistency
- Cross-reference integrity (strategy versions referenced in memory exist)
- Domain directory health

No API calls — pure filesystem validation.
"""

import json
import os
from datetime import datetime, timezone
from config import MEMORY_DIR, STRATEGY_DIR, LOG_DIR, QUALITY_THRESHOLD


REQUIRED_OUTPUT_FIELDS = [
    "timestamp", "domain", "question", "overall_score",
    "research", "critique",
]

REQUIRED_STRATEGY_FIELDS = [
    "agent_role", "domain", "version", "strategy", "status",
]


def validate_memory(domain: str | None = None) -> dict:
    """
    Validate all memory files for a domain (or all domains).
    
    Returns:
        {valid: int, invalid: int, warnings: int, issues: [str], domain_stats: {}}
    """
    if not os.path.exists(MEMORY_DIR):
        return {"valid": 0, "invalid": 0, "warnings": 0, "issues": ["MEMORY_DIR does not exist"]}
    
    domains = []
    if domain:
        domains = [domain]
    else:
        for d in sorted(os.listdir(MEMORY_DIR)):
            if os.path.isdir(os.path.join(MEMORY_DIR, d)) and not d.startswith("_"):
                domains.append(d)
    
    valid = 0
    invalid = 0
    warnings = 0
    issues = []
    domain_stats = {}
    
    for d in domains:
        domain_dir = os.path.join(MEMORY_DIR, d)
        if not os.path.exists(domain_dir):
            issues.append(f"[{d}] Domain directory not found")
            continue
        
        d_valid = 0
        d_invalid = 0
        d_warnings = 0
        
        for filename in sorted(os.listdir(domain_dir)):
            if not filename.endswith(".json") or filename.startswith("_"):
                continue
            
            filepath = os.path.join(domain_dir, filename)
            
            # Parse JSON
            try:
                with open(filepath) as f:
                    record = json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"[{d}] {filename}: Invalid JSON — {e}")
                invalid += 1
                d_invalid += 1
                continue
            except IOError as e:
                issues.append(f"[{d}] {filename}: Read error — {e}")
                invalid += 1
                d_invalid += 1
                continue
            
            # Check required fields
            file_valid = True
            for field in REQUIRED_OUTPUT_FIELDS:
                if field not in record:
                    issues.append(f"[{d}] {filename}: Missing required field '{field}'")
                    file_valid = False
            
            # Check types
            if "overall_score" in record:
                score = record["overall_score"]
                if not isinstance(score, (int, float)):
                    issues.append(f"[{d}] {filename}: 'overall_score' is not numeric: {type(score).__name__}")
                    file_valid = False
                elif score < 0 or score > 10:
                    issues.append(f"[{d}] {filename}: Score out of range: {score}")
                    warnings += 1
                    d_warnings += 1
            
            # Check domain consistency
            if record.get("domain") and record["domain"] != d:
                issues.append(f"[{d}] {filename}: Domain mismatch — file says '{record['domain']}' but stored in '{d}'")
                warnings += 1
                d_warnings += 1
            
            # Check timestamp parseable
            ts = record.get("timestamp", "")
            if ts:
                try:
                    datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    issues.append(f"[{d}] {filename}: Invalid timestamp format: {ts}")
                    warnings += 1
                    d_warnings += 1
            
            # Check accepted field exists and is consistent with score
            if "accepted" not in record:
                issues.append(f"[{d}] {filename}: Missing 'accepted' boolean field")
                warnings += 1
                d_warnings += 1
            elif isinstance(record.get("overall_score"), (int, float)):
                score = record["overall_score"]
                accepted = record["accepted"]
                expected = score >= QUALITY_THRESHOLD
                if accepted != expected:
                    issues.append(f"[{d}] {filename}: Score/accepted mismatch — "
                                  f"score={score}, accepted={accepted}, expected={expected}")
                    warnings += 1
                    d_warnings += 1
            
            # Check research is a dict
            if "research" in record and not isinstance(record["research"], dict):
                issues.append(f"[{d}] {filename}: 'research' is not a dict")
                file_valid = False
            
            # Check critique is a dict
            if "critique" in record and not isinstance(record["critique"], dict):
                issues.append(f"[{d}] {filename}: 'critique' is not a dict")
                file_valid = False
            
            if file_valid:
                valid += 1
                d_valid += 1
            else:
                invalid += 1
                d_invalid += 1
        
        domain_stats[d] = {"valid": d_valid, "invalid": d_invalid, "warnings": d_warnings}
    
    return {
        "valid": valid,
        "invalid": invalid,
        "warnings": warnings,
        "issues": issues,
        "domain_stats": domain_stats,
    }


def validate_strategies() -> dict:
    """
    Validate all strategy files and meta consistency.
    
    Returns:
        {valid: int, invalid: int, warnings: int, issues: [str]}
    """
    if not os.path.exists(STRATEGY_DIR):
        return {"valid": 0, "invalid": 0, "warnings": 0, "issues": ["STRATEGY_DIR does not exist"]}
    
    valid = 0
    invalid = 0
    warnings = 0
    issues = []
    
    for domain in sorted(os.listdir(STRATEGY_DIR)):
        domain_dir = os.path.join(STRATEGY_DIR, domain)
        if not os.path.isdir(domain_dir):
            continue
        
        # Check meta file
        meta_path = os.path.join(domain_dir, "_meta.json")
        meta = None
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"[{domain}] _meta.json: Invalid JSON — {e}")
                invalid += 1
        else:
            issues.append(f"[{domain}] Missing _meta.json — no version tracking")
            warnings += 1
        
        # Validate strategy files
        for filename in sorted(os.listdir(domain_dir)):
            if not filename.endswith(".json") or filename.startswith("_"):
                continue
            
            filepath = os.path.join(domain_dir, filename)
            try:
                with open(filepath) as f:
                    record = json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"[{domain}] {filename}: Invalid JSON — {e}")
                invalid += 1
                continue
            
            file_valid = True
            for field in REQUIRED_STRATEGY_FIELDS:
                if field not in record:
                    issues.append(f"[{domain}] {filename}: Missing required field '{field}'")
                    file_valid = False
            
            # Check status is valid
            status = record.get("status", "")
            valid_statuses = ["pending", "trial", "active", "rolled_back", "rejected"]
            if status and status not in valid_statuses:
                issues.append(f"[{domain}] {filename}: Invalid status '{status}'")
                warnings += 1
            
            if file_valid:
                valid += 1
            else:
                invalid += 1
        
        # Cross-validate: active version in meta exists as a file
        if meta:
            for key, value in meta.items():
                if not key.endswith("_active"):
                    continue
                if not isinstance(value, str) or value == "default":
                    continue
                agent_role = key.replace("_active", "")
                expected_file = os.path.join(domain_dir, f"{agent_role}_{value}.json")
                if not os.path.exists(expected_file):
                    issues.append(f"[{domain}] Active version {agent_role}_{value} file not found")
                    warnings += 1
    
    return {"valid": valid, "invalid": invalid, "warnings": warnings, "issues": issues}


def validate_cost_log() -> dict:
    """
    Validate cost log integrity.
    
    Returns:
        {entries: int, invalid_lines: int, issues: [str],
         date_range: {first, last}, total_cost: float}
    """
    cost_log = os.path.join(LOG_DIR, "costs.jsonl")
    if not os.path.exists(cost_log):
        return {"entries": 0, "invalid_lines": 0, "issues": ["Cost log not found"]}
    
    entries = 0
    invalid_lines = 0
    issues = []
    total_cost = 0.0
    dates = []
    
    required_fields = ["timestamp", "date", "model", "agent_role", "estimated_cost_usd"]
    
    with open(cost_log) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"Line {line_num}: Invalid JSON")
                invalid_lines += 1
                continue
            
            entries += 1
            
            for field in required_fields:
                if field not in entry:
                    issues.append(f"Line {line_num}: Missing '{field}'")
            
            cost = entry.get("estimated_cost_usd", 0)
            if isinstance(cost, (int, float)):
                total_cost += cost
                if cost < 0:
                    issues.append(f"Line {line_num}: Negative cost: {cost}")
            
            date_str = entry.get("date", "")
            if date_str:
                dates.append(date_str)
    
    dates.sort()
    return {
        "entries": entries,
        "invalid_lines": invalid_lines,
        "issues": issues,
        "date_range": {"first": dates[0] if dates else None, "last": dates[-1] if dates else None},
        "total_cost": round(total_cost, 4),
    }


def validate_knowledge_graphs() -> dict:
    """
    Validate knowledge graph files across all domains.
    
    Checks:
    - JSON structure and required fields
    - Node/edge integrity (valid types, required sub-fields)
    - Edge references point to existing nodes
    - Metadata consistency (node_count matches actual nodes)
    
    Returns:
        {valid: int, invalid: int, warnings: int, issues: [str]}
    """
    valid = 0
    invalid = 0
    warnings = 0
    issues = []

    if not os.path.exists(MEMORY_DIR):
        return {"valid": 0, "invalid": 0, "warnings": 0, "issues": []}

    valid_node_types = {"claim", "topic", "source", "gap", "question"}
    valid_edge_types = {"supports", "contradicts", "supersedes", "relates_to",
                        "belongs_to", "sourced_from", "answers"}

    for d in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, d)
        if not os.path.isdir(domain_dir):
            continue
        graph_file = os.path.join(domain_dir, "_knowledge_graph.json")
        if not os.path.exists(graph_file):
            continue

        try:
            with open(graph_file) as f:
                graph = json.load(f)
        except json.JSONDecodeError as e:
            issues.append(f"[{d}] _knowledge_graph.json: Invalid JSON — {e}")
            invalid += 1
            continue

        file_valid = True

        # Check top-level structure
        for field in ["nodes", "edges", "metadata"]:
            if field not in graph:
                issues.append(f"[{d}] Graph missing '{field}'")
                file_valid = False

        if not file_valid:
            invalid += 1
            continue

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        metadata = graph.get("metadata", {})
        node_ids = {n.get("id") for n in nodes}

        # Validate metadata consistency
        if metadata.get("node_count", 0) != len(nodes):
            issues.append(f"[{d}] Graph node_count mismatch: "
                          f"meta={metadata.get('node_count')}, actual={len(nodes)}")
            warnings += 1

        if metadata.get("edge_count", 0) != len(edges):
            issues.append(f"[{d}] Graph edge_count mismatch: "
                          f"meta={metadata.get('edge_count')}, actual={len(edges)}")
            warnings += 1

        # Validate nodes
        for node in nodes:
            if "id" not in node or "type" not in node:
                issues.append(f"[{d}] Node missing id or type: {node}")
                file_valid = False
                continue
            if node["type"] not in valid_node_types:
                issues.append(f"[{d}] Node '{node['id']}' has invalid type: {node['type']}")
                warnings += 1

        # Validate edges
        orphan_edges = 0
        for edge in edges:
            if "source" not in edge or "target" not in edge or "type" not in edge:
                issues.append(f"[{d}] Edge missing required fields: {edge}")
                file_valid = False
                continue
            if edge["type"] not in valid_edge_types:
                issues.append(f"[{d}] Edge has invalid type: {edge['type']}")
                warnings += 1
            if edge["source"] not in node_ids:
                orphan_edges += 1
            if edge["target"] not in node_ids:
                orphan_edges += 1

        if orphan_edges > 0:
            issues.append(f"[{d}] Graph has {orphan_edges} edge reference(s) to non-existent nodes")
            warnings += 1

        if file_valid:
            valid += 1
        else:
            invalid += 1

    return {
        "valid": valid,
        "invalid": invalid,
        "warnings": warnings,
        "issues": issues,
    }


def validate_bootstrap() -> dict:
    """
    Validate bootstrap status files across all domains.

    Checks:
    - JSON structure and required fields
    - Phase is valid (in_progress, complete)
    - Bootstrap questions are present and non-empty
    """
    valid = 0
    invalid = 0
    warnings = 0
    issues = []

    if not os.path.exists(MEMORY_DIR):
        return {"valid": 0, "invalid": 0, "warnings": 0, "issues": []}

    for d in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, d)
        if not os.path.isdir(domain_dir):
            continue
        bs_file = os.path.join(domain_dir, "_bootstrap.json")
        if not os.path.exists(bs_file):
            continue

        try:
            with open(bs_file) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            issues.append(f"[{d}] _bootstrap.json: Invalid JSON — {e}")
            invalid += 1
            continue

        file_valid = True
        phase = data.get("phase")
        if phase not in ("in_progress", "complete", None):
            issues.append(f"[{d}] Bootstrap has unknown phase: {phase}")
            warnings += 1

        if phase == "in_progress" and not data.get("bootstrap_questions"):
            issues.append(f"[{d}] Bootstrap in_progress but no questions generated")
            warnings += 1

        if file_valid:
            valid += 1
        else:
            invalid += 1

    return {"valid": valid, "invalid": invalid, "warnings": warnings, "issues": issues}


def validate_calibration() -> dict:
    """
    Validate the calibration data file.

    Checks:
    - JSON structure
    - Domain entries have required stats
    - Stats are within valid ranges
    """
    from config import CALIBRATION_FILE
    issues = []
    warnings = 0

    if not os.path.exists(CALIBRATION_FILE):
        return {"valid": False, "warnings": 0, "issues": ["Calibration file not found (normal if no cycles run)"]}

    try:
        with open(CALIBRATION_FILE) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {"valid": False, "warnings": 0, "issues": [f"Calibration file invalid JSON: {e}"]}

    domains = data.get("domains", {})
    for d, entry in domains.items():
        if "mean" not in entry or "count" not in entry:
            issues.append(f"[{d}] Calibration entry missing mean or count")
            continue
        if not (0 <= entry.get("mean", 0) <= 10):
            issues.append(f"[{d}] Calibration mean out of range: {entry['mean']}")
            warnings += 1
        if entry.get("accept_rate", 0) < 0 or entry.get("accept_rate", 0) > 1:
            issues.append(f"[{d}] Accept rate out of range: {entry['accept_rate']}")
            warnings += 1

    return {
        "valid": len(issues) == 0,
        "domains_tracked": len(domains),
        "warnings": warnings,
        "issues": issues,
    }


def validate_claim_verification() -> dict:
    """
    Validate claim verification state across knowledge bases.

    Checks:
    - _last_verified timestamps are parseable
    - _verification_verdict is a valid value
    - disputed claims have notes explaining why
    """
    issues = []
    warnings = 0
    domains_checked = 0

    if not os.path.exists(MEMORY_DIR):
        return {"domains_checked": 0, "warnings": 0, "issues": []}

    valid_verdicts = {"confirmed", "refuted", "weakened", "inconclusive"}

    for d in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, d)
        if not os.path.isdir(domain_dir):
            continue
        kb_path = os.path.join(domain_dir, "_knowledge_base.json")
        if not os.path.exists(kb_path):
            continue

        try:
            with open(kb_path) as f:
                kb = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        domains_checked += 1
        for claim in kb.get("claims", []):
            lv = claim.get("_last_verified")
            if lv:
                try:
                    datetime.fromisoformat(lv)
                except (ValueError, TypeError):
                    issues.append(f"[{d}] Claim '{claim.get('id', '?')}': "
                                  f"invalid _last_verified timestamp: {lv}")
                    warnings += 1

            verdict = claim.get("_verification_verdict")
            if verdict and verdict not in valid_verdicts:
                issues.append(f"[{d}] Claim '{claim.get('id', '?')}': "
                              f"invalid verification verdict: {verdict}")
                warnings += 1

            if claim.get("status") == "disputed" and not claim.get("notes"):
                issues.append(f"[{d}] Claim '{claim.get('id', '?')}': "
                              f"disputed but no explanation in notes")
                warnings += 1

    return {
        "domains_checked": domains_checked,
        "warnings": warnings,
        "issues": issues,
    }


def check_readiness() -> dict:
    """
    Check if the system is ready to run cycles.

    Verifies:
    - Required directories exist
    - API key is configured
    - Config is internally consistent
    - No critical data corruption
    """
    ready = True
    checks = []

    # Directories
    for name, path in [("MEMORY_DIR", MEMORY_DIR), ("STRATEGY_DIR", STRATEGY_DIR), ("LOG_DIR", LOG_DIR)]:
        if os.path.exists(path):
            checks.append({"check": name, "status": "ok"})
        else:
            checks.append({"check": name, "status": "missing", "detail": f"{path} does not exist"})

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key and api_key.startswith("sk-or-"):
        checks.append({"check": "OPENROUTER_API_KEY", "status": "ok"})
    elif api_key:
        checks.append({"check": "OPENROUTER_API_KEY", "status": "warning", "detail": "Key set but format unusual"})
    else:
        checks.append({"check": "OPENROUTER_API_KEY", "status": "missing"})
        ready = False

    # .env file
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        checks.append({"check": ".env file", "status": "ok"})
    else:
        checks.append({"check": ".env file", "status": "missing",
                       "detail": "Copy .env.example to .env and configure"})
        ready = False

    # Budget
    try:
        from config import DAILY_BUDGET_USD, TOTAL_BALANCE_USD
        if DAILY_BUDGET_USD > 0:
            checks.append({"check": "budget", "status": "ok",
                          "detail": f"${DAILY_BUDGET_USD:.2f}/day, ${TOTAL_BALANCE_USD:.2f} balance"})
        else:
            checks.append({"check": "budget", "status": "warning", "detail": "Zero budget"})
    except Exception as e:
        checks.append({"check": "budget", "status": "error", "detail": str(e)})

    # Data integrity (quick check)
    mem_result = validate_memory()
    if mem_result["invalid"] == 0:
        checks.append({"check": "memory_integrity", "status": "ok",
                       "detail": f"{mem_result['valid']} valid files"})
    else:
        checks.append({"check": "memory_integrity", "status": "warning",
                       "detail": f"{mem_result['invalid']} invalid files"})

    return {
        "ready": ready,
        "checks": checks,
        "failed": [c for c in checks if c["status"] in ("missing", "error")],
        "warnings": [c for c in checks if c["status"] == "warning"],
    }


def validate_all() -> dict:
    """
    Run all validation checks and return comprehensive report.
    """
    memory = validate_memory()
    strategies = validate_strategies()
    costs = validate_cost_log()
    graphs = validate_knowledge_graphs()
    bootstrap = validate_bootstrap()
    calibration = validate_calibration()
    claim_verification = validate_claim_verification()

    all_issues = (memory["issues"] + strategies["issues"] + costs["issues"]
                  + graphs["issues"] + bootstrap["issues"]
                  + calibration["issues"] + claim_verification["issues"])

    total_valid = memory["valid"] + strategies["valid"] + costs["entries"] + graphs["valid"] + bootstrap["valid"]
    total_invalid = memory["invalid"] + strategies["invalid"] + costs["invalid_lines"] + graphs["invalid"] + bootstrap["invalid"]
    total_warnings = (memory["warnings"] + strategies["warnings"] + graphs["warnings"]
                      + bootstrap["warnings"] + calibration["warnings"]
                      + claim_verification["warnings"])

    if total_invalid == 0 and total_warnings == 0:
        status = "HEALTHY"
    elif total_invalid == 0:
        status = "WARNINGS"
    else:
        status = "ISSUES FOUND"

    return {
        "status": status,
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "total_warnings": total_warnings,
        "total_issues": len(all_issues),
        "memory": memory,
        "strategies": strategies,
        "costs": costs,
        "graphs": graphs,
        "bootstrap": bootstrap,
        "calibration": calibration,
        "claim_verification": claim_verification,
    }


def display_validation():
    """Print formatted validation results."""
    result = validate_all()

    status_icon = {"HEALTHY": "✓", "WARNINGS": "⚠", "ISSUES FOUND": "✗"}.get(result["status"], "?")

    print(f"\n{'='*60}")
    print(f"  DATA VALIDATION — {status_icon} {result['status']}")
    print(f"{'='*60}")

    print(f"\n  Valid records: {result['total_valid']}")
    print(f"  Invalid records: {result['total_invalid']}")
    print(f"  Warnings: {result['total_warnings']}")

    # Memory
    mem = result["memory"]
    print(f"\n  ── Memory ({mem['valid']} valid, {mem['invalid']} invalid, {mem['warnings']} warnings) ──")
    if mem["domain_stats"]:
        for d, stats in mem["domain_stats"].items():
            status_mark = "✓" if stats["invalid"] == 0 else "✗"
            print(f"    {status_mark} {d}: {stats['valid']} valid, {stats['invalid']} invalid, {stats['warnings']} warnings")
    if not mem["issues"]:
        print(f"    All memory files valid.")

    # Strategies
    strat = result["strategies"]
    print(f"\n  ── Strategies ({strat['valid']} valid, {strat['invalid']} invalid) ──")
    if not strat["issues"]:
        print(f"    All strategy files valid.")

    # Costs
    costs = result["costs"]
    print(f"\n  ── Cost Log ({costs['entries']} entries, {costs['invalid_lines']} invalid) ──")
    if costs.get("date_range", {}).get("first"):
        print(f"    Date range: {costs['date_range']['first']} → {costs['date_range']['last']}")
    print(f"    Total logged cost: ${costs['total_cost']:.4f}")
    if not costs["issues"]:
        print(f"    Cost log valid.")

    # Knowledge Graphs
    graphs = result.get("graphs", {})
    if graphs.get("valid", 0) + graphs.get("invalid", 0) > 0:
        print(f"\n  ── Knowledge Graphs ({graphs['valid']} valid, {graphs['invalid']} invalid, {graphs['warnings']} warnings) ──")
        if not graphs["issues"]:
            print(f"    All knowledge graphs valid.")

    # Bootstrap
    bootstrap = result.get("bootstrap", {})
    bs_total = bootstrap.get("valid", 0) + bootstrap.get("invalid", 0)
    if bs_total > 0:
        print(f"\n  ── Bootstrap ({bootstrap['valid']} valid, {bootstrap['invalid']} invalid) ──")
        if not bootstrap["issues"]:
            print(f"    All bootstrap files valid.")

    # Calibration
    cal = result.get("calibration", {})
    if cal.get("valid") is not None:
        icon = "✓" if cal["valid"] else "⚠"
        domains_n = cal.get("domains_tracked", 0)
        print(f"\n  ── Calibration {icon} ({domains_n} domains tracked) ──")
        if not cal.get("issues"):
            print(f"    Calibration data valid.")

    # Claim verification
    cv = result.get("claim_verification", {})
    if cv.get("domains_checked", 0) > 0:
        print(f"\n  ── Claim Verification ({cv['domains_checked']} domains checked) ──")
        if not cv["issues"]:
            print(f"    All verification data valid.")

    # Show issues
    all_issues = []
    for section in [mem, strat, costs, graphs, bootstrap, cal, cv]:
        all_issues.extend(section.get("issues", []))
    if all_issues:
        print(f"\n  ── Issues ({len(all_issues)}) ──")
        for i, issue in enumerate(all_issues[:20], 1):
            print(f"    {i}. {issue}")
        if len(all_issues) > 20:
            print(f"    ... and {len(all_issues) - 20} more")

    print()


def display_readiness():
    """Print formatted readiness check results."""
    result = check_readiness()

    icon = "✓" if result["ready"] else "✗"
    print(f"\n{'='*60}")
    print(f"  READINESS CHECK — {icon} {'READY' if result['ready'] else 'NOT READY'}")
    print(f"{'='*60}")

    for check in result["checks"]:
        status_icon = {"ok": "✓", "warning": "⚠", "missing": "✗", "error": "✗"}.get(check["status"], "?")
        detail = f" — {check['detail']}" if check.get("detail") else ""
        print(f"  {status_icon} {check['check']}{detail}")

    if not result["ready"]:
        print(f"\n  Fix the above issues before running cycles.")
    print()
