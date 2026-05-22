import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


TIER_ORDER = ["low", "mid", "high", "ultra"]
VALID_TIERS = set(TIER_ORDER)


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_tier(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    tier = value.strip().lower()
    return tier if tier in VALID_TIERS else fallback


@dataclass
class TierResolution:
    model: str
    tier: str
    route_reason: str
    base_tier: str
    transition: Optional[Dict[str, Any]] = None


def get_node_role(caller_node: str) -> str:
    mapping = {
        "planner": "planner",
        "think": "executor",
        "auditor": "auditor",
        "reflect": "reflect",
    }
    return mapping.get(caller_node, caller_node)


def _tier_model_map(default_model: str) -> Dict[str, str]:
    return {
        "low": os.getenv("TIER_MODEL_LOW", default_model),
        "mid": os.getenv("TIER_MODEL_MID", default_model),
        "high": os.getenv("TIER_MODEL_HIGH", default_model),
        "ultra": os.getenv("TIER_MODEL_ULTRA", default_model),
    }


def _role_default_tier(role: str) -> str:
    env_key = f"TIER_DEFAULT_{role.upper()}"
    return _normalize_tier(os.getenv(env_key), "mid")


def _executor_precision_tier(precision_level: str | None) -> Optional[str]:
    if not precision_level:
        return None
    env_key = f"TIER_EXECUTOR_{precision_level.upper()}"
    if env_key not in os.environ:
        return None
    tier = _normalize_tier(os.getenv(env_key), "")
    return tier or None


def resolve_tier_and_model(
    *,
    default_model: str,
    caller_node: str,
    precision_level: str | None = None,
    state: Optional[Dict[str, Any]] = None,
    run_tokens_used: int = 0,
) -> TierResolution:
    enabled = _to_bool(os.getenv("TIER_ROUTING_ENABLED"), False)
    if not enabled:
        return TierResolution(
            model=default_model,
            tier="default",
            base_tier="default",
            route_reason="routing_disabled",
            transition=None,
        )

    role = get_node_role(caller_node)
    tier_models = _tier_model_map(default_model)

    route_reason = "role_default"
    tier = _role_default_tier(role)

    # Phase 2: role + L1~L6 双因子（仅 executor）
    if role == "executor":
        override = _executor_precision_tier(precision_level)
        if override:
            tier = override
            route_reason = "l_level_override"

    base_tier = tier

    # Phase 3: 自适应升级（重试 / 审计反馈）
    state = state or {}
    max_retries_before_upgrade = _safe_int(
        os.getenv("TIER_MAX_RETRIES_BEFORE_UPGRADE"),
        2,
    )
    retries = int(state.get("executor_retries", 0) or 0)
    has_audit_feedback = bool(state.get("audit_feedback"))

    transition: Optional[Dict[str, Any]] = None
    if role == "executor" and (has_audit_feedback or retries >= max_retries_before_upgrade):
        current_idx = TIER_ORDER.index(tier)
        upgraded_idx = min(current_idx + 1, len(TIER_ORDER) - 1)
        upgraded = TIER_ORDER[upgraded_idx]
        if upgraded != tier:
            transition = {
                "from_tier": tier,
                "to_tier": upgraded,
                "trigger": "audit_feedback" if has_audit_feedback else "retry_threshold",
                "retries": retries,
            }
            tier = upgraded
            route_reason = "adaptive_upgrade"

    # Phase 3: 预算降级
    budget_tokens = _safe_int(os.getenv("TIER_BUDGET_TOKENS_PER_RUN"), 0)
    budget_downgrade_tier = _normalize_tier(os.getenv("TIER_BUDGET_DOWNGRADE_TIER"), "low")
    if budget_tokens > 0 and run_tokens_used >= budget_tokens:
        if tier != budget_downgrade_tier:
            transition = {
                "from_tier": tier,
                "to_tier": budget_downgrade_tier,
                "trigger": "budget_exceeded",
                "run_tokens_used": run_tokens_used,
                "budget_tokens": budget_tokens,
            }
        tier = budget_downgrade_tier
        route_reason = "budget_downgrade"

    model = tier_models.get(tier, default_model)
    return TierResolution(
        model=model,
        tier=tier,
        base_tier=base_tier,
        route_reason=route_reason,
        transition=transition,
    )

