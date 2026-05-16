# THP: Tars Harness Protocol (Tars 约束协议规范)

**版本**: 1.0.0-Draft
**状态**: 核心协议

## 1. 概述
THP 是 Tars 2.0 多智能体系统的通信与执行标准。它基于 **LangGraph 的状态管理** 和 **Pydantic 的类型约束**，旨在确保在复杂的异步任务流中，数据的一致性、安全性和逻辑的可审计性。

---

## 2. 状态定义 (The State Schema)
所有 Agent 角色必须共享且遵循唯一的 `TarsState` 模型。

### 核心状态字段 (Current Implementation)：
- `history`: (Annotated[List[BaseMessage], add]) 核心对话流，支持多回合追加。
- `mission`: (Optional[dict]) 任务元数据，包含目标 ID 和核心指令。
- `lane`: (Lane Enum) 任务泳道（如 EXECUTION, PLANNING, AUDIT）。
- `audit_log`: (List[dict]) 审计痕迹。
- `next_node`: (str) 状态机下一个跳转节点的建议。

### 预留字段 (Planned/Phase 2)：
- `task_pool`: 跨角色领取的任务列表。
- `shared_memory`: 临时缓存池。

---

## 3. 节点执行生命周期 (Node Lifecycle)
Harness 强制要求每个图节点 (Node) 遵循以下生命周期：

1.  **Pre-check (前置校验)**：检查当前 `TarsState` 是否具备执行该节点所需的必要条件。
2.  **Logic Run (核心逻辑)**：调用 LLM 进行思考或工具调用。
3.  **Harness Validation (约束校验)**：
    - **类型安全**：输出必须符合预定义的 Pydantic Schema。
    - **逻辑对齐**：输出是否偏离了 `mission.goal`？
    - **安全扫描**：输出是否包含黑名单中的敏感路径或非法指令。
4.  **State Transition (状态流转)**：只有通过校验，数据才会被更新回全局 `TarsState`。

---

## 4. 角色间协议 (Inter-Role Protocol)

### 4.1 PM -> Executor
- PM 必须将任务包装为 `SubTask` 对象，包含：`description`, `expected_output_schema`, `priority`。
- Executor 必须根据 `expected_output_schema` 返回结果，否则 Harness 将直接触发节点重试。

### 4.2 Executor -> Auditor
- 所有 Executor 的输出在“提交”前，自动进入 `pending_audit` 状态。
- Auditor 拥有 **Veto Power (否决权)**。如果驳回，必须提供 `rejection_reason`，Harness 驱动状态回溯。

---

## 5. 错误处理与优雅降级
- **Retry Policy**：单节点由于 Harness 校验失败触发的重试不得超过 3 次。
- **Fail-safe**：若连续失败，Harness 必须强制进入 `Human-in-the-Loop` 状态，请求用户介入。

---

## 6. 脱水与复水标准 (Persistence)
- 整个 `TarsState` 必须是可序列化的。
- 每一个周期结束，Harness 自动将 Snapshot 写入数据库，作为复水断点。

---
*Stay Strict. Stay Tars.*
