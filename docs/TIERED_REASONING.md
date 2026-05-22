# Tiered Reasoning（仿生算力分级）实施规范

本文档定义 Tars 在 Harness Engineering 之上新增的 Tiered Reasoning 机制，覆盖 Phase 1~Phase 4 的实现与运维口径。

## 1. 目标

1. 按角色（Planner/Executor/Auditor/Reflect）分配默认算力档位。
2. 对 Executor 按 `L1~L6` 精度级别动态覆盖档位。
3. 在重试、审计驳回、预算超限时自动升降档。
4. 通过 Eval Gate 做回归门禁，防止“省钱但降质”。

## 2. 配置项（.env）

```env
TIER_ROUTING_ENABLED=false

TIER_MODEL_LOW=openai/gpt-5-mini
TIER_MODEL_MID=openai/gpt-5-mini
TIER_MODEL_HIGH=openai/gpt-5
TIER_MODEL_ULTRA=openai/gpt-5

TIER_DEFAULT_PLANNER=mid
TIER_DEFAULT_EXECUTOR=mid
TIER_DEFAULT_AUDITOR=high
TIER_DEFAULT_REFLECT=mid

TIER_EXECUTOR_L1=low
TIER_EXECUTOR_L2=low
TIER_EXECUTOR_L3=mid
TIER_EXECUTOR_L4=mid
TIER_EXECUTOR_L5=high
TIER_EXECUTOR_L6=ultra

TIER_MAX_RETRIES_BEFORE_UPGRADE=2
TIER_BUDGET_TOKENS_PER_RUN=0
TIER_BUDGET_DOWNGRADE_TIER=low

MODEL_FALLBACK_NAME=
LLM_MAX_RETRIES=2
LLM_RETRY_BASE_DELAY_MS=800
```

## 3. 路由优先级

1. `TIER_ROUTING_ENABLED=false` 时，直接使用 `MODEL_NAME`。
2. 启用后：
   1. Role 默认 Tier：`TIER_DEFAULT_<ROLE>`
   2. Executor 的 L 级别覆盖：`TIER_EXECUTOR_Lx`
   3. 自适应升级：审计驳回或重试达阈值升一档
   4. 预算降级：超过 `TIER_BUDGET_TOKENS_PER_RUN` 后降到 `TIER_BUDGET_DOWNGRADE_TIER`

## 4. 代码落点

- 路由核心：`app/tier_routing.py`
- 模型调用接入：`app/agent.py` 的 `_call_model`
- 节点透传：
  - Planner：`caller_node=planner`
  - Think：`caller_node=think` + `precision_level=Lx`
  - Auditor：`caller_node=auditor`
  - Reflect：`caller_node=reflect`

## 5. Trace 可观测性

新增/增强事件：

1. `llm_call_started`
   - `tier`
   - `base_tier`
   - `route_reason`
   - `precision_level`
   - `run_tokens_used_before_call`
2. `llm_call_finished`
   - `tier`
   - `route_reason`
   - `run_tokens_used_after_call`
3. `tier_transition`
   - `from_tier` / `to_tier`
   - `trigger`（`retry_threshold` / `audit_feedback` / `budget_exceeded`）

## 6. Phase 对应实施状态

1. Phase 1：已实现（Role 默认分层）
2. Phase 2：已实现（Role + L1~L6 双因子）
3. Phase 3：已实现（重试/审计触发升级 + Token 预算降级）
4. Phase 4：已提供 Eval Gate 框架（见 `docs/EVAL_GATE.md`）

## 7. 启用建议

1. 首次上线先开 `TIER_ROUTING_ENABLED=true`，但保持 `TIER_MODEL_*` 指向同一模型，确保行为一致。
2. 稳定后再逐步拉开模型档位差异。
3. 每次改动模型映射后，执行 Eval Gate：

```bash
python3 scripts/run_eval_gate.py --source auto
```
