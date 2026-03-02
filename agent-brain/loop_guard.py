"""
Loop Guard — Real-time protection for auto mode.

Detects problems DURING execution (not post-hoc like monitoring.py):
- Repeated/similar questions across rounds (brain is looping)
- Consecutive failures (stuck in a bad state)
- Runaway cost mid-run (spending too fast)
- Score regression (getting worse, not better)
- Same-error repetition (hitting the same wall)

Pure logic — no LLM calls. This is the watchdog.

Usage:
    guard = LoopGuard(domain, daily_budget=2.00)
    
    for round in range(rounds):
        guard.check_before_round(round)  # raises LoopGuardError if should stop
        ... do research ...
        guard.record_round(question, score, verdict, cost)
        guard.check_after_round()  # raises LoopGuardError if should stop
"""

import logging
from difflib import SequenceMatcher

logger = logging.getLogger("loop_guard")


class LoopGuardError(Exception):
    """Raised when loop guard detects a problem that should stop execution."""
    def __init__(self, reason: str, severity: str = "warning"):
        self.reason = reason
        self.severity = severity  # "warning" or "critical"
        super().__init__(reason)


class LoopGuard:
    """
    Real-time loop monitor. Tracks state across rounds and raises
    LoopGuardError when something goes wrong.
    """

    # Thresholds (adjustable)
    MAX_CONSECUTIVE_FAILURES = 3       # 3 rejects in a row = something is wrong
    QUESTION_SIMILARITY_THRESHOLD = 0.70  # questions >70% similar = brain is looping
    MAX_SIMILAR_QUESTIONS = 2          # allow 1 similar pair, not 2
    COST_VELOCITY_LIMIT = 0.80        # stop if >80% of remaining budget used
    SCORE_REGRESSION_WINDOW = 3        # look at last N scores
    SCORE_REGRESSION_THRESHOLD = -1.5  # avg score drop of 1.5+ = regression
    MAX_SAME_ERROR = 2                 # same error message repeated = structural problem

    def __init__(self, domain: str, daily_budget: float = 2.00, starting_spend: float = 0.0):
        self.domain = domain
        self.daily_budget = daily_budget
        self.starting_spend = starting_spend
        self.run_spend = 0.0

        # Accumulated state
        self.questions: list[str] = []
        self.scores: list[float] = []
        self.verdicts: list[str] = []
        self.errors: list[str] = []
        self.round_costs: list[float] = []

        # Counters
        self.consecutive_failures = 0
        self.similar_question_count = 0
        self.total_rounds = 0

    def check_before_round(self, round_num: int) -> None:
        """
        Pre-round checks. Call before each research round.
        Raises LoopGuardError if the loop should stop.
        """
        # Cost velocity check
        remaining_budget = self.daily_budget - self.starting_spend - self.run_spend
        if remaining_budget <= 0:
            raise LoopGuardError(
                f"Budget exhausted (${self.starting_spend + self.run_spend:.2f} of ${self.daily_budget:.2f})",
                severity="critical",
            )

        if self.run_spend > 0 and remaining_budget > 0:
            velocity = self.run_spend / (remaining_budget + self.run_spend)
            if velocity > self.COST_VELOCITY_LIMIT and self.total_rounds >= 2:
                raise LoopGuardError(
                    f"Cost velocity too high: {velocity:.0%} of available budget consumed "
                    f"in {self.total_rounds} rounds (${self.run_spend:.4f} spent, "
                    f"${remaining_budget:.4f} remaining)",
                    severity="warning",
                )

    def record_round(
        self,
        question: str,
        score: float,
        verdict: str,
        cost: float,
        error: str | None = None,
    ) -> None:
        """Record the outcome of a round. Call after each research round."""
        self.questions.append(question)
        self.scores.append(score)
        self.verdicts.append(verdict)
        self.round_costs.append(cost)
        self.run_spend += cost
        self.total_rounds += 1

        # Track consecutive failures
        if verdict != "accept":
            self.consecutive_failures += 1
            if error:
                self.errors.append(error)
        else:
            self.consecutive_failures = 0

        # Track question similarity
        if len(self.questions) >= 2:
            latest = self.questions[-1]
            for prev in self.questions[:-1]:
                similarity = SequenceMatcher(None, latest.lower(), prev.lower()).ratio()
                if similarity > self.QUESTION_SIMILARITY_THRESHOLD:
                    self.similar_question_count += 1
                    logger.info(
                        f"Similar questions detected ({similarity:.0%}): "
                        f"'{latest[:50]}' ≈ '{prev[:50]}'"
                    )
                    break  # Count once per new question

    def check_after_round(self) -> None:
        """
        Post-round checks. Call after recording each round.
        Raises LoopGuardError if the loop should stop.
        """
        # Consecutive failures
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            raise LoopGuardError(
                f"{self.consecutive_failures} consecutive failures in '{self.domain}' — "
                f"likely a structural problem (last scores: {self.scores[-self.MAX_CONSECUTIVE_FAILURES:]})",
                severity="critical",
            )

        # Question repetition (brain is looping)
        if self.similar_question_count >= self.MAX_SIMILAR_QUESTIONS:
            raise LoopGuardError(
                f"Brain is looping: {self.similar_question_count} similar questions generated "
                f"in '{self.domain}' — question generator may be stuck",
                severity="warning",
            )

        # Score regression
        if len(self.scores) >= self.SCORE_REGRESSION_WINDOW:
            recent = self.scores[-self.SCORE_REGRESSION_WINDOW:]
            earlier = self.scores[: max(1, len(self.scores) - self.SCORE_REGRESSION_WINDOW)]
            if earlier:
                avg_recent = sum(recent) / len(recent)
                avg_earlier = sum(earlier) / len(earlier)
                drop = avg_recent - avg_earlier
                if drop < self.SCORE_REGRESSION_THRESHOLD:
                    raise LoopGuardError(
                        f"Score regression in '{self.domain}': recent avg {avg_recent:.1f} "
                        f"vs earlier avg {avg_earlier:.1f} (drop: {drop:+.1f})",
                        severity="warning",
                    )

        # Same error repeated
        if len(self.errors) >= self.MAX_SAME_ERROR:
            last_errors = self.errors[-self.MAX_SAME_ERROR:]
            if len(set(last_errors)) == 1:
                raise LoopGuardError(
                    f"Same error repeated {self.MAX_SAME_ERROR}x: '{last_errors[0][:100]}' — "
                    f"structural issue in '{self.domain}'",
                    severity="critical",
                )

    def get_status(self) -> dict:
        """Get current guard status for display/logging."""
        avg_score = sum(self.scores) / len(self.scores) if self.scores else 0
        return {
            "domain": self.domain,
            "total_rounds": self.total_rounds,
            "run_spend": round(self.run_spend, 4),
            "consecutive_failures": self.consecutive_failures,
            "similar_questions": self.similar_question_count,
            "avg_score": round(avg_score, 1),
            "scores": self.scores,
            "healthy": self._is_healthy(),
        }

    def _is_healthy(self) -> bool:
        """Overall health check."""
        return (
            self.consecutive_failures < self.MAX_CONSECUTIVE_FAILURES
            and self.similar_question_count < self.MAX_SIMILAR_QUESTIONS
        )

    def summary(self) -> str:
        """Human-readable summary for end-of-run display."""
        status = self.get_status()
        lines = [
            f"  Loop Guard: {'✓ healthy' if status['healthy'] else '⚠ issues detected'}",
            f"  Rounds: {status['total_rounds']} | Spend: ${status['run_spend']:.4f}",
            f"  Avg score: {status['avg_score']}/10 | Failures: {status['consecutive_failures']} consecutive",
        ]
        if status["similar_questions"] > 0:
            lines.append(f"  ⚠ Similar questions: {status['similar_questions']}")
        return "\n".join(lines)
