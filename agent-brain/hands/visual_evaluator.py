"""
Visual Evaluator — Claude Vision scores what Hands built.

Takes a screenshot (base64 PNG) and evaluates it against the design standard.
Returns structured feedback: score, issues, and fixes.

This is the "eyes" of the system — without it, Hands builds blind.

Usage:
    from hands.visual_evaluator import evaluate_screenshot, evaluate_with_reference
    
    # Basic evaluation
    result = evaluate_screenshot(base64_image, context="Landing page for logistics company")
    # result = {"score": 7, "issues": [...], "strengths": [...], "fixes": [...]}
    
    # With reference comparison
    result = evaluate_with_reference(base64_image, reference_b64, context="...")
    # result = {"score": 6, "gaps": [...], "fixes": [...]}

Model: Uses Claude Sonnet (PREMIUM_MODEL) — visual quality is sacred.
Cost: ~$0.01-0.02 per evaluation (image + text response).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import MODELS, ANTHROPIC_API_KEY, LOG_DIR
from cost_tracker import log_cost

# Visual score thresholds
VISUAL_ACCEPT_THRESHOLD = 8      # Score ≥ 8: accept as-is
VISUAL_FIX_THRESHOLD = 5         # Score 5-7: fix pass needed
MAX_VISUAL_FIX_ROUNDS = 2        # Max fix iterations per component group
SCREENSHOT_LOG_DIR = os.path.join(LOG_DIR, "screenshots")


def _get_identity_file(filename: str, max_chars: int = 4000) -> str:
    """Load an identity file by name, truncated to max_chars."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "identity", filename)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read()[:max_chars]
        except OSError:
            pass
    return ""


def _get_design_system() -> str:
    """Load the design system prompt for visual evaluation context."""
    return _get_identity_file("design_system.md")


def _get_marketing_design() -> str:
    """Load the marketing page design standard."""
    return _get_identity_file("marketing_design.md")


def _get_scoring_rubric() -> str:
    """Load the visual scoring calibration rubric."""
    return _get_identity_file("visual_scoring_rubric.md", max_chars=3000)


def _build_eval_system(page_type: str = "app") -> str:
    """Build the system prompt for visual evaluation."""
    design = _get_marketing_design() if page_type == "marketing" else _get_design_system()
    rubric = _get_scoring_rubric()
    
    design_block = ""
    if design:
        label = "MARKETING DESIGN STANDARD" if page_type == "marketing" else "DESIGN STANDARD"
        design_block = f"""

=== {label} ===
{design}
=== END {label} ===
"""

    rubric_block = ""
    if rubric:
        rubric_block = f"""

=== SCORING CALIBRATION ===
{rubric}
=== END SCORING CALIBRATION ===
"""
    
    return f"""\
You are a senior UI/UX designer and front-end engineer reviewing a web page screenshot.
You evaluate visual quality, design consistency, and production-readiness.

Your evaluation is structured and specific — not vague praise or generic criticism.
Every issue you identify must be actionable (a developer can fix it in one step).
{design_block}{rubric_block}
SCORING RUBRIC (1-10):
  10: Exceptional — could ship to paying customers today. Looks designed by a top agency.
  8-9: Production-ready — clean, consistent, professional. Minor polish items only.
  6-7: Decent — functional but has noticeable visual issues. Needs one fix pass.
  4-5: Below average — multiple visual problems, inconsistent spacing/typography.
  1-3: Broken — layout issues, missing styles, clearly unfinished.

EVALUATION DIMENSIONS:
  1. Layout & Spacing — Grid consistency, padding, margins, alignment
  2. Typography — Font hierarchy, readability, weight contrast
  3. Color & Contrast — Palette consistency, accessibility, dark/light balance
  4. Components — Button styles, form fields, cards, navigation
  5. Responsiveness — Content fits viewport, no overflow/cutoff
  6. Polish — Hover states, transitions, empty states, loading states
  7. Overall Impression — Does this look like a real product or a prototype?

RESPOND IN THIS EXACT JSON FORMAT:
{{
  "score": <1-10>,
  "dimensions": {{
    "layout": <1-10>,
    "typography": <1-10>,
    "color": <1-10>,
    "components": <1-10>,
    "responsiveness": <1-10>,
    "polish": <1-10>
  }},
  "strengths": ["<specific good thing>", ...],
  "issues": [
    {{"severity": "critical|major|minor", "description": "<specific problem>", "fix": "<exact CSS/component fix>"}},
    ...
  ],
  "overall_impression": "<1-2 sentence summary>"
}}

Be ruthlessly honest. A 7 is not a compliment — it means "needs work." Give 9+ only to genuinely excellent pages."""


def evaluate_screenshot(
    base64_image: str,
    context: str = "",
    page_type: str = "app",
    viewport: str = "desktop",
) -> dict:
    """
    Evaluate a screenshot using Claude Vision.
    
    Args:
        base64_image: Base64-encoded PNG screenshot
        context: What this page is (e.g., "Landing page for a logistics SaaS")
        page_type: "app" or "marketing" — selects the design standard
        viewport: "desktop" or "mobile" — for evaluation context
    
    Returns:
        {
            "score": int (1-10),
            "dimensions": {"layout": int, ...},
            "strengths": [str, ...],
            "issues": [{"severity": str, "description": str, "fix": str}, ...],
            "overall_impression": str,
            "cost": float,
        }
    """
    from anthropic import Anthropic
    
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    model = MODELS.get("critic", "claude-sonnet-4-20250514")
    system = _build_eval_system(page_type)
    
    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64_image,
            },
        },
        {
            "type": "text",
            "text": _build_eval_prompt(context, viewport),
        },
    ]
    
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        
        # Log cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000  # Sonnet pricing
        log_cost("visual_evaluator", model, cost, input_tokens, output_tokens)
        
        # Parse response
        text = response.content[0].text if response.content else ""
        result = _parse_eval_response(text)
        result["cost"] = cost
        result["raw_response"] = text[:2000]
        
        return result
    
    except Exception as e:
        return {
            "score": 0,
            "dimensions": {},
            "strengths": [],
            "issues": [{"severity": "critical", "description": f"Evaluation failed: {e}", "fix": ""}],
            "overall_impression": f"Evaluation error: {e}",
            "cost": 0.0,
            "error": str(e),
        }


def evaluate_with_reference(
    base64_image: str,
    reference_base64: str,
    context: str = "",
    page_type: str = "marketing",
) -> dict:
    """
    Compare a screenshot against a reference image.
    
    Used for Task 4.4: Brain's research includes competitor screenshots.
    Claude vision compares current build vs reference and identifies gaps.
    
    Args:
        base64_image: The page we built (base64 PNG)
        reference_base64: The reference/competitor page (base64 PNG)
        context: Description of what we're comparing
        page_type: "app" or "marketing"
    
    Returns:
        {
            "score": int (1-10),
            "gaps": [{"area": str, "description": str, "fix": str}, ...],
            "matches": [str, ...],  # Things we do as well or better
            "overall_impression": str,
            "cost": float,
        }
    """
    from anthropic import Anthropic
    
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    model = MODELS.get("critic", "claude-sonnet-4-20250514")
    
    system = """\
You are a senior UI designer comparing two web page screenshots.
Image 1 is the page we built. Image 2 is a reference/competitor page.
Your job is to identify specific visual gaps between our page and the reference,
and provide actionable fixes to close those gaps.

RESPOND IN THIS EXACT JSON FORMAT:
{
  "score": <1-10, how close we are to the reference quality>,
  "gaps": [
    {"area": "<layout|typography|color|components|content|animation>", "description": "<specific gap>", "fix": "<exact fix>"},
    ...
  ],
  "matches": ["<thing we do as well or better than reference>", ...],
  "overall_impression": "<1-2 sentence comparison summary>"
}

Be specific. "Our hero section needs more whitespace" is good. "Could be better" is not."""
    
    user_content = [
        {
            "type": "text",
            "text": f"Compare these two pages. Image 1 is our build. Image 2 is the reference.\nContext: {context or 'Web page comparison'}",
        },
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64_image},
        },
        {
            "type": "text",
            "text": "Reference page (target aesthetic):",
        },
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": reference_base64},
        },
    ]
    
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000
        log_cost("visual_evaluator_reference", model, cost, input_tokens, output_tokens)
        
        text = response.content[0].text if response.content else ""
        result = _parse_reference_response(text)
        result["cost"] = cost
        
        return result
    
    except Exception as e:
        return {
            "score": 0,
            "gaps": [{"area": "error", "description": str(e), "fix": ""}],
            "matches": [],
            "overall_impression": f"Reference comparison failed: {e}",
            "cost": 0.0,
            "error": str(e),
        }


def generate_fix_instructions(issues: list[dict]) -> str:
    """
    Convert visual evaluation issues into concrete fix instructions
    that the executor can follow.
    
    Args:
        issues: List of issue dicts from evaluate_screenshot()
    
    Returns:
        Formatted instruction string for the executor
    """
    if not issues:
        return ""
    
    # Sort by severity: critical > major > minor
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    sorted_issues = sorted(issues, key=lambda x: severity_order.get(x.get("severity", "minor"), 3))
    
    lines = ["VISUAL FIX INSTRUCTIONS (fix these specific issues):\n"]
    
    for i, issue in enumerate(sorted_issues, 1):
        severity = issue.get("severity", "minor").upper()
        desc = issue.get("description", "Unknown issue")
        fix = issue.get("fix", "")
        
        lines.append(f"  {i}. [{severity}] {desc}")
        if fix:
            lines.append(f"     FIX: {fix}")
    
    lines.append("\nFix all critical and major issues. Minor issues are optional if time-constrained.")
    
    return "\n".join(lines)


def save_screenshot_log(
    domain: str,
    task_id: str,
    phase: str,
    base64_image: str,
    evaluation: dict,
    iteration: int = 0,
) -> str:
    """
    Save a screenshot and its evaluation to disk for audit trail.
    
    Returns the saved file path.
    """
    import base64 as b64_module
    
    screenshot_dir = os.path.join(SCREENSHOT_LOG_DIR, domain)
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Save the image
    filename = f"{task_id}_{phase}_iter{iteration}.png"
    img_path = os.path.join(screenshot_dir, filename)
    
    try:
        img_bytes = b64_module.b64decode(base64_image)
        with open(img_path, "wb") as f:
            f.write(img_bytes)
    except Exception:
        img_path = ""
    
    # Save the evaluation as JSON
    eval_path = os.path.join(screenshot_dir, f"{task_id}_{phase}_iter{iteration}_eval.json")
    try:
        # Don't include raw base64 in eval JSON
        eval_data = {k: v for k, v in evaluation.items() if k != "raw_response"}
        eval_data["screenshot_path"] = img_path
        eval_data["phase"] = phase
        eval_data["iteration"] = iteration
        
        from utils.atomic_write import atomic_json_write
        atomic_json_write(eval_path, eval_data)
    except Exception:
        pass
    
    return img_path


def store_visual_score(
    domain: str,
    task_id: str,
    evaluation: dict,
    page_type: str = "app",
) -> str | None:
    """
    Store a visual evaluation score for strategy evolution.

    Visual scores are stored per-domain in a JSONL log that the meta-analyst
    can read to identify patterns and propose design system improvements.

    Args:
        domain: The project domain (e.g., "logistics-saas")
        task_id: Unique task/build identifier
        evaluation: Result dict from evaluate_screenshot() or evaluate_with_reference()
        page_type: "app" or "marketing"

    Returns:
        Path to the scores file, or None on error.
    """
    from datetime import datetime, timezone
    from utils.atomic_write import atomic_json_write

    scores_dir = os.path.join(LOG_DIR, "visual_scores")
    os.makedirs(scores_dir, exist_ok=True)
    scores_path = os.path.join(scores_dir, f"{domain}.jsonl")

    record = {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "page_type": page_type,
        "score": evaluation.get("score", 0),
        "dimensions": evaluation.get("dimensions", {}),
        "issue_count": len(evaluation.get("issues", [])),
        "critical_issues": sum(
            1 for i in evaluation.get("issues", [])
            if i.get("severity") == "critical"
        ),
        "major_issues": sum(
            1 for i in evaluation.get("issues", [])
            if i.get("severity") == "major"
        ),
    }

    try:
        with open(scores_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return scores_path
    except OSError:
        return None


def load_visual_scores(domain: str, last_n: int = 20) -> list[dict]:
    """
    Load recent visual scores for a domain.

    Used by the meta-analyst to track visual quality trends and decide
    whether the design system prompts need evolution.

    Args:
        domain: The project domain
        last_n: How many recent scores to return

    Returns:
        List of score records (most recent last).
    """
    scores_path = os.path.join(LOG_DIR, "visual_scores", f"{domain}.jsonl")
    if not os.path.exists(scores_path):
        return []

    records = []
    try:
        with open(scores_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []

    return records[-last_n:]


def get_visual_score_summary(domain: str) -> dict:
    """
    Compute summary statistics for visual scores in a domain.

    Used by the meta-analyst / strategy evolution to decide if
    design system prompts need updating.

    Returns:
        {
            "count": int,
            "avg_score": float,
            "min_score": int,
            "max_score": int,
            "avg_dimensions": {"layout": float, ...},
            "trend": "improving" | "stable" | "declining",
            "common_issues": int (total critical+major across recent builds),
        }
    """
    scores = load_visual_scores(domain, last_n=20)
    if not scores:
        return {"count": 0, "avg_score": 0.0, "trend": "no_data"}

    overall_scores = [s["score"] for s in scores if s.get("score")]
    if not overall_scores:
        return {"count": len(scores), "avg_score": 0.0, "trend": "no_data"}

    # Compute dimension averages
    dim_sums: dict[str, list[float]] = {}
    for s in scores:
        for dim, val in s.get("dimensions", {}).items():
            if dim not in dim_sums:
                dim_sums[dim] = []
            dim_sums[dim].append(float(val))

    avg_dims = {dim: round(sum(vals) / len(vals), 1) for dim, vals in dim_sums.items()}

    # Trend: compare first half vs second half
    mid = len(overall_scores) // 2
    if mid >= 2:
        first_half = sum(overall_scores[:mid]) / mid
        second_half = sum(overall_scores[mid:]) / (len(overall_scores) - mid)
        if second_half > first_half + 0.3:
            trend = "improving"
        elif second_half < first_half - 0.3:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    total_critical = sum(s.get("critical_issues", 0) for s in scores)
    total_major = sum(s.get("major_issues", 0) for s in scores)

    return {
        "count": len(scores),
        "avg_score": round(sum(overall_scores) / len(overall_scores), 1),
        "min_score": min(overall_scores),
        "max_score": max(overall_scores),
        "avg_dimensions": avg_dims,
        "trend": trend,
        "common_issues": total_critical + total_major,
    }


# ── Internal helpers ─────────────────────────────────────────────────────

def _build_eval_prompt(context: str, viewport: str) -> str:
    """Build the user prompt for evaluation."""
    parts = ["Evaluate this web page screenshot."]
    
    if context:
        parts.append(f"Context: {context}")
    
    parts.append(f"Viewport: {viewport}")
    parts.append("Provide your evaluation in the specified JSON format.")
    
    return "\n".join(parts)


def _parse_eval_response(text: str) -> dict:
    """Parse Claude's evaluation response into structured dict."""
    # Try to extract JSON from response
    try:
        # Find JSON block (may be wrapped in markdown code fences)
        json_str = text
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            json_str = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            json_str = text[start:end].strip()
        elif "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            json_str = text[start:end]
        
        result = json.loads(json_str)
        
        # Validate expected fields
        return {
            "score": int(result.get("score", 0)),
            "dimensions": result.get("dimensions", {}),
            "strengths": result.get("strengths", []),
            "issues": result.get("issues", []),
            "overall_impression": result.get("overall_impression", ""),
        }
    except (json.JSONDecodeError, ValueError, IndexError):
        # Fallback: try to extract score from text
        score = 0
        import re
        score_match = re.search(r'"score"\s*:\s*(\d+)', text)
        if score_match:
            score = int(score_match.group(1))
        
        return {
            "score": score,
            "dimensions": {},
            "strengths": [],
            "issues": [{"severity": "major", "description": "Could not parse evaluation response", "fix": ""}],
            "overall_impression": text[:500] if text else "No response",
        }


def _parse_reference_response(text: str) -> dict:
    """Parse Claude's reference comparison response."""
    try:
        json_str = text
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            json_str = text[start:end].strip()
        elif "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            json_str = text[start:end]
        
        result = json.loads(json_str)
        
        return {
            "score": int(result.get("score", 0)),
            "gaps": result.get("gaps", []),
            "matches": result.get("matches", []),
            "overall_impression": result.get("overall_impression", ""),
        }
    except (json.JSONDecodeError, ValueError, IndexError):
        return {
            "score": 0,
            "gaps": [],
            "matches": [],
            "overall_impression": text[:500] if text else "No response",
        }
