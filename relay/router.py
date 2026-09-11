"""Cost-aware auto-routing: picks the cheapest engine capable of a given step instead of
sending every step to whatever model is configured for a tier.

The idea: most builder steps are mechanical (rename a variable, add a null check, write
a getter) and a free local model handles them fine. A minority are genuinely hard
(cross-file refactors, concurrency, security-sensitive code, "fix this subtle bug") and
benefit from a stronger hosted model. Router.choose() scores a step's *complexity* from
cheap, local signals (no extra API call) and returns the engine to use for it, escalating
to progressively stronger engines only when the cheap one is likely to struggle, or after
a verifier rejection.

This is intentionally simple and inspectable rather than another model call: every
decision it makes is explainable in one sentence, which matters when you're trying to
understand where your tokens went.
"""

from __future__ import annotations

from dataclasses import dataclass

# Signals that suggest a step needs more capability than "write this obvious code".
HARD_KEYWORDS = [
    "refactor", "architecture", "concurrency", "race condition", "thread", "async",
    "security", "auth", "encryption", "vulnerability", "performance", "optimize",
    "migrate", "migration", "backward compat", "edge case", "subtle", "flaky",
    "deadlock", "memory leak", "cross-file", "distributed", "consensus",
]

# Signals that suggest a step is small/mechanical and safe for the cheapest engine.
EASY_KEYWORDS = [
    "rename", "typo", "comment", "docstring", "formatting", "lint", "import",
    "add a getter", "add a log", "print statement", "readme", "changelog",
]


@dataclass
class RouteDecision:
    tier: str  # "cheap", "mid", "strong" — which rung of the ladder was chosen
    engine_key: str  # which configured engine slot this maps to
    reason: str  # one-sentence, human-readable justification


@dataclass
class TokenBudget:
    """Tracks spend against an optional session cap so the router can also escalate
    *down* under budget pressure, not just up for hard steps."""

    max_tokens: int | None = None
    spent: int = 0

    def record(self, n: int) -> None:
        self.spent += n

    def remaining(self) -> float:
        if self.max_tokens is None:
            return float("inf")
        return max(0, self.max_tokens - self.spent)

    def pressure(self) -> float:
        """0.0 = no budget set / plenty left, 1.0 = fully spent."""
        if self.max_tokens is None or self.max_tokens == 0:
            return 0.0
        return min(1.0, self.spent / self.max_tokens)


def score_complexity(description: str, target_files: list[str], file_sizes: dict) -> float:
    """Returns a 0.0-1.0 complexity estimate for one plan step, from free local signals:
    keyword hints in the description, how many files it touches, and how large those
    files already are (bigger files = more context to hold correctly = harder)."""
    text = (description or "").lower()
    score = 0.15  # baseline: assume mechanical unless signals say otherwise

    if any(k in text for k in HARD_KEYWORDS):
        score += 0.45
    if any(k in text for k in EASY_KEYWORDS):
        score -= 0.10

    n_files = len(target_files or [])
    if n_files >= 4:
        score += 0.25
    elif n_files >= 2:
        score += 0.10

    total_bytes = sum(file_sizes.get(f, 0) for f in (target_files or []))
    if total_bytes > 20_000:
        score += 0.2
    elif total_bytes > 6_000:
        score += 0.1

    return max(0.0, min(1.0, score))


class Router:
    """Chooses which configured engine slot ("cheap", "mid", "strong") handles a given
    builder step, and can escalate a specific step after a failure.

    ladder_cfg looks like:
        {
          "enabled": true,
          "escalate_on_verify_fail": true,
          "thresholds": {"mid": 0.35, "strong": 0.7},
          "rungs": {
            "cheap":  {"provider": "ollama", "model": "qwen2.5-coder:7b", ...},
            "mid":    {"provider": "openai_compatible", "model": "llama-3.1-70b", ...},
            "strong": {"provider": "anthropic", "model": "claude-sonnet-4-5", ...},
          }
        }
    Any rung can be omitted; the router falls back to the next cheaper configured rung
    if a rung above "cheap" isn't set up, and never fails a run just because "strong"
    has no API key — it just stays on "cheap"/"mid" and says so in the reason string.
    """

    def __init__(self, ladder_cfg: dict, budget: TokenBudget | None = None):
        self.cfg = ladder_cfg or {}
        self.rungs = self.cfg.get("rungs", {})
        self.thresholds = self.cfg.get("thresholds", {"mid": 0.35, "strong": 0.7})
        self.budget = budget or TokenBudget(self.cfg.get("max_tokens_per_run"))
        self._escalated_steps: set[str] = set()

    def _available_rung(self, preferred: str) -> str:
        order = ["strong", "mid", "cheap"]
        start = order.index(preferred) if preferred in order else len(order) - 1
        for rung in order[start:]:
            if self.rungs.get(rung):
                return rung
        # Nothing configured at all below the preferred rung — fall back to "cheap"
        # even if unconfigured; build_engine will raise a clear error if it's missing.
        return "cheap"

    def choose(self, step: dict, file_sizes: dict) -> RouteDecision:
        if not self.cfg.get("enabled", False):
            return RouteDecision(tier="cheap", engine_key="cheap", reason="Auto-routing disabled; using the configured builder engine.")

        step_id = str(step.get("id", ""))
        description = step.get("description", "")
        target_files = step.get("target_files", [])

        if step_id in self._escalated_steps and self.cfg.get("escalate_on_verify_fail", True):
            rung = self._available_rung("strong")
            return RouteDecision(
                tier=rung,
                engine_key=rung,
                reason=f"Step {step_id} failed verification once already; escalated to '{rung}'.",
            )

        complexity = score_complexity(description, target_files, file_sizes)
        pressure = self.budget.pressure()

        # Under heavy budget pressure, require a higher bar before spending on a
        # pricier rung — cap how much a tight budget lets you escalate.
        mid_threshold = self.thresholds.get("mid", 0.35) + 0.2 * pressure
        strong_threshold = self.thresholds.get("strong", 0.7) + 0.2 * pressure

        if complexity >= strong_threshold:
            preferred = "strong"
        elif complexity >= mid_threshold:
            preferred = "mid"
        else:
            preferred = "cheap"

        rung = self._available_rung(preferred)
        budget_note = f" (budget {pressure * 100:.0f}% spent, raised bar)" if pressure > 0.5 else ""
        if rung != preferred:
            reason = (
                f"Step {step_id} scored {complexity:.2f} complexity (wanted '{preferred}'), "
                f"but no '{preferred}' engine is configured, so using '{rung}'.{budget_note}"
            )
        else:
            reason = f"Step {step_id} scored {complexity:.2f} complexity → routed to '{rung}'.{budget_note}"

        return RouteDecision(tier=rung, engine_key=rung, reason=reason)

    def mark_failed(self, step_id: str) -> None:
        """Call when the verifier rejects a step's output, so the next attempt at that
        step escalates instead of repeating the same (apparently insufficient) engine."""
        self._escalated_steps.add(str(step_id))
