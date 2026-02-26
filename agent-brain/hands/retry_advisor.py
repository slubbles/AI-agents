"""
Retry Strategy Advisor — Classifies failures and recommends optimal retry strategy.

Problem: The current cascade (file_repair → surgical → full_replan) always starts
at the cheapest strategy and escalates. This wastes API calls when the failure type
clearly requires a specific strategy. E.g., a fundamental misunderstanding of the
task always needs a full replan — trying file_repair first is futile.

Solution: Classify failure severity from validation results and route directly
to the most appropriate retry strategy.

Failure Classes:
  - cosmetic (score 5.5-6.9): Minor issues like formatting, naming, comments.
    → File repair can fix these. Skip surgical/replan.
  - structural (score 3.0-5.4): Wrong logic, broken integration, missing features.
    → Surgical retry on failing steps. File repair won't help.
  - fundamental (score < 3.0): Task misunderstood, wrong architecture, everything broken.
    → Full replan required. Skip repair and surgical.
  - mixed: Some files cosmetic, some structural.
    → File repair on cosmetic files + surgical on structural steps.

Used by: main.py quality gate (replaces blind cascade)
"""

from __future__ import annotations

# ── Failure severity thresholds ──────────────────────────────────────
COSMETIC_FLOOR = 5.5     # Score 5.5-6.9 = cosmetic issues
STRUCTURAL_FLOOR = 3.0   # Score 3.0-5.4 = structural issues
# Below 3.0 = fundamental failure

# ── Dimension weights for severity classification ────────────────────
# Issues in these dimensions indicate structural vs cosmetic problems
_STRUCTURAL_DIMS = {"correctness", "completeness"}
_COSMETIC_DIMS = {"code_quality", "kb_alignment", "security"}


class FailureClass:
    """Enum-like class for failure classifications."""
    COSMETIC = "cosmetic"
    STRUCTURAL = "structural"
    FUNDAMENTAL = "fundamental"
    MIXED = "mixed"


class RetryRecommendation:
    """Retry strategy recommendation with reasoning."""
    
    FILE_REPAIR = "file_repair"
    SURGICAL = "surgical"
    FULL_REPLAN = "full_replan"
    SKIP_RETRY = "skip_retry"  # Don't retry — failure is too fundamental + no retries left

    def __init__(
        self,
        strategy: str,
        failure_class: str,
        confidence: float,
        reason: str,
        skip_strategies: list[str] | None = None,
    ):
        self.strategy = strategy
        self.failure_class = failure_class
        self.confidence = confidence  # 0.0-1.0
        self.reason = reason
        self.skip_strategies = skip_strategies or []

    def __repr__(self) -> str:
        return f"RetryRecommendation(strategy={self.strategy!r}, class={self.failure_class!r}, confidence={self.confidence:.2f})"

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "failure_class": self.failure_class,
            "confidence": self.confidence,
            "reason": self.reason,
            "skip_strategies": self.skip_strategies,
        }


def classify_failure(validation: dict) -> str:
    """
    Classify the failure type from validation results.
    
    Args:
        validation: Dict from validate_execution() with:
            - overall_score: float
            - dimension_scores: dict[str, float] (optional)
            - critical_issues: list[str] (optional)
            - weaknesses: list[str] (optional)
            - fast_rejected: bool (optional)
    
    Returns:
        FailureClass constant
    """
    score = validation.get("overall_score", 0)
    
    # Fast-rejected files have fundamental issues (won't even compile/parse)
    if validation.get("fast_rejected"):
        return FailureClass.FUNDAMENTAL
    
    # Very low score = fundamental
    if score < STRUCTURAL_FLOOR:
        return FailureClass.FUNDAMENTAL
    
    # Check dimension breakdown if available
    dims = validation.get("dimension_scores", {})
    if dims:
        structural_scores = [
            dims[d] for d in _STRUCTURAL_DIMS if d in dims
        ]
        cosmetic_scores = [
            dims[d] for d in _COSMETIC_DIMS if d in dims
        ]
        
        structural_avg = (
            sum(structural_scores) / len(structural_scores)
            if structural_scores else score
        )
        cosmetic_avg = (
            sum(cosmetic_scores) / len(cosmetic_scores)
            if cosmetic_scores else score
        )
        
        # If structural dimensions are fine but cosmetic are low → cosmetic
        if structural_avg >= 7.0 and cosmetic_avg < 7.0:
            return FailureClass.COSMETIC
        
        # If structural dimensions are low but cosmetic are fine → structural
        if structural_avg < 5.5 and cosmetic_avg >= 6.0:
            return FailureClass.STRUCTURAL
        
        # Mixed: both have issues at different severity levels
        if structural_avg < 6.5 and cosmetic_avg < 6.0:
            return FailureClass.MIXED
    
    # No dimension breakdown — use overall score
    if score >= COSMETIC_FLOOR:
        return FailureClass.COSMETIC
    elif score >= STRUCTURAL_FLOOR:
        return FailureClass.STRUCTURAL
    else:
        return FailureClass.FUNDAMENTAL


def recommend_strategy(
    validation: dict,
    attempt: int,
    max_retries: int,
    has_weak_artifacts: bool = False,
    has_failing_steps: bool = False,
) -> RetryRecommendation:
    """
    Recommend the best retry strategy based on failure classification.
    
    Args:
        validation: Validation results dict
        attempt: Current attempt number (1-based)
        max_retries: Maximum retries allowed
        has_weak_artifacts: Whether file_repair identified fixable artifacts
        has_failing_steps: Whether surgical retry identified failing steps
    
    Returns:
        RetryRecommendation with strategy, confidence, and reasoning
    """
    failure_class = classify_failure(validation)
    score = validation.get("overall_score", 0)
    retries_left = max_retries - attempt
    
    # ── Fundamental failures ─────────────────────────────────────
    if failure_class == FailureClass.FUNDAMENTAL:
        if retries_left <= 0:
            return RetryRecommendation(
                strategy=RetryRecommendation.SKIP_RETRY,
                failure_class=failure_class,
                confidence=0.9,
                reason=f"Fundamental failure (score={score:.1f}) with no retries left",
                skip_strategies=[RetryRecommendation.FILE_REPAIR, RetryRecommendation.SURGICAL],
            )
        return RetryRecommendation(
            strategy=RetryRecommendation.FULL_REPLAN,
            failure_class=failure_class,
            confidence=0.9,
            reason=f"Fundamental failure (score={score:.1f}) requires complete replan",
            skip_strategies=[RetryRecommendation.FILE_REPAIR, RetryRecommendation.SURGICAL],
        )
    
    # ── Cosmetic failures ────────────────────────────────────────
    if failure_class == FailureClass.COSMETIC:
        if has_weak_artifacts:
            return RetryRecommendation(
                strategy=RetryRecommendation.FILE_REPAIR,
                failure_class=failure_class,
                confidence=0.85,
                reason=f"Cosmetic issues (score={score:.1f}) with identifiable weak files",
                skip_strategies=[RetryRecommendation.FULL_REPLAN],
            )
        # Cosmetic but no specific weak artifacts — try surgical if possible
        if has_failing_steps:
            return RetryRecommendation(
                strategy=RetryRecommendation.SURGICAL,
                failure_class=failure_class,
                confidence=0.6,
                reason=f"Cosmetic issues (score={score:.1f}) but no specific weak files; trying surgical",
            )
        # Fall back to file repair anyway — it's cheap
        return RetryRecommendation(
            strategy=RetryRecommendation.FILE_REPAIR,
            failure_class=failure_class,
            confidence=0.5,
            reason=f"Cosmetic issues (score={score:.1f}) without clear targets; trying cheap repair first",
        )
    
    # ── Structural failures ──────────────────────────────────────
    if failure_class == FailureClass.STRUCTURAL:
        if has_failing_steps:
            return RetryRecommendation(
                strategy=RetryRecommendation.SURGICAL,
                failure_class=failure_class,
                confidence=0.8,
                reason=f"Structural issues (score={score:.1f}) with identifiable failing steps",
                skip_strategies=[RetryRecommendation.FILE_REPAIR],
            )
        # No clear failing steps — full replan
        if retries_left > 0:
            return RetryRecommendation(
                strategy=RetryRecommendation.FULL_REPLAN,
                failure_class=failure_class,
                confidence=0.7,
                reason=f"Structural issues (score={score:.1f}) without clear failing steps",
                skip_strategies=[RetryRecommendation.FILE_REPAIR],
            )
        return RetryRecommendation(
            strategy=RetryRecommendation.SKIP_RETRY,
            failure_class=failure_class,
            confidence=0.7,
            reason=f"Structural issues (score={score:.1f}) with no retries left",
        )
    
    # ── Mixed failures ───────────────────────────────────────────
    # Mixed: try file repair for cosmetic issues, then surgical for structural
    if has_weak_artifacts:
        return RetryRecommendation(
            strategy=RetryRecommendation.FILE_REPAIR,
            failure_class=failure_class,
            confidence=0.6,
            reason=f"Mixed issues (score={score:.1f}): repair cosmetic files first, then retry structural",
        )
    if has_failing_steps:
        return RetryRecommendation(
            strategy=RetryRecommendation.SURGICAL,
            failure_class=failure_class,
            confidence=0.6,
            reason=f"Mixed issues (score={score:.1f}): surgical retry on failing steps",
        )
    return RetryRecommendation(
        strategy=RetryRecommendation.FULL_REPLAN,
        failure_class=failure_class,
        confidence=0.5,
        reason=f"Mixed issues (score={score:.1f}): no clear targets, full replan",
    )


def should_skip_strategy(recommendation: RetryRecommendation, strategy: str) -> bool:
    """Check if a specific strategy should be skipped based on the recommendation."""
    return strategy in recommendation.skip_strategies
