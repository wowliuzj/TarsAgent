# Metabase Trace 看板指南

本文档描述 Tars Phase 2 的 Trace DB 化在 Metabase 的接入方式与推荐图表。

## 1. 前置条件

1. `.env` 配置 `TRACE_SINK_MODE=both`（或 `db`）。
2. 已执行数据库初始化（`app/db.py` 的 `init_db` 会自动建表）。
3. 已应用查询视图：

```bash
python3 scripts/apply_metabase_views.py
```

## 2. 推荐数据源

将 Metabase 连接到当前 PostgreSQL 后，优先使用以下视图：

- `vw_trace_runs_summary`
- `vw_trace_event_timeline`
- `vw_trace_llm_usage`
- `vw_trace_tool_calls`
- `vw_trace_hitl_decisions`
- `vw_trace_auditor_verdicts`
- `vw_trace_tier_transitions`

## 3. 推荐仪表盘组件

1. **运行成功率**（数值卡）
   - 来源：`vw_trace_runs_summary`
   - 指标：`status=completed` 占比
2. **平均时延**（趋势图）
   - 来源：`vw_trace_runs_summary`
   - 指标：`avg(duration_seconds)`，按天聚合
3. **LLM Token 消耗**（堆叠柱状图）
   - 来源：`vw_trace_llm_usage`
   - 维度：`node` / `model`
   - 指标：`sum(total_tokens)`
4. **工具调用热力图**（条形图）
   - 来源：`vw_trace_tool_calls`
   - 维度：`tool_name`
   - 指标：`count(*)`
5. **HITL 通过率**（饼图或数值卡）
   - 来源：`vw_trace_hitl_decisions`
   - 指标：`approved=true/false` 分布
6. **审计通过率**（数值卡 + 趋势）
   - 来源：`vw_trace_auditor_verdicts`
   - 指标：`approved=true` 占比

## 4. 仪表盘模板（可直接照抄）

建议仪表盘名：`Tars Trace Observability (Prod)`

统一筛选器（Dashboard Filter）：
- 时间范围：绑定 `started_at` / `ts`
- `trace_id`（可选）
- `node`（可选）
- `tool_name`（可选）

### 卡片 1：运行总量（今日）
- 类型：Number
- 来源：`vw_trace_runs_summary`
- 过滤：`started_at >= CURRENT_DATE`
- 指标：`count(*)`

```sql
SELECT count(*) AS runs_today
FROM vw_trace_runs_summary
WHERE started_at >= CURRENT_DATE;
```

### 卡片 2：运行成功率（近 7 天）
- 类型：Number / Gauge
- 来源：`vw_trace_runs_summary`
- 过滤：`started_at >= now() - interval '7 day'`
- 指标：`completed / total`

```sql
SELECT
  round(
    100.0 * sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / NULLIF(count(*), 0),
    2
  ) AS success_rate_pct
FROM vw_trace_runs_summary
WHERE started_at >= now() - interval '7 day';
```

### 卡片 3：平均时延趋势（近 14 天）
- 类型：Line
- 来源：`vw_trace_runs_summary`
- X 轴：`date_trunc('day', started_at)`
- Y 轴：`avg(duration_seconds)`

```sql
SELECT
  date_trunc('day', started_at) AS day,
  avg(duration_seconds) AS avg_duration_seconds
FROM vw_trace_runs_summary
WHERE started_at >= now() - interval '14 day'
GROUP BY 1
ORDER BY 1;
```

### 卡片 4：LLM Token 趋势（近 14 天）
- 类型：Stacked Bar / Line
- 来源：`vw_trace_llm_usage`
- 维度：`day + node`
- 指标：`sum(total_tokens)`

```sql
SELECT
  date_trunc('day', ts) AS day,
  node,
  sum(total_tokens) AS total_tokens
FROM vw_trace_llm_usage
WHERE ts >= now() - interval '14 day'
GROUP BY 1, 2
ORDER BY 1, 2;
```

### 卡片 5：模型成本分布（近 7 天）
- 类型：Bar
- 来源：`vw_trace_llm_usage`
- 维度：`model`
- 指标：`sum(total_tokens)`

```sql
SELECT
  model,
  sum(total_tokens) AS total_tokens
FROM vw_trace_llm_usage
WHERE ts >= now() - interval '7 day'
GROUP BY 1
ORDER BY 2 DESC;
```

### 卡片 6：工具调用 TOP10（近 7 天）
- 类型：Bar
- 来源：`vw_trace_tool_calls`
- 条件：`event_type='tool_call_finished'`
- 指标：`count(*)`

```sql
SELECT
  tool_name,
  count(*) AS call_count
FROM vw_trace_tool_calls
WHERE event_type = 'tool_call_finished'
  AND ts >= now() - interval '7 day'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
```

### 卡片 7：HITL 通过率（近 14 天）
- 类型：Pie / Number
- 来源：`vw_trace_hitl_decisions`
- 指标：`approved true/false 分布`

```sql
SELECT
  approved,
  count(*) AS decision_count
FROM vw_trace_hitl_decisions
WHERE ts >= now() - interval '14 day'
GROUP BY 1
ORDER BY 2 DESC;
```

### 卡片 8：审计通过率（近 14 天）
- 类型：Number / Gauge
- 来源：`vw_trace_auditor_verdicts`
- 指标：`approved=true 占比`

```sql
SELECT
  round(
    100.0 * sum(CASE WHEN approved THEN 1 ELSE 0 END) / NULLIF(count(*), 0),
    2
  ) AS auditor_pass_rate_pct
FROM vw_trace_auditor_verdicts
WHERE ts >= now() - interval '14 day';
```

### 卡片 9：审计驳回原因 TOP10（近 14 天）
- 类型：Table
- 来源：`vw_trace_auditor_verdicts`

```sql
SELECT
  reason,
  count(*) AS reject_count
FROM vw_trace_auditor_verdicts
WHERE ts >= now() - interval '14 day'
  AND approved = false
  AND reason IS NOT NULL
  AND reason <> ''
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
```

### 卡片 10：Trace 时间线明细（钻取）
- 类型：Table
- 来源：`vw_trace_event_timeline`
- 说明：绑定 `trace_id` 筛选器，作为回放入口

```sql
SELECT
  ts,
  node,
  event_type,
  severity,
  payload
FROM vw_trace_event_timeline
WHERE trace_id = {{trace_id}}
ORDER BY ts ASC;
```

### 卡片 11：Tier 升降级触发分布（近 14 天）
- 类型：Bar
- 来源：`vw_trace_tier_transitions`

```sql
SELECT
  trigger,
  count(*) AS transition_count
FROM vw_trace_tier_transitions
WHERE ts >= now() - interval '14 day'
GROUP BY 1
ORDER BY 2 DESC;
```

## 5. Trace 回放联动建议

- Metabase 卡片点击进入明细时，显示 `trace_id`。
- 用 `trace_id` 直接执行：

```bash
python3 scripts/replay_trace.py <trace_id> --source db
```

即可回放单次任务的完整事件链路。
