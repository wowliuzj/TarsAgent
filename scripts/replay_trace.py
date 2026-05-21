#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys
from typing import List, Dict, Any
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def load_events(trace_id: str, log_dir: str, file_path: str | None = None) -> List[Dict[str, Any]]:
    files = [file_path] if file_path else sorted(glob.glob(os.path.join(log_dir, "traces-*.jsonl")))
    events: List[Dict[str, Any]] = []
    for f in files:
        if not f or not os.path.exists(f):
            continue
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


def _fmt_ts(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_events_from_db(trace_id: str) -> List[Dict[str, Any]]:
    from sqlmodel import Session, select
    from app.db import engine, TraceEventRecord

    events: List[Dict[str, Any]] = []
    with Session(engine) as session:
        rows = session.exec(
            select(TraceEventRecord)
            .where(TraceEventRecord.trace_id == trace_id)
            .order_by(TraceEventRecord.ts.asc())
        ).all()
        for row in rows:
            events.append({
                "trace_id": row.trace_id,
                "event_id": row.event_id,
                "ts": _fmt_ts(row.ts),
                "node": row.node,
                "event_type": row.event_type,
                "severity": row.severity,
                "payload": row.payload or {},
            })
    return events


def main():
    parser = argparse.ArgumentParser(description="Replay Tars trace events by trace_id")
    parser.add_argument("trace_id", help="trace id to replay")
    parser.add_argument("--source", choices=["auto", "jsonl", "db"], default="auto", help="event source (default: auto)")
    parser.add_argument("--log-dir", default="logs", help="trace log directory (default: logs)")
    parser.add_argument("--file", default=None, help="specific trace jsonl file to read")
    args = parser.parse_args()

    events: List[Dict[str, Any]] = []
    if args.source in ("db", "auto"):
        try:
            events = load_events_from_db(args.trace_id)
        except Exception as e:
            if args.source == "db":
                print(f"Load from DB failed: {e}")
                return
            print(f"DB unavailable, fallback to JSONL: {e}")
    if not events and args.source in ("jsonl", "auto"):
        events = load_events(args.trace_id, args.log_dir, args.file)

    if not events:
        print(f"No events found for trace_id={args.trace_id} (source={args.source})")
        return

    print(f"Trace Replay: {args.trace_id}")
    print(f"Events: {len(events)}")
    print("-" * 80)
    for e in events:
        ts = e.get("ts", "")
        node = e.get("node", "")
        event_type = e.get("event_type", "")
        severity = e.get("severity", "info")
        payload = e.get("payload", {})
        print(f"[{ts}] [{severity.upper()}] [{node}] {event_type}")
        if payload:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("-" * 80)


if __name__ == "__main__":
    main()
