import logging
import os
import json
from datetime import datetime

# 确保日志目录存在
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

# 动态生成带日期的日志文件名
today = datetime.now().strftime('%Y-%m-%d')
LOG_FILE = os.path.join(LOG_DIR, f"tars-{today}.log")
TRACE_LOG_FILE = os.path.join(LOG_DIR, f"traces-{today}.jsonl")

# 配置全局 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(), # 启用控制台输出
    ]
)

# 显式禁止某些极其啰嗦的库输出到控制台
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)

# 针对 LiteLLM 的特殊静默设置
try:
    import litellm
    litellm.set_verbose = False
    litellm.suppress_debug_info = True
    # 彻底关闭它那个讨厌的 "Give Feedback" 提示
    litellm._disable_debugging_on_proxy = True
except ImportError:
    pass

logger = logging.getLogger("Tars")

def _parse_iso_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.utcnow()
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.utcnow()


def _write_trace_to_jsonl(event: dict):
    with open(TRACE_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _write_trace_to_db(event: dict):
    # 延迟导入，避免 logger 初始化时引入数据库连接副作用。
    from sqlmodel import Session, select
    from app.db import engine, TraceEventRecord, TraceRun

    trace_id = str(event.get("trace_id", "") or "")
    if not trace_id:
        return

    event_id = str(event.get("event_id", "") or "")
    if not event_id:
        return

    event_type = str(event.get("event_type", "") or "")
    payload = event.get("payload", {}) or {}

    with Session(engine) as session:
        existed = session.exec(
            select(TraceEventRecord).where(TraceEventRecord.event_id == event_id)
        ).first()
        if existed:
            return

        record = TraceEventRecord(
            trace_id=trace_id,
            event_id=event_id,
            ts=_parse_iso_ts(event.get("ts")),
            node=str(event.get("node", "") or "unknown"),
            event_type=event_type,
            severity=str(event.get("severity", "info") or "info"),
            payload=payload if isinstance(payload, dict) else {"raw": payload},
        )
        session.add(record)

        run = session.exec(
            select(TraceRun).where(TraceRun.trace_id == trace_id)
        ).first()
        if not run:
            run = TraceRun(trace_id=trace_id)
            session.add(run)

        if event_type == "agent_run_started":
            run.status = "running"
            run.started_at = _parse_iso_ts(event.get("ts"))
            run.session_id = payload.get("session_id")
            run.goal = payload.get("goal")
        elif event_type == "agent_run_completed":
            run.status = "completed"
            run.completed_at = _parse_iso_ts(event.get("ts"))
            run.response_length = payload.get("response_length")
        elif event_type == "agent_run_failed":
            run.status = "failed"
            run.completed_at = _parse_iso_ts(event.get("ts"))
            run.run_metadata = {
                **(run.run_metadata or {}),
                "error": payload.get("error")
            }

        run.updated_at = datetime.utcnow()
        session.commit()


def append_trace_event(event: dict):
    """将结构化追踪事件写入 sink（jsonl/db/both），供回放与复盘。"""
    try:
        mode = os.getenv("TRACE_SINK_MODE", "both").strip().lower()
        if mode not in {"jsonl", "db", "both"}:
            mode = "both"
        if mode in {"jsonl", "both"}:
            _write_trace_to_jsonl(event)
        if mode in {"db", "both"}:
            _write_trace_to_db(event)
    except Exception as e:
        logger.error(f"写入 trace 事件失败: {e}")

def log_debug_html(query, html_content):
    """专门用于记录搜索抓取的 HTML 内容以供排查"""
    debug_file = os.path.join(LOG_DIR, f"debug_search_{datetime.now().strftime('%H%M%S')}.html")
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(f"<!-- Query: {query} -->\n")
        f.write(html_content)
    logger.info(f"搜索原始 HTML 已保存至: {debug_file}")
    return debug_file
