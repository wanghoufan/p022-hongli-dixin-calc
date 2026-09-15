#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 连接工厂与运行参数（D1）。

约定（见 docs/sop/sqlite.md 与 PRODUCT_PLAN_V1.0）：
- 一个项目一个独立 .db；开发库默认 <项目根>/dev.db，可用环境变量切换。
- 正式库路径（含 DockerData / DockerBackups）不得由本模块自动创建，除非显式放行。
- foreign_keys=ON、journal_mode=WAL、busy_timeout=5000ms、synchronous=NORMAL。
- 浏览器不得直接访问 .db，只能经 HTTP API。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_FILENAME = "dev.db"
DEFAULT_BUSY_TIMEOUT_MS = 5000
ENV_DB_PATH = "DIVIDEND_LEDGER_DB"
ENV_ALLOW_PROD = "DIVIDEND_LEDGER_ALLOW_PROD"

PROD_PATH_MARKERS = ("DockerData", "DockerBackups")
PROD_DB_MARKERS = ("docker", "prod", "production")
READONLY_SUFFIXES = (".db", ".sqlite", ".sqlite3")


class LedgerError(Exception):
    """业务/校验错误，携带 HTTP 状态码，由 API 层转成 JSON。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def resolve_db_path(db_path: str | None = None) -> Path:
    if db_path:
        return Path(db_path).expanduser().resolve()
    env = os.environ.get(ENV_DB_PATH) or os.environ.get("SQLITE_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return (ROOT / DEFAULT_DB_FILENAME).resolve()


def is_production_like(path: Path) -> bool:
    parts = path.parts
    if any(marker in parts for marker in PROD_PATH_MARKERS):
        return True
    return any(marker in path.name.lower() for marker in PROD_DB_MARKERS)


def guard_path(path: Path) -> None:
    """未授权时不得创建/打开正式库（审批通过后可用环境变量显式放行）。"""
    if is_production_like(path) and os.environ.get(ENV_ALLOW_PROD) != "1":
        raise LedgerError(
            "拒绝操作疑似正式数据库路径（未经授权）：%s；"
            "确需操作请显式设置 %s=1" % (path, ENV_ALLOW_PROD),
            status=403,
        )


def apply_pragmas(conn: sqlite3.Connection, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = %d" % int(busy_timeout_ms))
    conn.execute("PRAGMA synchronous = NORMAL")


def connect(db_path: str | None = None, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
            create: bool = True) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    if create:
        guard_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise LedgerError("数据库不存在：%s" % path, status=404)
    conn = sqlite3.connect(
        str(path),
        timeout=max(0.1, busy_timeout_ms / 1000.0),
        isolation_level=None,  # autocommit；事务由 write_tx / 显式语句控制
    )
    conn.row_factory = sqlite3.Row
    try:
        apply_pragmas(conn, busy_timeout_ms)
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise LedgerError("SQLite 打开失败：%s" % exc, status=500)
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection):
    """单写事务：BEGIN IMMEDIATE 立即取写锁，busy_timeout 内等待，超时转 503。

    所有写操作必须走这里；禁止在事务内做网络/IO 等长耗时动作。
    """
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        raise LedgerError("数据库繁忙（无法获取写锁）：%s" % exc, status=503)
    try:
        yield conn
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    else:
        try:
            conn.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise LedgerError("提交失败：%s" % exc, status=503)


def pragma_snapshot(conn: sqlite3.Connection) -> dict:
    def one(sql):
        try:
            row = conn.execute(sql).fetchone()
            return list(row)[0] if row is not None else None
        except sqlite3.Error:
            return None

    return {
        "journal_mode": one("PRAGMA journal_mode"),
        "foreign_keys": one("PRAGMA foreign_keys"),
        "busy_timeout_ms": one("PRAGMA busy_timeout"),
        "synchronous": one("PRAGMA synchronous"),
        "user_version": one("PRAGMA user_version"),
        "page_count": one("PRAGMA page_count"),
    }
