#!/usr/bin/env python3
import argparse
import asyncio
import glob
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def ensure_trace_schema():
    """
    启动前确保 trace 相关表存在。
    若数据库不可用或初始化失败，自动降级为 jsonl sink，避免评测流程被硬阻断。
    """
    try:
        from app.db import init_db
        init_db()
        print("Trace schema ready (init_db ok).")
    except Exception as e:
        os.environ["TRACE_SINK_MODE"] = "jsonl"
        print(f"WARN: init_db failed, fallback TRACE_SINK_MODE=jsonl. reason={e}")


def _parse_iso_ts(ts: str | None) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def load_trace_events_jsonl(trace_id: str, log_dir: str = "logs") -> List[Dict[str, Any]]:
    files = sorted(glob.glob(os.path.join(log_dir, "traces-*.jsonl")))
    events: List[Dict[str, Any]] = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("trace_id") == trace_id:
                    events.append(data)
    events.sort(key=lambda e: e.get("ts", ""))
    return events


def load_trace_events_db(trace_id: str) -> List[Dict[str, Any]]:
    from sqlmodel import Session, select
    from app.db import engine, TraceEventRecord

    rows: List[Dict[str, Any]] = []
    with Session(engine) as session:
        records = session.exec(
            select(TraceEventRecord)
            .where(TraceEventRecord.trace_id == trace_id)
            .order_by(TraceEventRecord.ts.asc())
        ).all()
        for r in records:
            ts = r.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rows.append(
                {
                    "trace_id": r.trace_id,
                    "event_id": r.event_id,
                    "ts": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "node": r.node,
                    "event_type": r.event_type,
                    "severity": r.severity,
                    "payload": r.payload or {},
                }
            )
    return rows


def load_trace_events(trace_id: str, source: str, log_dir: str = "logs") -> List[Dict[str, Any]]:
    if source == "db":
        return load_trace_events_db(trace_id)
    if source == "jsonl":
        return load_trace_events_jsonl(trace_id, log_dir=log_dir)
    # auto
    try:
        return load_trace_events_db(trace_id)
    except Exception:
        return load_trace_events_jsonl(trace_id, log_dir=log_dir)


@dataclass
class EvalCaseResult:
    case_id: str
    trace_id: str
    response_length: int
    success: bool
    audit_passed: bool
    total_tokens: int
    duration_seconds: Optional[float]
    missing_required_phrases: List[str]


def analyze_case_result(
    *,
    case: Dict[str, Any],
    response: str,
    trace_id: str,
    events: List[Dict[str, Any]],
) -> EvalCaseResult:
    required = case.get("must_include", []) or []
    missing = [p for p in required if p not in response]
    success = len(missing) == 0 and len(response.strip()) > 0

    audit_passed = False
    total_tokens = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    for e in events:
        event_type = e.get("event_type", "")
        payload = e.get("payload", {}) or {}
        if event_type == "auditor_verdict":
            if payload.get("approved") is True:
                audit_passed = True
        if event_type == "llm_call_finished":
            usage = payload.get("usage", {}) or {}
            total_tokens += int(usage.get("total_tokens", 0) or 0)
        if event_type == "agent_run_started":
            started_at = _parse_iso_ts(e.get("ts"))
        if event_type == "agent_run_completed":
            completed_at = _parse_iso_ts(e.get("ts"))

    duration = None
    if started_at and completed_at:
        duration = (completed_at - started_at).total_seconds()

    return EvalCaseResult(
        case_id=str(case.get("id", "unknown_case")),
        trace_id=trace_id,
        response_length=len(response or ""),
        success=success,
        audit_passed=audit_passed,
        total_tokens=total_tokens,
        duration_seconds=duration,
        missing_required_phrases=missing,
    )


async def run_eval(
    dataset_path: str,
    source: str,
    log_dir: str,
    min_success_rate: float,
    min_audit_pass_rate: float,
) -> int:
    from app.agent import TarsAgent

    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    if not cases:
        print("No eval cases found.")
        return 1

    results: List[EvalCaseResult] = []
    for idx, case in enumerate(cases):
        prompt = case.get("prompt", "")
        if not prompt:
            continue
        agent = TarsAgent(session_id=900000 + idx)
        try:
            response = await agent.run(prompt)
            trace_id = agent.last_trace_id or ""
        except asyncio.CancelledError:
            # 用户中断（Ctrl+C）时，保持优雅退出，不抛整段异步栈。
            print("Eval interrupted (cancelled by user).")
            return 130
        finally:
            await agent.shutdown()

        events = load_trace_events(trace_id, source=source, log_dir=log_dir) if trace_id else []
        results.append(
            analyze_case_result(
                case=case,
                response=response,
                trace_id=trace_id,
                events=events,
            )
        )

    total = len(results)
    success_count = sum(1 for r in results if r.success)
    audit_pass_count = sum(1 for r in results if r.audit_passed)
    avg_tokens = (sum(r.total_tokens for r in results) / total) if total else 0.0
    avg_duration = (
        sum(r.duration_seconds or 0.0 for r in results) / total if total else 0.0
    )

    success_rate = (success_count / total) * 100 if total else 0.0
    audit_pass_rate = (audit_pass_count / total) * 100 if total else 0.0

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "dataset_path": dataset_path,
        "summary": {
            "total_cases": total,
            "success_count": success_count,
            "audit_pass_count": audit_pass_count,
            "success_rate_pct": round(success_rate, 2),
            "audit_pass_rate_pct": round(audit_pass_rate, 2),
            "avg_total_tokens": round(avg_tokens, 2),
            "avg_duration_seconds": round(avg_duration, 2),
            "gate": {
                "min_success_rate_pct": min_success_rate,
                "min_audit_pass_rate_pct": min_audit_pass_rate,
            },
        },
        "cases": [
            {
                "case_id": r.case_id,
                "trace_id": r.trace_id,
                "response_length": r.response_length,
                "success": r.success,
                "audit_passed": r.audit_passed,
                "total_tokens": r.total_tokens,
                "duration_seconds": r.duration_seconds,
                "missing_required_phrases": r.missing_required_phrases,
            }
            for r in results
        ],
    }

    reports_dir = Path("evals/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    report_path = reports_dir / f"eval_report_{ts}.json"
    latest_path = reports_dir / "latest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Eval report written: {report_path}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))

    gate_passed = success_rate >= min_success_rate and audit_pass_rate >= min_audit_pass_rate
    if gate_passed:
        print("EVAL_GATE: PASS")
        return 0
    print("EVAL_GATE: FAIL")
    return 1


def main():
    parser = argparse.ArgumentParser(description="Run Tars eval gate on golden task set.")
    parser.add_argument(
        "--dataset",
        default="evals/golden_tasks.sample.jsonl",
        help="jsonl dataset path (default: evals/golden_tasks.sample.jsonl)",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "jsonl", "db"],
        default="auto",
        help="trace source for metrics (default: auto)",
    )
    parser.add_argument("--log-dir", default="logs", help="trace log directory")
    parser.add_argument("--min-success-rate", type=float, default=80.0, help="min success rate pct")
    parser.add_argument("--min-audit-pass-rate", type=float, default=70.0, help="min audit pass rate pct")
    args = parser.parse_args()

    ensure_trace_schema()

    try:
        code = asyncio.run(
            run_eval(
                dataset_path=args.dataset,
                source=args.source,
                log_dir=args.log_dir,
                min_success_rate=args.min_success_rate,
                min_audit_pass_rate=args.min_audit_pass_rate,
            )
        )
    except KeyboardInterrupt:
        print("Eval interrupted by user (KeyboardInterrupt). Exit 130.")
        code = 130
    raise SystemExit(code)


if __name__ == "__main__":
    main()
