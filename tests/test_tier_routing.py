from app.tier_routing import resolve_tier_and_model


def _setup_minimal_env(monkeypatch):
    monkeypatch.setenv("TIER_ROUTING_ENABLED", "true")
    monkeypatch.setenv("TIER_MODEL_LOW", "model-low")
    monkeypatch.setenv("TIER_MODEL_MID", "model-mid")
    monkeypatch.setenv("TIER_MODEL_HIGH", "model-high")
    monkeypatch.setenv("TIER_MODEL_ULTRA", "model-ultra")
    monkeypatch.setenv("TIER_DEFAULT_PLANNER", "mid")
    monkeypatch.setenv("TIER_DEFAULT_EXECUTOR", "mid")
    monkeypatch.setenv("TIER_DEFAULT_AUDITOR", "high")
    monkeypatch.setenv("TIER_DEFAULT_REFLECT", "mid")


def test_tier_routing_disabled(monkeypatch):
    monkeypatch.setenv("TIER_ROUTING_ENABLED", "false")
    res = resolve_tier_and_model(
        default_model="fallback-model",
        caller_node="planner",
    )
    assert res.model == "fallback-model"
    assert res.route_reason == "routing_disabled"


def test_role_default_routing(monkeypatch):
    _setup_minimal_env(monkeypatch)
    res = resolve_tier_and_model(
        default_model="fallback-model",
        caller_node="auditor",
    )
    assert res.tier == "high"
    assert res.model == "model-high"
    assert res.route_reason == "role_default"


def test_executor_precision_override(monkeypatch):
    _setup_minimal_env(monkeypatch)
    monkeypatch.setenv("TIER_EXECUTOR_L1", "low")
    res = resolve_tier_and_model(
        default_model="fallback-model",
        caller_node="think",
        precision_level="L1",
        state={},
    )
    assert res.tier == "low"
    assert res.model == "model-low"
    assert res.route_reason == "l_level_override"


def test_retry_upgrade(monkeypatch):
    _setup_minimal_env(monkeypatch)
    monkeypatch.setenv("TIER_MAX_RETRIES_BEFORE_UPGRADE", "2")
    res = resolve_tier_and_model(
        default_model="fallback-model",
        caller_node="think",
        state={"executor_retries": 2},
    )
    assert res.tier == "high"
    assert res.route_reason == "adaptive_upgrade"
    assert res.transition is not None
    assert res.transition["trigger"] == "retry_threshold"


def test_budget_downgrade(monkeypatch):
    _setup_minimal_env(monkeypatch)
    monkeypatch.setenv("TIER_DEFAULT_AUDITOR", "high")
    monkeypatch.setenv("TIER_BUDGET_TOKENS_PER_RUN", "100")
    monkeypatch.setenv("TIER_BUDGET_DOWNGRADE_TIER", "low")
    res = resolve_tier_and_model(
        default_model="fallback-model",
        caller_node="auditor",
        run_tokens_used=120,
    )
    assert res.tier == "low"
    assert res.route_reason == "budget_downgrade"
    assert res.transition is not None
    assert res.transition["trigger"] == "budget_exceeded"

