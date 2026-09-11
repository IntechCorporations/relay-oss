"""Tests for the cost-aware auto-router: complexity scoring, rung selection, fallback
when a rung isn't configured, escalation on verifier failure, and end-to-end wiring
through the Orchestrator with per-step model switching."""

from relay.engines.mock_engine import MockEngine
from relay.orchestrator import Orchestrator
from relay.router import Router, TokenBudget, score_complexity


def test_score_complexity_easy_step_scores_low():
    score = score_complexity("Rename a variable for clarity", ["a.py"], {"a.py": 100})
    assert score < 0.35


def test_score_complexity_hard_step_scores_high():
    score = score_complexity(
        "Refactor the concurrency handling to avoid a race condition across threads",
        ["a.py", "b.py", "c.py", "d.py"],
        {"a.py": 30_000, "b.py": 10_000, "c.py": 5_000, "d.py": 5_000},
    )
    assert score > 0.7


def test_router_disabled_always_returns_cheap():
    router = Router({"enabled": False})
    decision = router.choose({"id": "1", "description": "refactor everything", "target_files": []}, {})
    assert decision.tier == "cheap"


def test_router_routes_easy_step_to_cheap():
    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "strong": {"provider": "mock"}}})
    decision = router.choose({"id": "1", "description": "add a docstring", "target_files": []}, {})
    assert decision.tier == "cheap"


def test_router_routes_hard_step_to_strong_when_configured():
    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "strong": {"provider": "mock"}}})
    decision = router.choose(
        {"id": "1", "description": "refactor the security-sensitive auth flow for concurrency safety", "target_files": ["a.py", "b.py"]},
        {},
    )
    assert decision.tier == "strong"


def test_router_falls_back_when_preferred_rung_missing():
    # Only "cheap" is configured, so even a hard step must fall back to it.
    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}}})
    decision = router.choose(
        {"id": "1", "description": "refactor the concurrency-sensitive race condition", "target_files": ["a.py"] * 5},
        {},
    )
    assert decision.tier == "cheap"
    assert "no 'strong' engine is configured" in decision.reason


def test_router_escalates_after_mark_failed():
    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "strong": {"provider": "mock"}}})
    step = {"id": "1", "description": "add a comment", "target_files": []}
    first = router.choose(step, {})
    assert first.tier == "cheap"
    router.mark_failed("1")
    second = router.choose(step, {})
    assert second.tier == "strong"
    assert "failed verification" in second.reason


def test_budget_pressure_raises_thresholds():
    step = {"id": "1", "description": "update the config loader", "target_files": ["a.py", "b.py"]}
    file_sizes = {"a.py": 6_000, "b.py": 4_000}  # total 10,000 bytes -> moderate complexity

    fresh_budget = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "mid": {"provider": "mock"}}})
    baseline = fresh_budget.choose(step, file_sizes)
    assert baseline.tier == "mid"  # with no budget pressure, this step clears the "mid" bar

    budget = TokenBudget(max_tokens=1000)
    budget.record(900)  # 90% spent
    assert budget.pressure() == 0.9
    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "mid": {"provider": "mock"}}}, budget=budget)
    # The same step, under heavy budget pressure, should be pushed back to "cheap"
    # because pressure raises how much complexity it takes to justify a pricier rung.
    decision = router.choose(step, file_sizes)
    assert decision.tier == "cheap"


def test_orchestrator_routes_steps_to_different_engines_and_labels_ledger():
    planner = MockEngine(model="mock-planner")
    verifier = MockEngine(model="mock-verifier")
    fixed_builder = MockEngine(model="mock-builder-unused")
    cheap_engine = MockEngine(model="mock-cheap")
    strong_engine = MockEngine(model="mock-strong")

    router = Router({"enabled": True, "rungs": {"cheap": {"provider": "mock"}, "strong": {"provider": "mock"}}})

    orch = Orchestrator(
        planner,
        fixed_builder,
        verifier,
        safety_cfg={},
        verification_cfg={"max_fix_retries": 0},
        project_dir="/tmp",
        logger=lambda msg: None,
        router=router,
        rung_engines={"cheap": cheap_engine, "strong": strong_engine},
    )

    easy_step = {"id": "1", "description": "add a docstring", "target_files": []}
    result = orch.build_step("demo task", easy_step)
    assert result["step"] == easy_step

    hard_step = {"id": "2", "description": "refactor the concurrency-sensitive auth flow", "target_files": ["a.py", "b.py", "c.py"]}
    orch.build_step("demo task", hard_step)

    by_model = orch.ledger.by_model()
    tiers_used = {row["tier"] for row in by_model}
    assert "builder:cheap" in tiers_used
    assert "builder:strong" in tiers_used
    # The fixed builder engine should never have been called at all.
    assert not any(row["model"] == "mock-builder-unused" for row in by_model)
