#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migration runner（Python 标准库 sqlite3，无第三方依赖）。

- 已发布 Migration 不回改；新结构新增文件。
- 每个 Migration 在单个 BEGIN IMMEDIATE 事务内执行，成功后才写入 schema_migrations
  并推进 PRAGMA user_version；失败整体回滚，不允许半成品结构。
- 版本表 schema_migrations 由 runner 先引导创建（与 0001 中定义一致，IF NOT EXISTS）。

CLI：
    python3 -m db.migrate --status
    python3 -m db.migrate                 # 应用所有未执行 Migration
    python3 -m db.migrate --db /tmp/x.db --dry-run
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):  # 允许 python3 db/migrate.py 直接运行
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from db.connection import connect, pragma_snapshot, resolve_db_path
else:
    from .connection import connect, pragma_snapshot, resolve_db_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
TZ8 = timezone(timedelta(hours=8))
MIGRATION_RE = re.compile(r"^(\d+)_([A-Za-z0-9_\-]+)\.sql$")

REGISTRY_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "  version    INTEGER PRIMARY KEY,"
    "  name       TEXT    NOT NULL,"
    "  applied_at TEXT    NOT NULL"
    ")"
)


def now_cn() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")


def split_statements(sql: str) -> list[str]:
    """按 sqlite3 官方 tokenizer 切分语句，正确处理触发器 BEGIN...END 内部的分号。"""
    stmts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines(True):
        buf.append(line)
        chunk = "".join(buf)
        if sqlite3.complete_statement(chunk):
            if chunk.strip():
                stmts.append(chunk.strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def ensure_registry(conn: sqlite3.Connection) -> None:
    conn.execute(REGISTRY_DDL)


def discover_migrations(migrations_dir: Path | None = None) -> list[dict]:
    base = Path(migrations_dir) if migrations_dir else MIGRATIONS_DIR
    out: list[dict] = []
    if not base.is_dir():
        return out
    for path in sorted(base.iterdir()):
        m = MIGRATION_RE.match(path.name)
        if not m:
            continue
        out.append({"version": int(m.group(1)), "name": m.group(2), "path": path})
    out.sort(key=lambda x: x["version"])
    versions = [x["version"] for x in out]
    if len(set(versions)) != len(versions):
        raise RuntimeError("Migration 版本号重复：%s" % versions)
    return out


def applied_migrations(conn: sqlite3.Connection) -> list[dict]:
    ensure_registry(conn)
    rows = conn.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [dict(r) for r in rows]


def pending_migrations(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[dict]:
    done = {r["version"] for r in applied_migrations(conn)}
    return [m for m in discover_migrations(migrations_dir) if m["version"] not in done]


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path | None = None,
                     dry_run: bool = False) -> list[dict]:
    ensure_registry(conn)
    done = {r["version"] for r in applied_migrations(conn)}
    applied: list[dict] = []
    for mig in discover_migrations(migrations_dir):
        if mig["version"] in done:
            continue
        sql = mig["path"].read_text(encoding="utf-8")
        stmts = split_statements(sql)
        if dry_run:
            applied.append({"version": mig["version"], "name": mig["name"],
                            "statements": len(stmts), "dry_run": True})
            continue
        try:
            conn.execute("BEGIN IMMEDIATE")
            for stmt in stmts:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                (mig["version"], mig["name"], now_cn()),
            )
            conn.execute("PRAGMA user_version = %d" % mig["version"])
            conn.execute("COMMIT")
        except (sqlite3.Error, RuntimeError) as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise RuntimeError("Migration %s 失败已回滚：%s" % (mig["path"].name, exc)) from exc
        applied.append({"version": mig["version"], "name": mig["name"],
                        "statements": len(stmts), "dry_run": False})
    return applied


def migration_status(conn: sqlite3.Connection) -> dict:
    return {
        "user_version": pragma_snapshot(conn).get("user_version"),
        "applied": applied_migrations(conn),
        "pending": [{"version": m["version"], "name": m["name"]}
                    for m in pending_migrations(conn)],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SQLite Migration runner（D1）")
    ap.add_argument("--db", default=None, help="数据库路径（默认 ./dev.db 或环境变量）")
    ap.add_argument("--status", action="store_true", help="只打印版本状态")
    ap.add_argument("--dry-run", action="store_true", help="只列出待执行语句数，不落库")
    args = ap.parse_args(argv)

    path = resolve_db_path(args.db)
    print("数据库：%s" % path)
    conn = connect(path, create=not args.status)
    try:
        if args.status:
            print("迁移状态：%s" % migration_status(conn))
            print("运行参数：%s" % pragma_snapshot(conn))
            return 0
        applied = apply_migrations(conn, dry_run=args.dry_run)
        if not applied:
            print("无待执行 Migration（已是最新）。")
        for item in applied:
            print("完成 %s_%s（%s 条语句）" % (item["version"], item["name"],
                                            item["statements"]))
        print("迁移状态：%s" % migration_status(conn))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
