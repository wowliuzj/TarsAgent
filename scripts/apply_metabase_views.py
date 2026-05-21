#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from sqlmodel import Session
from sqlalchemy import text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.db import engine


def main():
    sql_file = Path(__file__).with_name("metabase_trace_views.sql")
    if not sql_file.exists():
        raise SystemExit(f"SQL file not found: {sql_file}")

    sql = sql_file.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
    if not statements:
        print("No SQL statements found.")
        return

    with Session(engine) as session:
        for stmt in statements:
            session.execute(text(stmt))
        session.commit()

    print(f"Applied {len(statements)} statements from {sql_file}")


if __name__ == "__main__":
    main()
