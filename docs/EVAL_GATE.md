# Eval Gate（回归门禁）指南

本文档说明如何使用评测集对 Tiered Reasoning 改造进行回归守护。

## 1. 目标

1. 防止模型路由优化造成质量回退。
2. 建立“可量化”的上线门槛。
3. 为后续 CI 接入提供统一接口。

## 2. 数据集格式

数据集采用 JSONL，每行一个 case：

```json
{
  "id": "l3_practical",
  "precision_level": "L3",
  "prompt": "给我一份团队每周技术复盘会议的模板。",
  "must_include": ["议程", "行动项"]
}
```

字段说明：

1. `id`：用例唯一标识。
2. `precision_level`：用例意图级别（用于分层覆盖统计）。
3. `prompt`：输入任务。
4. `must_include`：最终回复必须包含的关键词列表（简化质量校验）。

示例文件：`evals/golden_tasks.sample.jsonl`

## 3. 运行方式

```bash
python3 scripts/run_eval_gate.py \
  --dataset evals/golden_tasks.sample.jsonl \
  --source auto \
  --min-success-rate 80 \
  --min-audit-pass-rate 70
```

参数说明：

1. `--source`：trace 读取源（`auto`/`db`/`jsonl`）。
2. `--min-success-rate`：关键词命中成功率门槛（百分比）。
3. `--min-audit-pass-rate`：审计通过率门槛（百分比）。

## 4. 输出与判定

报告输出路径：

1. `evals/reports/eval_report_<timestamp>.json`
2. `evals/reports/latest.json`

核心指标：

1. `success_rate_pct`
2. `audit_pass_rate_pct`
3. `avg_total_tokens`
4. `avg_duration_seconds`

门禁规则：

1. 成功率低于门槛 -> `EVAL_GATE: FAIL`（退出码 1）
2. 审计通过率低于门槛 -> `EVAL_GATE: FAIL`（退出码 1）
3. 否则 -> `EVAL_GATE: PASS`（退出码 0）

## 5. CI 接入建议

在 CI 中添加以下步骤：

```bash
python3 scripts/run_eval_gate.py --source auto --min-success-rate 85 --min-audit-pass-rate 75
```

如退出码为 1，则阻断合并。

