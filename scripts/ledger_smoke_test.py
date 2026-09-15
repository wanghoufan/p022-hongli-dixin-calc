#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1 实测矩阵 + V1.2 回归（只使用系统临时目录里的开发库；绝不触碰正式库/生产目录）。

覆盖：
  1) Migration / schema.sql 等价 / 版本表 / PRAGMA
  2) 账本业务语义（confirmed 语义、整手、禁止裸空、持仓重建、现金追加式、不可变护栏、幂等）
  3) 双连接读写、写锁等待（busy_timeout）、短超时确实失败、WAL 读并发
  4) WAL checkpoint、进程重启后持久化
  5) .backup / VACUUM INTO 备份 + 隔离恢复 + integrity_check / foreign_key_check
  6) HTTP API：旧接口语义不变 + 新 /api/ledger/* + 静态服务不泄漏 .db
  D3) 下单执行闭环：CLOSED 后三写 409 / revise 防改写 / 四态机 / 完成门禁 / 重启后进度恢复
  D4) 估值回撤双源核验（正常/缺日/超差/负例）+ 行情三路状态字段契约 + 页面契约回归
  D5) 非当前成分（STALE_CONSTITUENT）处理 + P1-1 行情恢复条件（连续 2 次/窗口过期/
      坏 dataDate 不计数）+ P1-2 seeded 随机 20 抽样 + 持仓页 API/页面契约

用法：python3 scripts/ledger_smoke_test.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.connection import LedgerError, connect, write_tx  # noqa: E402
from db.migrate import apply_migrations, split_statements  # noqa: E402
from db.service import DELETE_CONFIRM_TEXT, LedgerService  # noqa: E402
from db.valution import drawdown_board  # noqa: E402
from db import valution  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""))
    return bool(ok)


def free_port(preferred: int = 8799) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free port")


def fingerprint(conn: sqlite3.Connection) -> dict:
    """结构指纹：忽略 IF NOT EXISTS 与空白差异，用于校验 schema.sql 与 migrations 等价。"""
    out = {}
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for r in rows:
        norm = " ".join((r[2] or "").replace("IF NOT EXISTS", " ").split())
        norm = re.sub(r"\s*([(),;])\s*", r"\1", norm)
        out["%s:%s" % (r[0], r[1])] = norm
    return out


def counts(conn: sqlite3.Connection) -> dict:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in tables}


def http(method: str, path: str, body=None, timeout: int = 15):
    url = "http://127.0.0.1:%d%s" % (PORT, path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def http_json(method: str, path: str, body=None):
    status, ctype, raw = http(method, path, body)
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, {"_raw": raw[:200].decode("utf-8", "replace")}


def http_port(port: int, method: str, path: str, body=None, timeout: int = 15):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def http_json_port(port: int, method: str, path: str, body=None, timeout: int = 15):
    status, ctype, raw = http_port(port, method, path, body, timeout)
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, {"_raw": raw[:200].decode("utf-8", "replace")}


PORT = free_port()
TMP = Path(tempfile.mkdtemp(prefix="d1-ledger-matrix-"))
DB = TMP / "matrix.dev.db"
D2DB = TMP / "d2-plans.dev.db"
D3DB = TMP / "d3-execution.dev.db"
D5DB = TMP / "d5-holdings.dev.db"
D7DB = TMP / "d7-delete.dev.db"
D8DB = TMP / "d8-revert.dev.db"
D3_STATE: dict = {}
print("临时目录：%s" % TMP)
print("服务端口：%d" % PORT)

# ---------------------------------------------- D2 夹具（全部虚构，可清除）
D2_PRICES = {"600111": 1370, "600222": 2260, "600333": 845}  # 单位：分
D2_WEIGHTS = [("600111", 40.5, "SH"), ("600222", 35.5, "SH"), ("600333", 24.0, "SZ")]
D2_NAMES = {"600111": "虚构甲", "600222": "虚构乙", "600333": "虚构丙"}
D2_QUOTE_TIME = "2026-09-15T20:00:00+08:00"

# D5 夹具：600999 不在 D2 权重成分 universe 内（虚构退指样例，可清除）
D5_STALE_CODE = "600999"
D5_PRICES = {**D2_PRICES, D5_STALE_CODE: 500}


def d2_body(kind, cycle_id, capital_cents, prices=None, source="腾讯主源"):
    prices = D2_PRICES if prices is None else prices
    return {
        "cycle_id": cycle_id, "kind": kind, "capital_cents": capital_cents,
        "weight_version": "H30269-closeweight-2026-08-31", "weight_date": "2026-08-31",
        "quote_source": source, "quote_fetched_at": D2_QUOTE_TIME,
        "weights": [{"code": c, "name": D2_NAMES[c], "market": m, "weight": w}
                    for c, w, m in D2_WEIGHTS],
        "quotes": [{"code": c, "price_cents": p, "source": source, "fetched_at": D2_QUOTE_TIME}
                   for c, p in prices.items()],
    }


def d2_invariant(plan) -> bool:
    rows = plan["rows"]
    row_ok = all(r["deviation_cents"] == r["actual_amount_cents"] - r["target_amount_cents"]
                 for r in rows)
    tsum = sum(r["target_amount_cents"] for r in rows)
    asum = sum(r["actual_amount_cents"] for r in rows)
    t = plan["totals"]
    return bool(row_ok and t["target_total_cents"] == tsum and t["actual_total_cents"] == asum
                and t["deviation_total_cents"] == asum - tsum)


# ------------------------------------------------------------------ 1) Migration
def test_migration() -> None:
    conn = connect(str(DB))
    applied = apply_migrations(conn)
    check("1.1 首次迁移应用（v1 init + v2 test_batch_delete + v3 revert）",
          [a["version"] for a in applied] == [1, 2, 3], applied)
    st = conn.execute("SELECT version, name FROM schema_migrations").fetchall()
    check("1.2 版本表记录（v1+v2+v3）", [r["version"] for r in st] == [1, 2, 3], [dict(x) for x in st])
    check("1.3 user_version=3", conn.execute("PRAGMA user_version").fetchone()[0] == 3)
    check("1.4 journal_mode=WAL",
          str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal")
    check("1.5 foreign_keys=ON", conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
    check("1.6 busy_timeout=5000", conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000)
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    need = {"schema_migrations", "cycles", "batches", "order_items", "transactions",
            "cash_ledger", "ledger_audit", "ledger_batch_deletions", "ledger_reverts"}
    check("1.7 五张业务表+版本表+审计表齐全", need <= names, sorted(need - names))
    views = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    check("1.8 重建视图存在", {"v_holdings", "v_cash_balance"} <= views, sorted(views))
    trig = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")]
    check("1.9 不可变/追加式触发器", len(trig) == 4, trig)

    again = apply_migrations(conn)
    check("1.10 重复迁移幂等（无待执行）", again == [], again)

    schema_db = TMP / "schema-only.db"
    sconn = sqlite3.connect(str(schema_db))
    sconn.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
    sconn.execute("PRAGMA foreign_keys = ON")
    check("1.11 schema.sql 可独立建库", fingerprint(sconn) == fingerprint(conn),
          "结构指纹不一致" if fingerprint(sconn) != fingerprint(conn) else "结构等价")
    check("1.12 schema.sql user_version=3",
          sconn.execute("PRAGMA user_version").fetchone()[0] == 3)
    sconn.close()
    conn.close()


# ------------------------------------------------------- 2) 账本业务语义
def test_semantics() -> None:
    svc = LedgerService(str(DB))
    cycle = svc.create_cycle({"name": "演示周期A", "note": "D1 虚构可清除"})["cycle"]
    cid = cycle["cycle_id"]
    batch = svc.create_batch({"cycle_id": cid, "kind": "INITIAL", "algorithm_version": "d1-0"})["batch"]
    item = svc.create_order_item({"batch_id": batch["batch_id"], "code": "600519",
                                  "name": "虚构股票", "market": "SH", "side": "BUY",
                                  "target_weight": 3.5, "suggested_qty": 100,
                                  "reference_price_cents": 150000})["order_item"]
    check("2.1 cycle/batch/order_item 写入", cid > 0 and batch["batch_id"] > 0
          and item["order_item_id"] > 0, {"cycle": cid, "batch": batch["batch_id"]})

    for label, payload in (
        ("2.2 confirmed=false 拒绝",
         {"cycle_id": cid, "code": "600519", "side": "BUY", "qty": 100, "price_cents": 150000}),
        ("2.3 非整手 150 股拒绝",
         {"cycle_id": cid, "code": "600519", "side": "BUY", "qty": 150, "price_cents": 150000,
          "confirmed": True}),
        ("2.4 缺价缺额拒绝",
         {"cycle_id": cid, "code": "600519", "side": "BUY", "qty": 100, "confirmed": True}),
        ("2.5 amount 与 price*qty 不一致拒绝",
         {"cycle_id": cid, "code": "600519", "side": "BUY", "qty": 100, "price_cents": 150000,
          "amount_cents": 1, "confirmed": True}),
    ):
        try:
            svc.record_transaction(dict(payload))
            check(label, False, "未被拒绝")
        except LedgerError as exc:
            check(label, exc.status == 400, exc.message)

    tx1 = svc.record_transaction({"cycle_id": cid, "batch_id": batch["batch_id"],
                                  "order_item_id": item["order_item_id"], "code": "600519",
                                  "name": "虚构股票", "side": "BUY", "qty": 200,
                                  "price_cents": 150000, "confirmed": True,
                                  "idempotency_key": "demo-buy-1"})
    check("2.6 confirmed 买入入账", tx1["transaction"]["confirmed"] == 1,
          tx1["transaction"]["transaction_id"])
    check("2.7 买入自动现金事件为负",
          tx1["cash_event"]["amount_cents"] == -30000000 and tx1["balance_cents"] == -30000000,
          tx1["cash_event"]["amount_cents"])

    replay = svc.record_transaction({"cycle_id": cid, "code": "600519", "side": "BUY", "qty": 200,
                                     "price_cents": 150000, "confirmed": True,
                                     "idempotency_key": "demo-buy-1"})
    check("2.8 幂等键重放不重复入账",
          replay.get("idempotent_replay") is True
          and len(svc.list_transactions(cycle_id=cid)["transactions"]) == 1)

    h = svc.holdings(cycle_id=cid)["holdings"]
    check("2.9 持仓由 confirmed 重建", len(h) == 1 and h[0]["qty"] == 200
          and h[0]["avg_cost_cents"] == 150000, h)

    try:
        svc.record_transaction({"cycle_id": cid, "code": "600519", "side": "SELL", "qty": 300,
                                "price_cents": 160000, "confirmed": True})
        check("2.10 超卖（裸空）拒绝", False, "未被拒绝")
    except LedgerError as exc:
        check("2.10 超卖（裸空）拒绝", exc.status == 409, exc.message)

    svc.record_transaction({"cycle_id": cid, "code": "600519", "side": "SELL", "qty": 200,
                            "price_cents": 160000, "confirmed": True})
    h = svc.holdings(cycle_id=cid)["holdings"]
    check("2.11 清仓后净额归零且不列持仓", h == [], h)
    txs = svc.list_transactions(cycle_id=cid)["transactions"]
    check("2.12 归零仍保留全部交易事实（可追溯）", len(txs) == 2, len(txs))
    bal = svc.list_cash(cycle_id=cid)["balance_cents"]
    check("2.13 现金余额=卖出-买入", bal == -30000000 + 32000000, bal)

    dep = svc.append_cash({"cycle_id": cid, "event_type": "DEPOSIT", "amount_cents": 50000000})
    check("2.14 追加现金事件", dep["balance_cents"] == bal + 50000000, dep["balance_cents"])
    try:
        svc.append_cash({"cycle_id": cid, "event_type": "DEPOSIT", "amount_cents": -1})
        check("2.15 现金符号校验（DEPOSIT 必须为正）", False, "未被拒绝")
    except LedgerError as exc:
        check("2.15 现金符号校验（DEPOSIT 必须为正）", exc.status == 400, exc.message)

    events = svc.list_cash(cycle_id=cid)["cash_events"]
    check("2.16 现金为逐事件账本（含交易自动事件）", len(events) == 3, len(events))

    # 不可变 / 追加式护栏（直连 SQL 尝试破坏）
    conn = connect(str(DB))
    try:
        conn.execute("UPDATE transactions SET qty = 100 WHERE transaction_id = ?",
                     (tx1["transaction"]["transaction_id"],))
        check("2.17 已确认交易不可改写", False, "UPDATE 未被阻止")
    except sqlite3.IntegrityError as exc:
        check("2.17 已确认交易不可改写", "immutable" in str(exc), str(exc))
    for label, sql in (
        ("2.18 transactions 不可 DELETE", "DELETE FROM transactions WHERE transaction_id = ?"),
        ("2.19 cash_ledger 不可 DELETE", "DELETE FROM cash_ledger WHERE cash_event_id = ?"),
        ("2.20 cash_ledger 不可 UPDATE", "UPDATE cash_ledger SET amount_cents = 1 WHERE cash_event_id = ?"),
    ):
        try:
            conn.execute(sql, (1,))
            check(label, False, "未被阻止")
        except sqlite3.IntegrityError as exc:
            check(label, "append-only" in str(exc), str(exc))
    try:
        conn.execute("INSERT INTO transactions (cycle_id, code, side, qty, amount_cents, "
                     "confirmed, confirmed_at, created_at, updated_at) "
                     "VALUES (999999, '600519', 'BUY', 100, 1, 1, 'x', 'x', 'x')")
        check("2.21 外键约束拦截孤儿交易", False, "未被阻止")
    except sqlite3.IntegrityError as exc:
        check("2.21 外键约束拦截孤儿交易", "FOREIGN KEY" in str(exc).upper(), str(exc))
    try:
        svc.record_transaction({"cycle_id": 999999, "code": "600519", "side": "BUY", "qty": 100,
                                "price_cents": 100, "confirmed": True})
        check("2.22 未知 cycle 返回 404", False, "未被拒绝")
    except LedgerError as exc:
        check("2.22 未知 cycle 返回 404", exc.status == 404, exc.message)
    conn.close()


# ------------------------------------------------------- 3) 并发 / 锁
def test_concurrency() -> None:
    lock_db = TMP / "lock.dev.db"
    c0 = connect(str(lock_db))
    apply_migrations(c0)
    c0.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
               "VALUES ('并发探测','OPEN','', 'x','x')")
    c0.close()

    holder = connect(str(lock_db), busy_timeout_ms=5000)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
                   "VALUES ('持锁者','OPEN','', 'x','x')")

    reader = connect(str(lock_db), busy_timeout_ms=5000)
    try:
        n = reader.execute("SELECT COUNT(*) FROM cycles").fetchone()[0]
        check("3.1 WAL 下写锁不阻塞读", n >= 1, "读到 %d 行" % n)
    except sqlite3.Error as exc:
        check("3.1 WAL 下写锁不阻塞读", False, str(exc))

    result: dict = {}

    def waiter():
        cw = connect(str(lock_db), busy_timeout_ms=5000)
        try:
            t0 = time.time()
            with write_tx(cw):
                cw.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
                           "VALUES ('等待者','OPEN','', 'x','x')")
            result["elapsed"] = time.time() - t0
            result["ok"] = True
        except Exception as exc:  # pragma: no cover
            result["ok"] = False
            result["error"] = str(exc)
        finally:
            cw.close()

    th = threading.Thread(target=waiter)
    th.start()
    time.sleep(0.8)
    holder.execute("COMMIT")
    th.join(10)
    check("3.2 busy_timeout 内等待而非立即失败",
          result.get("ok") and result.get("elapsed", 0) >= 0.6,
          {"ok": result.get("ok"), "elapsed": round(result.get("elapsed", 0), 3),
           "error": result.get("error")})
    check("3.3 双连接写入均落库",
          holder.execute("SELECT COUNT(*) FROM cycles").fetchone()[0] == 3)
    reader.close()

    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
                   "VALUES ('再次持锁','OPEN','', 'x','x')")
    short = connect(str(lock_db), busy_timeout_ms=100)
    t0 = time.time()
    try:
        with write_tx(short):
            short.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
                          "VALUES ('超时者','OPEN','', 'x','x')")
        check("3.4 busy_timeout 耗尽后明确失败（不静默）", False, "未超时")
    except LedgerError as exc:
        check("3.4 busy_timeout 耗尽后明确失败（不静默）",
              exc.status == 503 and (time.time() - t0) < 3, exc.message)
    finally:
        short.close()
        holder.execute("COMMIT")
        holder.close()


# ---------------------------------------------- 4) WAL checkpoint / 重启持久化
def test_wal_and_restart() -> None:
    wal_db = TMP / "wal.dev.db"
    conn = connect(str(wal_db))
    apply_migrations(conn)
    for i in range(50):
        conn.execute("INSERT INTO cycles (name, status, note, created_at, updated_at) "
                     "VALUES (?, 'OPEN','','x','x')", ("WAL-%d" % i,))
    wal_path = Path(str(wal_db) + "-wal")
    check("4.1 写入后存在 -wal 文件", wal_path.exists() and wal_path.stat().st_size > 0,
          wal_path.stat().st_size if wal_path.exists() else "缺失")
    row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    check("4.2 WAL checkpoint(TRUNCATE) 成功", row is not None, list(row) if row else None)
    check("4.3 checkpoint 后 -wal 归零", not wal_path.exists() or wal_path.stat().st_size == 0,
          wal_path.stat().st_size if wal_path.exists() else 0)
    check("4.4 checkpoint 后数据可读",
          conn.execute("SELECT COUNT(*) FROM cycles").fetchone()[0] == 50)
    conn.close()

    probe = "重启持久化探测"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from db.service import LedgerService\n"
        "s = LedgerService(%r)\n"
        "print(s.create_cycle({'name': %r})['cycle']['cycle_id'])\n"
    ) % (str(ROOT), str(wal_db), probe)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    check("4.5 独立进程写入成功", proc.returncode == 0, proc.stderr.strip()[:200])

    conn2 = connect(str(wal_db))
    names = [r["name"] for r in conn2.execute("SELECT name FROM cycles")]
    check("4.6 进程重启后数据仍在", probe in names and len(names) == 51, len(names))
    closed = conn2.execute("PRAGMA integrity_check").fetchall()
    check("4.7 integrity_check=ok", [list(r)[0] for r in closed] == ["ok"],
          [list(r)[0] for r in closed])
    conn2.close()


# ------------------------------------------------------------- 5) 备份 / 恢复
def test_backup_restore() -> None:
    src = connect(str(DB))
    baseline = counts(src)
    src.close()

    cli = shutil.which("sqlite3")
    bkp = TMP / "backup-cli.db"
    if cli:
        p = subprocess.run([cli, str(DB), ".backup '%s'" % bkp], capture_output=True, text=True)
        check("5.1 .backup（sqlite3 CLI）成功", p.returncode == 0 and bkp.exists(),
              p.stderr.strip()[:200])
    else:
        c = sqlite3.connect(str(DB))
        d = sqlite3.connect(str(bkp))
        c.backup(d)
        c.close()
        d.close()
        check("5.1 .backup（stdlib backup API）成功", bkp.exists(), "sqlite3 CLI 缺失，用 API 兜底")

    vac = TMP / "backup-vacuum.db"
    conn = sqlite3.connect(str(DB))
    conn.execute("VACUUM INTO ?", (str(vac),))
    conn.close()
    check("5.2 VACUUM INTO 成功", vac.exists() and vac.stat().st_size > 0, vac.stat().st_size)

    for label, path in (("5.3 .backup 副本", bkp), ("5.4 VACUUM INTO 副本", vac)):
        check("%s 无 WAL 残留（备份产物单文件边界）" % label,
              not Path(str(path) + "-wal").exists() and not Path(str(path) + "-shm").exists())
        c = sqlite3.connect(str(path))
        integ = [list(r)[0] for r in c.execute("PRAGMA integrity_check").fetchall()]
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
        same = counts(c) == baseline
        c.close()
        check("%s integrity=ok / fk 违规=0 / 行数一致" % label,
              integ == ["ok"] and len(fk) == 0 and same,
              {"integrity": integ, "fk": len(fk), "row_counts_match": same})

    restore_dir = TMP / "restore-tests"
    restore_dir.mkdir(exist_ok=True)
    restored = restore_dir / "restored-dividend-portfolio.db"
    shutil.copy2(bkp, restored)
    c = sqlite3.connect(str(restored))
    c.execute("PRAGMA foreign_keys = ON")
    integ = [list(r)[0] for r in c.execute("PRAGMA integrity_check").fetchall()]
    fk = c.execute("PRAGMA foreign_key_check").fetchall()
    cycles = c.execute("SELECT COUNT(*) FROM cycles").fetchone()[0]
    tx = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    cash = c.execute("SELECT SUM(amount_cents) FROM cash_ledger").fetchone()[0]
    c.close()
    check("5.5 隔离恢复后可读关键业务数据",
          integ == ["ok"] and len(fk) == 0 and cycles >= 1 and tx == 2 and cash is not None,
          {"cycles": cycles, "transactions": tx, "cash_sum": cash})


# ------------------------------------- D2) 四生命周期计划 / 冻结 revision / 不变量
def test_d2_plans() -> None:
    svc = LedgerService(str(D2DB))

    # ---- 首次建仓 INITIAL：10万 / 20万 ----
    c_init = svc.create_cycle({"name": "D2 首次建仓"})["cycle"]["cycle_id"]
    plan10 = svc.preview_batch(d2_body("INITIAL", c_init, 10_000_000))["plan"]
    by = {r["code"]: r for r in plan10["rows"]}
    check("D2.1 INITIAL 10万 生成三行计划", len(plan10["rows"]) == 3, len(plan10["rows"]))
    check("D2.2 INITIAL 10万 按权重+100股整手取整",
          [by["600111"]["suggested_qty"], by["600222"]["suggested_qty"],
           by["600333"]["suggested_qty"]] == [2900, 1500, 2800],
          {c: by[c]["suggested_qty"] for c in by})
    check("D2.3 INITIAL 10万 理论目标/实际投入/行偏差",
          by["600111"]["target_amount_cents"] == 4_050_000
          and by["600111"]["actual_amount_cents"] == 3_973_000
          and by["600111"]["deviation_cents"] == -77_000, by["600111"])
    check("D2.4 INITIAL 10万 总额与偏差和",
          plan10["totals"]["target_total_cents"] == 10_000_000
          and plan10["totals"]["actual_total_cents"] == 9_729_000
          and plan10["totals"]["deviation_total_cents"] == -271_000
          and plan10["totals"]["leftover_cents"] == 271_000, plan10["totals"])
    check("D2.5 INITIAL 透明字段（权重版本/日期、行情来源/时间、算法版本）",
          plan10["weight_version"] == "H30269-closeweight-2026-08-31"
          and plan10["weight_date"] == "2026-08-31" and plan10["quote_source"] == "腾讯主源"
          and plan10["quote_fetched_at"] == D2_QUOTE_TIME
          and plan10["algorithm_version"] == "d2-1",
          {k: plan10[k] for k in ("weight_version", "quote_source", "algorithm_version")})
    check("D2.6 数学不变量：逐行+总额双校验（10万）", d2_invariant(plan10))

    plan20 = svc.preview_batch(d2_body("INITIAL", c_init, 20_000_000))["plan"]
    by20 = {r["code"]: r for r in plan20["rows"]}
    check("D2.7 INITIAL 20万 股数与偏差",
          [by20["600111"]["suggested_qty"], by20["600222"]["suggested_qty"],
           by20["600333"]["suggested_qty"]] == [5900, 3100, 5600]
          and plan20["totals"]["actual_total_cents"] == 19_821_000
          and plan20["totals"]["deviation_total_cents"] == -179_000, plan20["totals"])
    check("D2.8 数学不变量：逐行+总额双校验（20万）", d2_invariant(plan20))

    # ---- 追加投资 ADD：持仓市值+策略现金+新增资金，低配优先/超配0/默认不卖 ----
    c_add = svc.create_cycle({"name": "D2 追加投资"})["cycle"]["cycle_id"]
    svc.append_cash({"cycle_id": c_add, "event_type": "DEPOSIT", "amount_cents": 12_330_000})
    svc.record_transaction({"cycle_id": c_add, "code": "600111", "name": "虚构甲", "side": "BUY",
                            "qty": 9000, "price_cents": 1370, "confirmed": True})
    plan_add = svc.preview_batch(d2_body("ADD", c_add, 10_000_000))["plan"]
    add = {r["code"]: r for r in plan_add["rows"]}
    check("D2.9 ADD 持仓市值+策略现金+新增资金=目标总额",
          plan_add["totals"]["holding_value_cents"] == 12_330_000
          and plan_add["totals"]["cash_balance_cents"] == 0
          and plan_add["totals"]["portfolio_total_cents"] == 22_330_000
          and plan_add["totals"]["investable_cents"] == 10_000_000, plan_add["totals"])
    check("D2.10 ADD 超配 0 股且默认不卖（无 SELL 行）",
          add["600111"]["suggested_qty"] == 0
          and not any(r["side"] == "SELL" for r in plan_add["rows"]),
          {r["code"]: r["side"] for r in plan_add["rows"]})
    check("D2.11 ADD 低配优先：乙先补足、丙受可投资金限制",
          add["600222"]["suggested_qty"] == 3500
          and add["600222"]["actual_amount_cents"] == 7_910_000
          and add["600333"]["suggested_qty"] == 2400
          and add["600333"]["actual_amount_cents"] == 2_028_000,
          {c: add[c]["suggested_qty"] for c in add})
    check("D2.12 ADD 实际投入<=可投资金 且不变量成立",
          plan_add["totals"]["actual_total_cents"] <= plan_add["totals"]["investable_cents"]
          and d2_invariant(plan_add), plan_add["totals"])
    check("D2.13 ADD 为预览：不落批次/不写交易",
          len(svc.list_transactions(cycle_id=c_add)["transactions"]) == 1
          and len(svc.list_batches(c_add)["batches"]) == 0)

    # ---- 全面再平衡 REBALANCE：只生成 BUY/SELL 计划不执行 ----
    c_reb = svc.create_cycle({"name": "D2 全面再平衡"})["cycle"]["cycle_id"]
    svc.append_cash({"cycle_id": c_reb, "event_type": "DEPOSIT", "amount_cents": 14_305_000})
    for code, qty, price in (("600111", 9000, 1370), ("600222", 500, 2260), ("600333", 1000, 845)):
        svc.record_transaction({"cycle_id": c_reb, "code": code, "name": D2_NAMES[code],
                                "side": "BUY", "qty": qty, "price_cents": price, "confirmed": True})
    plan_reb = svc.preview_batch(d2_body("REBALANCE", c_reb, 0))["plan"]
    reb = {r["code"]: r for r in plan_reb["rows"]}
    check("D2.14 REBALANCE 同时生成 BUY/SELL",
          reb["600111"]["side"] == "SELL" and reb["600222"]["side"] == "BUY"
          and reb["600333"]["side"] == "BUY", {c: reb[c]["side"] for c in reb})
    check("D2.15 REBALANCE 卖出不超持仓、买入整手",
          reb["600111"]["suggested_qty"] == 4700
          and reb["600111"]["actual_amount_cents"] == -6_439_000
          and reb["600222"]["suggested_qty"] == 1700
          and reb["600333"]["suggested_qty"] == 3000,
          {c: reb[c]["suggested_qty"] for c in reb})
    check("D2.16 REBALANCE 不变量成立 + 仅计划不执行",
          d2_invariant(plan_reb)
          and len(svc.list_transactions(cycle_id=c_reb)["transactions"]) == 3
          and len(svc.list_batches(c_reb)["batches"]) == 0)

    # ---- 清仓退出 EXIT：逐笔 SELL + 人工确认 + 周期关闭 ----
    c_exit = svc.create_cycle({"name": "D2 清仓退出"})["cycle"]["cycle_id"]
    svc.append_cash({"cycle_id": c_exit, "event_type": "DEPOSIT", "amount_cents": 14_305_000})
    for code, qty, price in (("600111", 9000, 1370), ("600222", 500, 2260), ("600333", 1000, 845)):
        svc.record_transaction({"cycle_id": c_exit, "code": code, "name": D2_NAMES[code],
                                "side": "BUY", "qty": qty, "price_cents": price, "confirmed": True})
    plan_exit = svc.preview_batch(d2_body("EXIT", c_exit, 0))["plan"]
    ex = {r["code"]: r for r in plan_exit["rows"]}
    check("D2.17 EXIT 逐笔 SELL 全仓、偏差为 0",
          all(r["side"] == "SELL" for r in plan_exit["rows"])
          and ex["600111"]["suggested_qty"] == 9000 and ex["600222"]["suggested_qty"] == 500
          and ex["600333"]["suggested_qty"] == 1000
          and plan_exit["totals"]["deviation_total_cents"] == 0, plan_exit["totals"])
    check("D2.18 EXIT 仅计划不执行（未确认前仍持仓）",
          len(svc.holdings(c_exit)["holdings"]) == 3)
    try:
        svc.close_cycle(c_exit)
        check("D2.19 未清仓拒绝关闭周期", False, "未被拒绝")
    except LedgerError as exc:
        check("D2.19 未清仓拒绝关闭周期", exc.status == 409, exc.message)
    for code, qty, price in (("600111", 9000, 1370), ("600222", 500, 2260), ("600333", 1000, 845)):
        svc.record_transaction({"cycle_id": c_exit, "code": code, "name": D2_NAMES[code],
                                "side": "SELL", "qty": qty, "price_cents": price, "confirmed": True})
    check("D2.20 人工逐笔确认后持仓归零", svc.holdings(c_exit)["holdings"] == [])
    closed = svc.close_cycle(c_exit)
    check("D2.21 清仓归零后周期关闭（CLOSED + closed_at）",
          closed["cycle"]["status"] == "CLOSED" and closed["cycle"]["closed_at"], closed["cycle"])
    summary = svc.cycle_summary(c_exit)
    check("D2.22 summary 关闭态 + 持仓重建为空 + 现金余额（清仓回款）",
          summary["cycle"]["status"] == "CLOSED" and summary["holdings"] == []
          and summary["cash_balance_cents"] == 14_305_000 and summary["transaction_count"] == 6,
          {"status": summary["cycle"]["status"], "cash": summary["cash_balance_cents"]})
    try:
        svc.create_batch({"cycle_id": c_exit, "kind": "INITIAL", "algorithm_version": "x"})
        check("D2.23 已关闭周期拒绝新批次", False, "未被拒绝")
    except LedgerError as exc:
        check("D2.23 已关闭周期拒绝新批次", exc.status == 409, exc.message)
    c_new = svc.create_cycle({"name": "D2 新周期"})["cycle"]["cycle_id"]
    check("D2.24 新投资新 cycle_id", c_new != c_exit and c_new > c_exit, (c_exit, c_new))

    # ---- 冻结快照 / revision / 已确认不可改写 / 刷新行情不改建议股数 ----
    c_frz = svc.create_cycle({"name": "D2 冻结与 revision"})["cycle"]["cycle_id"]
    frozen = svc.freeze_batch(d2_body("INITIAL", c_frz, 10_000_000))
    fbatch = frozen["batch"]["batch_id"]
    rev1 = {i["code"]: i for i in svc.list_order_items(fbatch, latest_only=True)["order_items"]}
    check("D2.25 freeze 落 order_items + revision=1 + FROZEN",
          frozen["batch"]["status"] == "FROZEN" and frozen["batch"]["revision"] == 1
          and bool(frozen["batch"]["frozen_at"]) and len(rev1) == 3
          and all(i["revision"] == 1 and i["status"] == "PENDING" for i in rev1.values()),
          {"status": frozen["batch"]["status"], "rev": frozen["batch"]["revision"]})
    check("D2.26 freeze 快照 plan_json 含透明字段",
          '"quote_source"' in (frozen["batch"]["plan_json"] or "")
          and '"algorithm_version"' in (frozen["batch"]["plan_json"] or ""))
    refreshed = d2_body("INITIAL", c_frz, 10_000_000,
                        prices={"600111": 1500, "600222": 2260, "600333": 845})
    p_new = svc.preview_batch(refreshed)["plan"]
    pn = {r["code"]: r for r in p_new["rows"]}
    stored = {i["code"]: i for i in svc.list_order_items(fbatch, latest_only=True)["order_items"]}
    check("D2.27 刷新行情不改已冻结建议股数",
          pn["600111"]["reference_price_cents"] == 1500
          and stored["600111"]["reference_price_cents"] == 1370
          and stored["600111"]["suggested_qty"] == 2900,
          {"preview_price": pn["600111"]["reference_price_cents"],
           "frozen_price": stored["600111"]["reference_price_cents"]})
    item_a = stored["600111"]
    svc.record_transaction({"cycle_id": c_frz, "batch_id": fbatch,
                            "order_item_id": item_a["order_item_id"], "code": "600111",
                            "name": "虚构甲", "side": "BUY", "qty": 100, "price_cents": 1370,
                            "confirmed": True})
    conf = [i for i in svc.list_order_items(fbatch, revision=1)["order_items"]
            if i["order_item_id"] == item_a["order_item_id"]][0]
    check("D2.28 人工确认成交后 order_item 标记 CONFIRMED", conf["status"] == "CONFIRMED",
          conf["status"])
    revised = svc.revise_batch(fbatch, refreshed)
    check("D2.29 revise 重算只增 revision=2",
          revised["batch"]["revision"] == 2
          and all(i["revision"] == 2 for i in revised["order_items"])
          and len(revised["order_items"]) == 3, {"rev": revised["batch"]["revision"]})
    conf_after = [i for i in svc.list_order_items(fbatch, revision=1)["order_items"]
                  if i["order_item_id"] == item_a["order_item_id"]][0]
    check("D2.30 已确认项不可改写（revision 1 原样保留）",
          conf_after["status"] == "CONFIRMED" and conf_after["revision"] == 1
          and conf_after["suggested_qty"] == 2900
          and conf_after["reference_price_cents"] == 1370, conf_after)
    check("D2.31 revise 后旧 revision 全保留、最新 revision 为 2",
          len(svc.list_order_items(fbatch)["order_items"]) == 6
          and len(svc.list_order_items(fbatch, latest_only=True)["order_items"]) == 3)

    try:
        svc.preview_batch(d2_body("INITIAL", c_frz, 10_000_000, prices={"600111": 1370}))
        check("D2.32 缺行情拒绝生成计划（不补造数）", False, "未被拒绝")
    except LedgerError as exc:
        check("D2.32 缺行情拒绝生成计划（不补造数）", exc.status == 400, exc.message)
    try:
        svc.freeze_batch(d2_body("INITIAL", c_exit, 10_000_000))
        check("D2.33 已关闭周期拒绝 freeze", False, "未被拒绝")
    except LedgerError as exc:
        check("D2.33 已关闭周期拒绝 freeze", exc.status == 409, exc.message)


# ------------------------------------- D3) 下单执行闭环：四态机 / 门禁 / P1×2 修复
def test_d3_flow() -> None:
    svc = LedgerService(str(D3DB))

    # ---- P1-1：CLOSED 周期后三写均 409 ----
    c_closed = svc.create_cycle({"name": "D3 关闭后写入防护"})["cycle"]["cycle_id"]
    frozen = svc.freeze_batch(d2_body("INITIAL", c_closed, 10_000_000))
    cl_batch = frozen["batch"]["batch_id"]
    cl_item = frozen["order_items"][0]["order_item_id"]
    svc.close_cycle(c_closed)  # 空仓可关
    for label, fn in (
        ("D3.1 close 后 record_transaction 409",
         lambda: svc.record_transaction({"cycle_id": c_closed, "code": "600111", "name": "虚构甲",
                                         "side": "BUY", "qty": 100, "price_cents": 1370,
                                         "confirmed": True})),
        ("D3.2 close 后 append_cash 409",
         lambda: svc.append_cash({"cycle_id": c_closed, "event_type": "DEPOSIT",
                                  "amount_cents": 100})),
        ("D3.3 close 后 create_order_item 409",
         lambda: svc.create_order_item({"batch_id": cl_batch, "code": "600111", "side": "BUY",
                                        "suggested_qty": 100})),
    ):
        try:
            fn()
            check(label, False, "未被拒绝")
        except LedgerError as exc:
            check(label, exc.status == 409, "%s | %s" % (exc.status, exc.message))
    try:
        svc.set_order_item_state(cl_item, {"status": "SKIPPED"})
        check("D3.3a close 后 order_item state 409", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.3a close 后 order_item state 409", exc.status == 409, exc.message)

    # ---- P1-2：revise 不得改写 kind / cycle_id ----
    c_rev = svc.create_cycle({"name": "D3 revise 防改写"})["cycle"]["cycle_id"]
    c_other = svc.create_cycle({"name": "D3 异 cycle"})["cycle"]["cycle_id"]
    rb = svc.freeze_batch(d2_body("INITIAL", c_rev, 10_000_000))["batch"]["batch_id"]
    try:
        svc.revise_batch(rb, dict(d2_body("EXIT", c_rev, 0), kind="EXIT"))
        check("D3.4 revise 传异 kind 拒绝（400）", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.4 revise 传异 kind 拒绝（400）", exc.status == 400, exc.message)
    try:
        svc.revise_batch(rb, dict(d2_body("INITIAL", c_other, 10_000_000), cycle_id=c_other))
        check("D3.5 revise 传异 cycle_id 拒绝（400）", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.5 revise 传异 cycle_id 拒绝（400）", exc.status == 400, exc.message)
    rev_ok = svc.revise_batch(rb, d2_body("INITIAL", c_rev, 10_000_000))
    check("D3.6 revise 缺省 kind/cycle 被强制为原批次值",
          rev_ok["batch"]["kind"] == "INITIAL" and rev_ok["plan"]["kind"] == "INITIAL"
          and rev_ok["plan"]["cycle_id"] == c_rev and rev_ok["batch"]["revision"] == 2,
          {"kind": rev_ok["plan"]["kind"], "cycle": rev_ok["plan"]["cycle_id"]})

    # ---- 四态流转 + 完成门禁 ----
    c_exec = svc.create_cycle({"name": "D3 四态与门禁"})["cycle"]["cycle_id"]
    fb = svc.freeze_batch(d2_body("INITIAL", c_exec, 10_000_000))
    exec_batch = fb["batch"]["batch_id"]
    items = {i["code"]: i for i in fb["order_items"]}
    a = items["600111"]["order_item_id"]
    b = items["600222"]["order_item_id"]
    c = items["600333"]["order_item_id"]
    D3_STATE["batch_id"] = exec_batch
    D3_STATE["cycle_id"] = c_exec

    p0 = svc.batch_progress(exec_batch)
    check("D3.7 progress 初始 progressing + 四态计数",
          p0["gate"] == "progressing" and p0["counts"]["PENDING"] == 3 and p0["total"] == 3
          and p0["can_complete"] is False, {"gate": p0["gate"], "counts": p0["counts"]})

    svc.set_order_item_state(a, {"status": "REVIEW"})
    p1 = svc.batch_progress(exec_batch)
    check("D3.8 四态流转 PENDING→REVIEW",
          p1["counts"]["REVIEW"] == 1 and p1["counts"]["PENDING"] == 2, p1["counts"])
    check("D3.9 存在 REVIEW → 门禁 blocked", p1["gate"] == "blocked", p1["gate"])

    svc.set_order_item_state(a, {"status": "SKIPPED"})
    p2 = svc.batch_progress(exec_batch)
    check("D3.10 四态流转 REVIEW→SKIPPED",
          p2["counts"]["SKIPPED"] == 1 and p2["counts"]["REVIEW"] == 0, p2["counts"])

    try:
        svc.set_order_item_state(b, {"status": "CONFIRMED"})
        check("D3.11 state 接口不能设 CONFIRMED（409）", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.11 state 接口不能设 CONFIRMED（409）", exc.status == 409, exc.message)

    svc.record_transaction({"cycle_id": c_exec, "batch_id": exec_batch, "order_item_id": b,
                            "code": "600222", "name": "虚构乙", "side": "BUY", "qty": 100,
                            "price_cents": 2260, "confirmed": True})
    p3 = svc.batch_progress(exec_batch)
    check("D3.12 record_transaction 联动 order_item → CONFIRMED",
          p3["counts"]["CONFIRMED"] == 1 and p3["counts"]["PENDING"] == 1, p3["counts"])

    try:
        svc.record_transaction({"cycle_id": c_exec, "batch_id": exec_batch, "order_item_id": b,
                                "code": "600222", "name": "虚构乙", "side": "BUY", "qty": 100,
                                "price_cents": 2260, "confirmed": True})
        check("D3.13 重复确认同一 order_item 防护（409）", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.13 重复确认同一 order_item 防护（409）", exc.status == 409, exc.message)

    try:
        svc.set_order_item_state(b, {"status": "SKIPPED"})
        check("D3.14 CONFIRMED 不可逆转（409）", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.14 CONFIRMED 不可逆转（409）", exc.status == 409, exc.message)

    svc.set_order_item_state(c, {"status": "SKIPPED"})
    p4 = svc.batch_progress(exec_batch)
    check("D3.15 全部确认/跳过后门禁 done + can_complete",
          p4["gate"] == "done" and p4["can_complete"] is True and p4["processed"] == 3,
          {"gate": p4["gate"], "counts": p4["counts"]})

    try:
        svc.batch_progress(999999)
        check("D3.16 未知 batch progress 404", False, "未被拒绝")
    except LedgerError as exc:
        check("D3.16 未知 batch progress 404", exc.status == 404, exc.message)

    svc2 = LedgerService(str(D3DB))
    p5 = svc2.batch_progress(exec_batch)
    check("D3.17 刷新恢复：进程/实例重开后 progress 一致",
          p5["gate"] == p4["gate"] and p5["counts"] == p4["counts"]
          and p5["revision"] == p4["revision"], {"gate": p5["gate"], "counts": p5["counts"]})


def test_d3_http_restart() -> None:
    port = free_port(8801)
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(D3DB)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d3-server.log").open("w")
    procs: list = []

    def start():
        p = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                             cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        procs.append(p)
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    return p
            except Exception:
                time.sleep(0.25)
        return p

    def stop(p):
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()

    try:
        p = start()
        batch_id = D3_STATE.get("batch_id")
        s, j = http_json_port(port, "GET", "/api/ledger/batches/%s/progress" % batch_id)
        check("D3.H1 GET batches/:id/progress 200 + 四态计数 + order_items",
              s == 200 and j.get("gate") == "done" and j["counts"]["CONFIRMED"] == 1
              and j["counts"]["SKIPPED"] == 2 and len(j.get("order_items") or []) == 3,
              {"status": s, "gate": j.get("gate"), "counts": j.get("counts")})

        s, j = http_json_port(port, "GET", "/api/ledger/batches/999999/progress")
        check("D3.H2 未知 batch progress 404", s == 404, j.get("error"))

        s, j = http_json_port(port, "POST", "/api/ledger/cycles", {"name": "D3 HTTP 四态"})
        cyc = j["cycle"]["cycle_id"]
        s, j = http_json_port(port, "POST", "/api/ledger/batches/freeze",
                              d2_body("INITIAL", cyc, 10_000_000))
        hb = j["batch"]["batch_id"]
        hi = j["order_items"][0]["order_item_id"]
        s, j = http_json_port(port, "POST", "/api/ledger/order-items/%s/state" % hi,
                              {"status": "SKIPPED"})
        check("D3.H3 POST order-items/:id/state 200",
              s == 200 and j["order_item"]["status"] == "SKIPPED", {"status": s})
        s, j = http_json_port(port, "POST", "/api/ledger/order-items/%s/state" % hi,
                              {"status": "CONFIRMED"})
        check("D3.H4 state 接口不能设 CONFIRMED（409）", s == 409, j.get("error"))

        s, j = http_json_port(port, "GET", "/api/ledger/batches/%s/progress" % hb)
        before = {"gate": j.get("gate"), "counts": j.get("counts")}
        check("D3.H5 HTTP progress 计数（1 已跳过 / 2 待下单）",
              s == 200 and j["counts"]["SKIPPED"] == 1 and j["counts"]["PENDING"] == 2, before)

        stop(p)
        p = start()
        s, j = http_json_port(port, "GET", "/api/ledger/batches/%s/progress" % hb)
        after = {"gate": j.get("gate"), "counts": j.get("counts")}
        check("D3.H6 重启服务后 progress 一致（刷新恢复）",
              s == 200 and after == before, {"before": before, "after": after})
    finally:
        for proc in procs:
            if proc.poll() is None:
                stop(proc)
        log.close()
        check("D3.H7 D3 服务进程干净退出", all(proc.returncode is not None for proc in procs),
              [proc.returncode for proc in procs])


# --------------------------------------------------- 6) HTTP API + V1.2 回归
def test_http() -> None:
    global PORT
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(DB)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                status, _c, raw = http("GET", "/api/health", timeout=2)
                if status == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("6.1 服务启动可访问", up, "server.log 见 %s" % log.name)
        if not up:
            return

        # --- 旧接口语义回归（V1.2）---
        status, _c, raw = http("GET", "/")
        body = raw.decode("utf-8", "replace")
        check("6.2 首页 200 + 含 V1.2 界面标记",
              status == 200 and "红利" in body and len(body) > 10000, status)

        s, j = http_json("GET", "/api/health")
        check("6.3 /api/health 语义不变", s == 200 and j.get("ok") is True
              and j.get("version") == "1.2", j)

        s, j = http_json("GET", "/api/cache-status")
        check("6.4 /api/cache-status 语义不变", s == 200 and "indices" in j and "quotes" in j,
              sorted(j.keys()))

        s, j = http_json("GET", "/api/holdings?code=H30269")
        check("6.5 /api/holdings?code= 仍为指数权重缓存（旧语义）",
              s == 200 and isinstance(j.get("holdings"), list) and len(j["holdings"]) > 0,
              {"status": s, "count": len(j.get("holdings") or [])})

        s, j = http_json("GET", "/api/holdings?code=NOPE")
        check("6.6 未知指数代码仍 400", s == 400, j)

        s, j = http_json("GET", "/api/quotes")
        check("6.7 /api/quotes 无有效代码仍 400", s == 400, j)

        s, j = http_json("GET", "/api/weight?code=000300")
        check("6.8 /api/weight 非中证权重指数仍 400", s == 400, j)

        s, j = http_json("POST", "/api/save-parsed", {"code": "H30269", "holdings": []})
        check("6.9 /api/save-parsed 校验语义不变（异常入参 400）", s == 400, j)

        # --- 静态服务不得泄漏数据库 ---
        s, _c, _r = http("GET", "/db/schema.sql")
        check("6.10 静态服务不暴露 db/ 目录", s == 403, s)
        s, _c, _r = http("GET", "/dev.db")
        check("6.11 静态服务不暴露 .db 文件", s == 403, s)

        # --- 新账本 API ---
        s, j = http_json("GET", "/api/ledger/status?check=1")
        check("6.12 /api/ledger/status 200 + schema v3（D8 起）",
              s == 200 and j.get("schema_version") == 3
              and j.get("integrity_check") == ["ok"]
              and j["foreign_key_check"]["violations"] == 0,
              {"status": s, "schema": j.get("schema_version"),
               "integrity": j.get("integrity_check")})

        s, j = http_json("GET", "/api/ledger/routes")
        check("6.13 /api/ledger/routes 可用", s == 200 and "GET" in j.get("routes", {}), j.get("routes"))

        s, j = http_json("POST", "/api/ledger/cycles", {"name": "HTTP 演示周期"})
        http_cycle = (j.get("cycle") or {}).get("cycle_id")
        check("6.14 POST /api/ledger/cycles 201", s == 201 and http_cycle, j)

        s, j = http_json("POST", "/api/ledger/transactions",
                         {"cycle_id": http_cycle, "code": "000001", "side": "BUY", "qty": 100,
                          "price_cents": 1000})
        check("6.15 未 confirmed 的交易被拒（400）", s == 400, j)

        s, j = http_json("POST", "/api/ledger/transactions",
                         {"cycle_id": http_cycle, "code": "000001", "name": "虚构", "side": "BUY",
                          "qty": 100, "price_cents": 1000, "confirmed": True})
        check("6.16 POST confirmed 交易 201", s == 201 and j["transaction"]["amount_cents"] == 100000, j)
        check("6.17 交易同步追加现金事件", j["cash_event"]["event_type"] == "BUY"
              and j["cash_event"]["amount_cents"] == -100000, j.get("cash_event"))

        s, j = http_json("GET", "/api/ledger/holdings?cycle_id=%s" % http_cycle)
        check("6.18 GET holdings 重建持仓", s == 200 and len(j["holdings"]) == 1
              and j["holdings"][0]["qty"] == 100, j.get("holdings"))

        s, j = http_json("GET", "/api/ledger/cash?cycle_id=%s" % http_cycle)
        check("6.19 GET cash 余额正确", s == 200 and j["balance_cents"] == -100000, j)

        s, j = http_json("POST", "/api/ledger/batches",
                         {"cycle_id": http_cycle, "kind": "INITIAL", "algorithm_version": "http-0"})
        http_batch = (j.get("batch") or {}).get("batch_id")
        s, j = http_json("GET", "/api/ledger/batches?cycle_id=%s" % http_cycle)
        check("6.19a GET batches 带 cycle_id 查询串可用",
              s == 200 and any(b["batch_id"] == http_batch for b in j["batches"]),
              {"status": s, "batch": http_batch})

        s, j = http_json("POST", "/api/ledger/order-items",
                         {"batch_id": http_batch, "code": "000001", "name": "虚构", "market": "SZ",
                          "side": "BUY", "suggested_qty": 100, "reference_price_cents": 1000})
        http_item = (j.get("order_item") or {}).get("order_item_id")
        s, j = http_json("GET", "/api/ledger/order-items?batch_id=%s" % http_batch)
        check("6.19b GET order-items 带 batch_id 查询串可用",
              s == 200 and any(i["order_item_id"] == http_item for i in j["order_items"]),
              {"status": s, "item": http_item})

        s, j = http_json("GET", "/api/ledger/transactions?cycle_id=%s" % http_cycle)
        check("6.19c GET transactions 带 cycle_id 查询串可用",
              s == 200 and len(j["transactions"]) == 1, {"status": s, "n": len(j.get("transactions") or [])})

        s, j = http_json("POST", "/api/ledger/cash",
                         {"cycle_id": http_cycle, "event_type": "WITHDRAW", "amount_cents": 500})
        check("6.20 现金符号校验经 API 生效（400）", s == 400, j)

        s, j = http_json("GET", "/api/ledger/nope")
        check("6.21 未知账本端点 404", s == 404, j.get("error"))

        s, j = http_json("POST", "/api/ledger/transactions", None)
        check("6.22 空请求体 400（JSON 契约）", s == 400, j.get("error"))

        db_file = Path(str(DB))
        check("6.23 临时开发库文件已生成（默认路径外可用 --db 指定）", db_file.exists(),
              db_file.stat().st_size if db_file.exists() else "缺失")

        # --- D2：四生命周期 / 冻结 revision / summary（HTTP 层）---
        s, j = http_json("POST", "/api/ledger/cycles", {"name": "D2 HTTP 计划周期"})
        hplan = j["cycle"]["cycle_id"]
        s, j = http_json("POST", "/api/ledger/batches/preview", d2_body("INITIAL", hplan, 10_000_000))
        check("D2.H1 POST batches/preview 200 + 透明计划",
              s == 200 and len(j["plan"]["rows"]) == 3
              and j["plan"]["totals"]["deviation_total_cents"] == -271_000, {"status": s})
        s, j = http_json("POST", "/api/ledger/batches/preview",
                         d2_body("INITIAL", hplan, 10_000_000, prices={"600111": 1370}))
        check("D2.H2 preview 缺行情 400", s == 400, j.get("error"))
        s, j = http_json("POST", "/api/ledger/batches/freeze", d2_body("INITIAL", hplan, 10_000_000))
        hb = (j.get("batch") or {}).get("batch_id")
        check("D2.H3 POST batches/freeze 201 + revision=1 + 3 项",
              s == 201 and bool(hb) and j["batch"]["status"] == "FROZEN"
              and j["batch"]["revision"] == 1 and len(j["order_items"]) == 3,
              {"status": s, "batch": hb})
        s, j = http_json("POST", "/api/ledger/batches/%s/revise" % hb,
                         d2_body("INITIAL", hplan, 10_000_000))
        check("D2.H4 POST batches/:id/revise 200 + revision=2",
              s == 200 and j["batch"]["revision"] == 2, {"status": s, "rev": j.get("revision")})
        s, j = http_json("GET", "/api/ledger/order-items?batch_id=%s&latest=1" % hb)
        check("D2.H5 GET order-items latest=1 仅最新 revision",
              s == 200 and len(j["order_items"]) == 3
              and all(i["revision"] == 2 for i in j["order_items"]), {"status": s})
        s, j = http_json("GET", "/api/ledger/cycles/%s/summary" % http_cycle)
        check("D2.H6 GET cycles/:id/summary 200 含持仓重建+现金余额",
              s == 200 and "cash_balance_cents" in j and isinstance(j.get("holdings"), list)
              and j["cycle"]["cycle_id"] == http_cycle, {"status": s})
        s, j = http_json("GET", "/api/ledger/cycles/999999/summary")
        check("D2.H7 未知 cycle summary 404", s == 404, j.get("error"))
        s, j = http_json("POST", "/api/ledger/cycles", {"name": "D2 HTTP 关闭周期"})
        hclose = j["cycle"]["cycle_id"]
        s, j = http_json("POST", "/api/ledger/cycles/%s/close" % hclose, {"note": "D2 http"})
        check("D2.H8 空仓周期 close 200 → CLOSED",
              s == 200 and j["cycle"]["status"] == "CLOSED" and j["cycle"]["closed_at"],
              {"status": s})
        s, j = http_json("POST", "/api/ledger/batches/freeze", d2_body("INITIAL", hclose, 10_000_000))
        check("D2.H9 已关闭周期 freeze 409", s == 409, j.get("error"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("6.24 服务进程干净退出", proc.returncode is not None, proc.returncode)


# ------------------------------------- D4) 估值回撤双源核验 + 行情三路契约
D4_REQUIRED_QUOTE_KEYS = ("source", "status", "dataDate", "fetchedAt", "ageSeconds", "attempts",
                          "errorCode", "cacheAgeSeconds", "stale")


def d4_series(n: int = 40, start: str = "2026-06-01", base: float = 4000.0, step: float = 5.0) -> dict:
    """生成确定性的 n 个交易日（跳过周末）递增收盘序列（全部虚构，可清除）。"""
    from datetime import date, timedelta
    y, m, dd = (int(x) for x in start.split("-"))
    cur, i, out = date(y, m, dd), 0, {}
    while len(out) < n:
        if cur.weekday() < 5:
            i += 1
            out[cur.strftime("%Y-%m-%d")] = round(base + i * step, 2)
        cur += timedelta(days=1)
    return out


def d4_source(series, code: str = "000300", name: str = "沪深300", **over) -> dict:
    src = {"indexCode": code, "indexName": name, "instrument": "index", "kind": "price",
           "currency": "CNY", "field": "close", "series": series}
    src.update(over)
    return src


def test_d4_drawdown_algorithm() -> None:
    series = d4_series(40)
    good = d4_source(dict(series))
    r = valution.verify_drawdown(good, d4_source(dict(series)))
    check("D4.1 双源同指数同序列通过核验（OK）",
          r["ok"] and r["status"] == "OK" and r["joinedDays"] == 40
          and r["missingRate"] == 0.0 and r["maxRelError"] == 0.0,
          {"ok": r["ok"], "joined": r["joinedDays"], "maxRel": r["maxRelError"]})
    check("D4.2 回撤公式 = currentClose/highestClose-1（同一序列）",
          abs(r["drawdown"] - (r["currentClose"] / r["highestClose"] - 1.0)) < 1e-12
          and r["currentClose"] == series[max(series)] and r["highestClose"] == max(series.values()),
          {"drawdown": r["drawdown"], "current": r["currentClose"], "highest": r["highestClose"]})
    check("D4.3 抽样复核点覆盖端点与最高点前后（含 seeded 随机 20）",
          2 <= r["sampled"] and r["highestDate"] in series
          and len(r["sampledRandom"]) == 20
          and all(d in series for d in r["sampledRandom"]),
          {"sampled": r["sampled"], "random": len(r["sampledRandom"])})

    dates = sorted(series)
    cut = {d: series[d] for d in dates if d != dates[5]}
    r2 = valution.verify_drawdown(d4_source(series), d4_source(cut))
    check("D4.4 并集缺失率超 0.5% → NA + 原因（不兜底）",
          (not r2["ok"]) and "缺失率" in r2["reason"] and r2["drawdown"] is None
          and r2["display"] == "暂无数据", r2["reason"])

    drift = dict(series)
    drift[dates[10]] = round(series[dates[10]] * 1.002, 2)
    r3 = valution.verify_drawdown(d4_source(series), d4_source(drift))
    check("D4.5 相对误差超 0.10% → NA + 原因",
          (not r3["ok"]) and "相对误差" in r3["reason"] and r3["drawdown"] is None, r3["reason"])

    big = d4_series(400)
    peak = max(big, key=lambda d: big[d])
    b_top = {d: big[d] for d in sorted(big) if d != peak}
    r4 = valution.verify_drawdown(d4_source(big), d4_source(b_top))
    check("D4.6 候选最高日缺日 → NA（即使缺失率 0.25% 未超限）",
          (not r4["ok"]) and "最高" in r4["reason"] and r4["drawdown"] is None, r4["reason"])

    for label, bad in (
        ("D4.7 负例：ETF 收盘被身份校验拒绝",
         d4_source(dict(series), instrument="etf")),
        ("D4.8 负例：个股收盘被身份校验拒绝",
         d4_source(dict(series), instrument="stock")),
        ("D4.9 负例：盘中 high 被身份校验拒绝",
         d4_source(dict(series), field="high")),
        ("D4.10 负例：全收益指数被身份校验拒绝",
         d4_source(dict(series), kind="total_return")),
        ("D4.11 负例：指数代码不一致被拒绝",
         d4_source(dict(series), code="000905", name="沪深300")),
        ("D4.12 负例：指数名称不一致被拒绝",
         d4_source(dict(series), code="000300", name="中证500")),
        ("D4.13 负例：币种不一致被拒绝",
         d4_source(dict(series), currency="USD")),
        ("D4.14 负例：空序列 → NA（不崩、不编数）",
         d4_source({})),
    ):
        rr = valution.verify_drawdown(good, bad)
        check(label, (not rr["ok"]) and rr["drawdown"] is None and rr["status"] == "NA"
              and bool(rr["reason"]), rr["reason"])

    board = valution.drawdown_board()
    codes = [x["code"] for x in board["indices"]]
    check("D4.15 九指数回撤近似上架（用户已拍板）＋逐项来源标注",
          len(board["indices"]) == 9 and board["verified"] is True
          and all(x["status"] == "OK" and x["drawdown"] is not None
                  and "近似数据" in (x["reason"] or "") for x in board["indices"])
          and codes[:3] == ["000300", "000905", "000852"],
          {"n": len(board["indices"]), "codes": codes})
    check("D4.16 看板规则字段锁死（缺失率 0.5% / 容差 0.10% / top20 / 公式）",
          board["rules"]["missingRateLimit"] == 0.005
          and board["rules"]["relTolerance"] == 0.001
          and board["rules"]["topN"] == 20 and "highestClose" in board["rules"]["formula"],
          board["rules"])


def test_d4_page_contract() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    thead = html.split('id="valuationTable"')[1].split("</thead>")[0]
    cols = re.findall(r'data-col="([A-Za-z]+)"', thead)
    check("D4.P1 宽基估值表字段顺序（D7 起拆两表，宽基表列顺序固定）",
          cols == ["currentClose", "drawdown", "pePct", "pbPct", "dyPct", "rpPe", "rpDy",
                   "explain", "links"], cols)
    check("D4.P2 三宽基与六红利分区展示（D7 起拆两表：宽基表 + 红利表，六红利顺序不变）",
          all(c in html for c in ('"000300"', '"000905"', '"000852"', "MARKET_DATA"))
          and 'id="valuationDivTable"' in html and 'id="valuationDivRows"' in html)
    check("D4.P3 NA 渲染：无历史序列时回撤列显示「暂无数据」+ 原因",
          "const NA_TEXT='暂无数据'" in html and "drawdownBoard" in html
          and "currentClose" in html and "highestClose" in html and "highestDate" in html)
    check("D4.P4 三层口径各自标注（课程/官方/第三方），不混口径",
          "vLayer('课程'" in html and "vLayer('官方'" in html and "vLayer('第三方'" in html
          and "VALUATION_META" in html and "不合并分位" in html)
    check("D4.P5 手动覆盖默认隐藏在高级异常处理区",
          'id="manualOverrideArea"' in html
          and re.search(r'id="manualOverrideArea"[^>]*display:none', html) is not None)
    check("D4.P6 手动覆盖 localStorage 持久 + MANUAL_OVERRIDE 标记 + 不进账本定价",
          "divManualOverride" in html and "MANUAL_OVERRIDE" in html
          and "不进账本定价" in html and "isManual(h.code)" in html)
    check("D4.P7 行情状态枚举五态齐全",
          all(s in html for s in ("LIVE", "DEGRADED", "CACHE", "STALE_BLOCKED", "MANUAL_OVERRIDE")))
    check("D4.P8 普通价格只读（主表不再有可编辑 .price 输入）",
          'class="price"' not in html and "当前价格（只读）" in html
          and 'class="manual-price"' in html)
    check("D4.P9 V1.2 区块未动（initSelect / indexSelect / valuationRows / SheetJS 第3行）",
          "function initSelect" in html and 'id="indexSelect"' in html
          and 'id="valuationRows"' in html
          and "xlsx.full.min.js" in html.split("\n")[2])


def test_d4_http() -> None:
    from datetime import datetime, timedelta, timezone
    port = free_port(8811)
    tz8 = timezone(timedelta(hours=8))
    now = datetime.now(tz8)
    fresh = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    old = (now - timedelta(days=20)).isoformat(timespec="seconds")
    cache_file = TMP / "d4-quotes-cache.json"
    cache_file.write_text(json.dumps({
        "saved_at": fresh, "quotes": {
            "999999": {"price": 3.21, "source": "腾讯主源", "market_time": fresh[:19].replace("T", " "),
                       "fetched_at": fresh, "stale": False},
            "999998": {"price": 1.11, "source": "腾讯主源", "market_time": old[:19].replace("T", " "),
                       "fetched_at": old, "stale": False},
        }}, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(TMP / "d4-http.dev.db")
    env["DIVIDEND_QUOTE_CACHE"] = str(cache_file)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d4-server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("D4.H0 D4 服务启动可访问", up)
        if not up:
            return

        s, j = http_json_port(port, "GET", "/api/drawdown")
        check("D4.H1 GET /api/drawdown 200 + 九指数近似 OK（用户已拍板）",
              s == 200 and len(j.get("indices") or []) == 9 and j.get("verified") is True
              and all(x["status"] == "OK" and x["drawdown"] is not None for x in j["indices"]),
              {"status": s, "n": len(j.get("indices") or [])})

        s, j = http_json_port(port, "GET", "/api/quotes?symbols=sz999999,sz999998", timeout=40)
        quotes = j.get("quotes") or {}
        fresh_q, old_q = quotes.get("999999", {}), quotes.get("999998", {})
        check("D4.H2 行情状态字段契约完整（source/status/dataDate/fetchedAt/ageSeconds/"
              "attempts/errorCode/cacheAgeSeconds/stale）",
              s == 200 and set(D4_REQUIRED_QUOTE_KEYS) <= set(fresh_q)
              and set(D4_REQUIRED_QUOTE_KEYS) <= set(old_q),
              {"status": s, "keys": sorted(set(fresh_q) & set(D4_REQUIRED_QUOTE_KEYS))})
        check("D4.H3 缓存新鲜 → CACHE（cacheAgeSeconds 有值、stale=false）",
              fresh_q.get("status") == "CACHE" and fresh_q.get("cache") is True
              and fresh_q.get("stale") is False and fresh_q.get("cacheAgeSeconds") is not None
              and fresh_q.get("dataDate"), {k: fresh_q.get(k) for k in ("status", "stale", "cacheAgeSeconds")})
        check("D4.H4 缓存超 72 小时 → STALE_BLOCKED + stale 标记（不伪装实时）",
              old_q.get("status") == "STALE_BLOCKED" and old_q.get("stale") is True
              and (old_q.get("cacheAgeSeconds") or 0) > 72 * 3600,
              {k: old_q.get(k) for k in ("status", "stale", "cacheAgeSeconds")})
        check("D4.H5 响应声明五态枚举 + 主备源健康度（连续失败次数可见）",
              set(("LIVE", "DEGRADED", "CACHE", "STALE_BLOCKED", "MANUAL_OVERRIDE"))
              <= set(j.get("statuses") or []) and isinstance(j.get("sources"), dict)
              and any("consecutiveFailures" in v for v in j["sources"].values()),
              {"statuses": j.get("statuses"), "sources": list((j.get("sources") or {}).keys())})

        s, j = http_json_port(port, "GET", "/api/quotes")
        check("D4.H6 /api/quotes 无有效代码仍 400（V1.2 回归）", s == 400, j.get("error"))
        s, j = http_json_port(port, "GET", "/api/health")
        check("D4.H7 /api/health 语义不变（V1.2 回归）",
              s == 200 and j.get("ok") is True and j.get("version") == "1.2", j)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("D4.H8 D4 服务进程干净退出", proc.returncode is not None, proc.returncode)


# ------------------------------------- D5) 非当前成分 / D4 P1×2 修复 / 持仓页契约
def test_d5_non_current_constituent() -> None:
    svc = LedgerService(str(D5DB))
    cid = svc.create_cycle({"name": "D5 非当前成分"})["cycle"]["cycle_id"]
    svc.record_transaction({"cycle_id": cid, "code": D5_STALE_CODE, "name": "虚构退指",
                            "side": "BUY", "qty": 1000, "price_cents": 500, "confirmed": True})

    add = svc.preview_batch(d2_body("ADD", cid, 10_000_000, prices=D5_PRICES))["plan"]
    by = {r["code"]: r for r in add["rows"]}
    stale = by.get(D5_STALE_CODE, {})
    check("D5.ST1 ADD universe=成分∪持仓 + stale_constituents 标记",
          add["universe"]["constituents"] == 3 and add["universe"]["holdings"] == 1
          and add["stale_constituents"] == [D5_STALE_CODE], add.get("universe"))
    check("D5.ST2 非当前成分行标 STALE_CONSTITUENT + 原因",
          stale.get("constituent_status") == "STALE_CONSTITUENT"
          and stale.get("stale_constituent") is True
          and "非当前成分" in (stale.get("constituent_reason") or ""), stale)
    check("D5.ST3 ADD 不向非当前成分分配新 BUY（0 股）",
          stale.get("side") == "BUY" and stale.get("suggested_qty") == 0
          and stale.get("actual_amount_cents") == 0
          and not any(r["side"] == "BUY" and r["suggested_qty"] > 0
                      for r in add["rows"] if r["stale_constituent"]), stale)
    check("D5.ST4 缺口只向在成分内低配分配（在成分行有 BUY）",
          by["600222"]["side"] == "BUY" and by["600222"]["suggested_qty"] > 0
          and by["600222"]["constituent_status"] == "IN_INDEX", by.get("600222"))
    check("D5.ST5 ADD 不变量成立 + 非当前成分告警可见",
          d2_invariant(add) and any("非当前成分" in w for w in add["warnings"]),
          add["warnings"])

    summ = svc.cycle_summary(cid)
    codes = [h["code"] for h in summ["holdings"]]
    check("D5.ST6 summary/holdings 保留非当前成分持仓（不过滤）",
          D5_STALE_CODE in codes and "v_holdings" in summ["holdings_rebuild_source"],
          {"holdings": codes, "rebuild": summ["holdings_rebuild_source"]})

    reb = svc.preview_batch(d2_body("REBALANCE", cid, 0, prices=D5_PRICES))["plan"]
    check("D5.ST7 REBALANCE 不向非当前成分分配新 BUY",
          not any(r["side"] == "BUY" and r["suggested_qty"] > 0
                  for r in reb["rows"] if r["stale_constituent"]),
          {"stale": reb["stale_constituents"]})

    ex = svc.preview_batch(d2_body("EXIT", cid, 0, prices=D5_PRICES))["plan"]
    exby = {r["code"]: r for r in ex["rows"]}
    check("D5.ST8 EXIT 对非当前成分照常全仓 SELL",
          exby.get(D5_STALE_CODE, {}).get("side") == "SELL"
          and exby[D5_STALE_CODE]["suggested_qty"] == 1000
          and exby[D5_STALE_CODE]["constituent_status"] == "STALE_CONSTITUENT"
          and "EXIT 照常全仓 SELL" in (exby[D5_STALE_CODE]["constituent_reason"] or ""),
          exby.get(D5_STALE_CODE))


def test_d5_quote_health() -> None:
    import server as srv
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=8))
    t0 = datetime(2026, 9, 15, 10, 0, 0, tzinfo=tz)

    srv.reset_source_health()
    name = "自检滚动源"
    st = None
    for i in range(srv.DEGRADED_FAILS):
        st = srv.note_source_result(name, False, "TIMEOUT", t0 + timedelta(seconds=i))
    check("D5.Q1 窗口内连续 %d 次失败 → DEGRADED" % srv.DEGRADED_FAILS,
          st["status"] == "DEGRADED" and st["consecutiveFailures"] == srv.DEGRADED_FAILS, st)
    st = srv.note_source_result(name, True, "", t0 + timedelta(seconds=4))
    check("D5.Q2 恢复需连续 2 次：1 次成功仍 DEGRADED",
          st["status"] == "DEGRADED" and st["consecutiveSuccesses"] == 1, st)
    st = srv.note_source_result(name, True, "", t0 + timedelta(seconds=5))
    check("D5.Q3 连续 2 次成功 → 恢复 LIVE",
          st["status"] == "LIVE" and st["consecutiveSuccesses"] == srv.RECOVER_AFTER, st)

    srv.reset_source_health()
    n2 = "自检窗口过期源"
    srv.note_source_result(n2, False, "TIMEOUT", t0)
    st = srv.note_source_result(n2, False, "TIMEOUT",
                                t0 + timedelta(seconds=srv.DEGRADED_WINDOW + 1))
    check("D5.Q4 滚动窗口过期 → 连续失败计数重置（不累加成 DEGRADED）",
          st["consecutiveFailures"] == 1 and st["status"] == "LIVE", st)

    mt = t0.strftime("%Y-%m-%d %H:%M:%S")
    good = {"600519": {"price": 1500.0, "source": "腾讯主源", "market_time": mt,
                       "fetched_at": t0.isoformat()}}
    valid, probs = srv.split_valid_quotes(good, t0)
    check("D5.Q5 字段范围+dataDate 全校验通过 → 计入成功",
          set(valid) == {"600519"} and probs == [], probs)
    bad_date = {"600519": {"price": 1500.0, "source": "腾讯主源", "market_time": "",
                           "fetched_at": ""}}
    valid2, probs2 = srv.split_valid_quotes(bad_date, t0)
    check("D5.Q6 坏 dataDate → 剔除且不计成功",
          valid2 == {} and any("dataDate" in p for p in probs2), probs2)
    bad_price = {"600519": {"price": -1, "source": "腾讯主源", "market_time": mt,
                            "fetched_at": t0.isoformat()}}
    valid3, probs3 = srv.split_valid_quotes(bad_price, t0)
    check("D5.Q7 价格越界 → 剔除且不计成功",
          valid3 == {} and any("价格" in p for p in probs3), probs3)
    srv.reset_source_health()


def test_d5_drawdown_sampling() -> None:
    series = d4_series(40)
    r1 = valution.verify_drawdown(d4_source(dict(series)), d4_source(dict(series)))
    r2 = valution.verify_drawdown(d4_source(dict(series)), d4_source(dict(series)))
    check("D5.S1 seeded 随机 20 抽样（确定性，同输入同结果）",
          r1["ok"] and len(r1["sampledRandom"]) == 20
          and r1["sampledRandom"] == r2["sampledRandom"]
          and all(d in series for d in r1["sampledRandom"]),
          {"n": len(r1["sampledRandom"]), "seed": r1["sampleSeed"]})
    small = d4_series(12)
    r3 = valution.verify_drawdown(d4_source(dict(small)), d4_source(dict(small)))
    check("D5.S2 joined 不足 20 则全取",
          r3["ok"] and len(r3["sampledRandom"]) == 12, len(r3["sampledRandom"]))
    f1 = valution.verify_drawdown(d4_source(dict(series)), d4_source(dict(series)),
                                  sample_seed=1)
    f2 = valution.verify_drawdown(d4_source(dict(series)), d4_source(dict(series)),
                                  sample_seed=1)
    check("D5.S3 换种子抽样仍确定且可复现",
          len(f1["sampledRandom"]) == 20 and f1["sampledRandom"] == f2["sampledRandom"],
          f1["sampleSeed"])


def test_d5_page_contract() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check("D5.P1 新增「七、持仓与历史」只读区块", "七、持仓与历史" in html)
    check("D5.P2 持仓页调 cycle_summary（GET /api/ledger/cycles/:id/summary）",
          "/api/ledger/cycles/'+cid+'/summary" in html)
    check("D5.P3 持仓表 + confirmed 重建声明 + 现金余额/流水 + 批次计数",
          'id="hpRows"' in html and "v_holdings(confirmed transactions)" in html
          and "策略现金余额" in html and "现金事件流水" in html and "批次数量" in html)
    check("D5.P4 非当前成分 STALE 标记行",
          "STALE_CONSTITUENT" in html and "非当前成分" in html)
    d5 = html.split("D5 持仓与历史")[-1]
    check("D5.P5 持仓区块只读（脚本内无 POST 写接口）", "POST" not in d5)
    check("D5.P6 V1.2/D1-D4 区块未动（SheetJS 第3行/initSelect/valuationTable/MANUAL_OVERRIDE）",
          "xlsx.full.min.js" in html.split("\n")[2] and "function initSelect" in html
          and 'id="valuationTable"' in html and "MANUAL_OVERRIDE" in html)


def test_d5_holdings_http() -> None:
    port = free_port(8821)
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(D5DB)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d5-server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("D5.H0 D5 服务启动可访问", up)
        if not up:
            return
        s, j = http_json_port(port, "GET", "/api/ledger/cycles")
        cycles = j.get("cycles") or []
        cid = cycles[-1]["cycle_id"] if cycles else None
        s, j = http_json_port(port, "GET", "/api/ledger/cycles/%s/summary" % cid)
        codes = [h["code"] for h in (j.get("holdings") or [])]
        check("D5.H1 持仓页 API 契约：summary 200 + 持仓/现金/批次/成交计数 + 重建声明",
              s == 200 and isinstance(j.get("holdings"), list)
              and "cash_balance_cents" in j and "batch_count" in j
              and "transaction_count" in j
              and "v_holdings" in (j.get("holdings_rebuild_source") or ""),
              {"status": s, "keys": sorted(j.keys())})
        check("D5.H2 summary 保留非当前成分持仓（只读展示，不做过滤）",
              D5_STALE_CODE in codes, codes)
        s, j = http_json_port(port, "GET", "/api/ledger/cash?cycle_id=%s" % cid)
        check("D5.H3 策略现金事件流水可读",
              s == 200 and isinstance(j.get("cash_events"), list)
              and j.get("balance_cents") is not None, {"status": s})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("D5.H4 D5 服务进程干净退出", proc.returncode is not None, proc.returncode)


# ------------------------------------- D7) 删除测试批次（Change B）/ 页面契约
def test_d7_delete_batch() -> None:
    svc = LedgerService(str(D7DB))

    # 1) 无 CONFIRMED 的批次：直接删，落 order_items 删除 + 审计
    c1 = svc.create_cycle({"name": "D7 删空批"})["cycle"]["cycle_id"]
    b1 = svc.freeze_batch(d2_body("INITIAL", c1, 10_000_000))
    bid1 = b1["batch"]["batch_id"]
    r1 = svc.delete_batch(bid1, {})
    check("D7.1 无 CONFIRMED 批次可删（整批 order_items 移除）",
          r1["deleted"] is True and r1["order_items_deleted"] == 3
          and r1["transactions_deleted"] == 0 and r1["confirmed_items"] == 0, r1)
    try:
        svc.batch_progress(bid1)
        check("D7.2 删后 progress 404", False, "未 404")
    except LedgerError as exc:
        check("D7.2 删后 progress 404", exc.status == 404, exc.message)
    check("D7.3 删除写审计（audit_id + DELETE_BATCH）",
          bool(r1["audit"].get("audit_id")) and r1["audit"]["action"] == "DELETE_BATCH"
          and r1["audit"]["entity"] == "batch", r1["audit"])

    # 2) 含 CONFIRMED：未传 confirm_text 拒绝；传「确认删除」放行并连带删成交/现金
    c2 = svc.create_cycle({"name": "D7 含确认"})["cycle"]["cycle_id"]
    b2 = svc.freeze_batch(d2_body("INITIAL", c2, 10_000_000))
    bid2 = b2["batch"]["batch_id"]
    item = b2["order_items"][0]
    svc.record_transaction({"cycle_id": c2, "batch_id": bid2,
                            "order_item_id": item["order_item_id"], "code": item["code"],
                            "name": item["name"], "side": "BUY",
                            "qty": item["suggested_qty"],
                            "price_cents": item["reference_price_cents"], "confirmed": True})
    tx_before = len(svc.list_transactions(cycle_id=c2)["transactions"])
    cash_before = len(svc.list_cash(cycle_id=c2)["cash_events"])
    check("D7.4 删除前：1 成交 + 1 自动现金事件",
          tx_before == 1 and cash_before == 1, {"tx": tx_before, "cash": cash_before})
    try:
        svc.delete_batch(bid2, {})
        check("D7.5 含 CONFIRMED 未传确认词 → 400 拒绝", False, "未被拒绝")
    except LedgerError as exc:
        check("D7.5 含 CONFIRMED 未传确认词 → 400 拒绝",
              exc.status == 400 and DELETE_CONFIRM_TEXT in exc.message, exc.message)
    try:
        svc.delete_batch(bid2, {"confirm_text": "删除"})
        check("D7.6 确认词错误（非「确认删除」）→ 400", False, "未被拒绝")
    except LedgerError as exc:
        check("D7.6 确认词错误（非「确认删除」）→ 400", exc.status == 400, exc.message)
    r2 = svc.delete_batch(bid2, {"confirm_text": DELETE_CONFIRM_TEXT})
    check("D7.7 传「确认删除」后整批删除（含成交与现金事件）",
          r2["deleted"] is True and r2["confirmed_items"] == 1
          and r2["transactions_deleted"] == 1 and r2["cash_events_deleted"] == 1, r2)
    check("D7.8 删除后该周期成交/现金归零、持仓重建为空",
          len(svc.list_transactions(cycle_id=c2)["transactions"]) == 0
          and len(svc.list_cash(cycle_id=c2)["cash_events"]) == 0
          and svc.holdings(c2)["holdings"] == [])

    # 3) 未知批次 404 / CLOSED 周期 409
    try:
        svc.delete_batch(999999, {"confirm_text": DELETE_CONFIRM_TEXT})
        check("D7.9 未知批次删除 → 404", False, "未 404")
    except LedgerError as exc:
        check("D7.9 未知批次删除 → 404", exc.status == 404, exc.message)
    c3 = svc.create_cycle({"name": "D7 关闭周期"})["cycle"]["cycle_id"]
    bid3 = svc.freeze_batch(d2_body("INITIAL", c3, 10_000_000))["batch"]["batch_id"]
    svc.close_cycle(c3)
    try:
        svc.delete_batch(bid3, {"confirm_text": DELETE_CONFIRM_TEXT})
        check("D7.10 CLOSED 周期拒绝删除批次 → 409", False, "未被拒绝")
    except LedgerError as exc:
        check("D7.10 CLOSED 周期拒绝删除批次 → 409", exc.status == 409, exc.message)

    # 3b) P1-1：事实成交但 order_item 仍 PENDING（不给 order_item_id 写成交）也必须 typed 确认
    c3b = svc.create_cycle({"name": "D7 事实成交无 order_item"})["cycle"]["cycle_id"]
    b3b = svc.freeze_batch(d2_body("INITIAL", c3b, 10_000_000))
    bid3b = b3b["batch"]["batch_id"]
    it3b = b3b["order_items"][0]
    svc.record_transaction({"cycle_id": c3b, "batch_id": bid3b, "code": it3b["code"],
                            "name": it3b["name"], "side": "BUY", "qty": 100,
                            "price_cents": it3b["reference_price_cents"], "confirmed": True})
    prog3b = svc.batch_progress(bid3b)
    check("D7.14 成交已写账本但 order_item 仍 PENDING（API 路径）",
          prog3b["counts"]["PENDING"] == 3 and prog3b["confirmed_transactions"] == 1,
          {"counts": prog3b["counts"], "tx": prog3b["confirmed_transactions"]})
    try:
        svc.delete_batch(bid3b, {})
        check("D7.15 事实成交（无 order_item 联动）未传确认词 → 400", False, "未被拒绝")
    except LedgerError as exc:
        check("D7.15 事实成交（无 order_item 联动）未传确认词 → 400",
              exc.status == 400 and DELETE_CONFIRM_TEXT in exc.message, exc.message)
    r3b = svc.delete_batch(bid3b, {"confirm_text": DELETE_CONFIRM_TEXT})
    check("D7.16 传确认词后删除，成交事实口径计入审计",
          r3b["deleted"] is True and r3b["transactions_deleted"] == 1
          and r3b["confirmed_transactions"] == 1 and r3b["confirmed_facts"] >= 1, r3b)

    # 4) 审计/授权表落盘行；正常批次不受影响
    conn = connect(str(D7DB))
    try:
        audit_n = conn.execute(
            "SELECT COUNT(*) FROM ledger_audit WHERE action='DELETE_BATCH'").fetchone()[0]
        auth_n = conn.execute("SELECT COUNT(*) FROM ledger_batch_deletions").fetchone()[0]
    finally:
        conn.close()
    check("D7.11 审计表 DELETE_BATCH 行数 = 3、删除授权行 = 3",
          audit_n == 3 and auth_n == 3, {"audit": audit_n, "authorize": auth_n})
    c4 = svc.create_cycle({"name": "D7 回归未受影响"})["cycle"]["cycle_id"]
    b4 = svc.freeze_batch(d2_body("INITIAL", c4, 10_000_000))
    check("D7.12 正常批次创建/冻结不受影响",
          b4["batch"]["status"] == "FROZEN" and len(b4["order_items"]) == 3)
    p4 = svc.batch_progress(b4["batch"]["batch_id"])
    check("D7.13 正常批次 progress 可用（progressing）",
          p4["gate"] == "progressing" and p4["total"] == 3, p4["gate"])


def test_d7_http() -> None:
    port = free_port(8841)
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(D7DB)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d7-server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("D7.H0 D7 服务启动可访问", up)
        if not up:
            return
        s, j = http_json_port(port, "GET", "/api/ledger/status")
        check("D7.H1 status 报 schema v3 + 审计表在位",
              s == 200 and j.get("schema_version") == 3, {"status": s})
        s, j = http_json_port(port, "POST", "/api/ledger/cycles", {"name": "D7 HTTP 删除"})
        cyc = j["cycle"]["cycle_id"]
        s, j = http_json_port(port, "POST", "/api/ledger/batches/freeze",
                              d2_body("INITIAL", cyc, 10_000_000))
        hb = j["batch"]["batch_id"]
        hi = j["order_items"][0]["order_item_id"]
        http_json_port(port, "POST", "/api/ledger/transactions",
                       {"cycle_id": cyc, "batch_id": hb, "order_item_id": hi,
                        "code": "600111", "name": "虚构甲", "side": "BUY", "qty": 100,
                        "price_cents": 1370, "confirmed": True})
        s, j = http_json_port(port, "POST", "/api/ledger/batches/%s/delete" % hb, {})
        check("D7.H2 HTTP 含 CONFIRMED 未传确认词 → 400",
              s == 400 and DELETE_CONFIRM_TEXT in (j.get("error") or ""), {"status": s, "err": j.get("error")})
        s, j = http_json_port(port, "POST", "/api/ledger/batches/%s/delete" % hb,
                              {"confirm_text": DELETE_CONFIRM_TEXT})
        check("D7.H3 HTTP 传确认词 → 200 且整批删除",
              s == 200 and j.get("deleted") is True and j.get("transactions_deleted") == 1,
              {"status": s, "body": {k: j.get(k) for k in ("deleted", "transactions_deleted", "order_items_deleted")}})
        s, j = http_json_port(port, "GET", "/api/ledger/batches/%s/progress" % hb)
        check("D7.H4 HTTP 删后 progress 404", s == 404, j.get("error"))
        s, j = http_json_port(port, "POST", "/api/ledger/batches/999999/delete",
                              {"confirm_text": DELETE_CONFIRM_TEXT})
        check("D7.H5 HTTP 未知批次删除 → 404", s == 404, j.get("error"))
        s, j = http_json_port(port, "GET", "/api/ledger/routes")
        check("D7.H6 routes 声明 batches/<id>/delete",
              any("batches/<id>/delete" in r for r in (j.get("routes", {}).get("POST") or [])),
              j.get("routes", {}).get("POST"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("D7.H7 D7 服务进程干净退出", proc.returncode is not None, proc.returncode)


def test_d7_page_contract() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check("D7.P1 估值拆两张表（宽基 valuationTable / 红利 valuationDivTable）",
          'id="valuationTable"' in html and 'id="valuationDivTable"' in html
          and 'id="valuationRows"' in html and 'id="valuationDivRows"' in html)
    check("D7.P2 列顺序：当前收盘→回撤→PE分位→PB分位→股息率分位→风险溢价×2→解释→来源",
          html.index('data-col="currentClose"') < html.index('data-col="drawdown"')
          < html.index('data-col="pePct"') < html.index('data-col="pbPct"')
          < html.index('data-col="dyPct"') < html.index('data-col="rpPe"')
          < html.index('data-col="rpDy"') < html.index('data-col="explain"')
          < html.index('data-col="links"'))
    check("D7.P3 紧凑样式与分位分档（vtable/sticky/vlow/vmid/vhigh 文字标识）",
          "table.vtable" in html and "position:sticky" in html
          and ".vlow" in html and ".vmid" in html and ".vhigh" in html
          and "VCOLOR" in html and "偏低" in html and "偏高" in html)
    check("D7.P4 宽基公开估算已落盘且带来源 URL（百分位/股叉叉）+ 估算标记",
          "baifenwei.com/index/hs300/" in html and "baifenwei.com/index/zz500/" in html
          and "baifenwei.com/index/zz1000/" in html
          and "guchacha.com/index-valuation/000300" in html
          and "估算" in html and '"pePct":63.8' in html and '"dyPct":69.1' in html)
    check("D7.P5 宽基风险溢价：PE 口径反推有值、股息率口径仍 NA（用户已拍板近似）",
          "风险溢价(PE口径)反推" in html and "股息率口径无授权同口径来源" in html
          and "暂无数据" in html)
    check("D7.P6 行内确认（dp-confirm）+ 回车/Esc 键盘确认，无 window.confirm 确认弹窗",
          "dp-confirm" in html and "dpCancelConfirm" in html
          and "e.key==='Enter'" in html and "e.key==='Escape'" in html
          and "window.confirm(`确认第 #" not in html)
    check("D7.P7 复制就近 toast（cp-toast + dpToast）",
          "cp-toast" in html and "function dpToast" in html
          and "已复制'+label" in html)
    check("D7.P8 删除测试批次前端（高级区 + 确认删除四字 + typed prompt）",
          'id="dpDeleteBatchBtn"' in html and "dpDeleteBatch" in html
          and "确认删除" in html and "batches/'+dpBatchId+'/delete" in html)
    check("D7.P9 V1.2 区块未动（SheetJS 第3行 / initSelect / 手动覆盖区仍在）",
          "xlsx.full.min.js" in html.split("\n")[2] and "function initSelect" in html
          and "MANUAL_OVERRIDE" in html)


# ------------------------------------- D8) 撤销已确认成交（用户明确要求可撤销/清空）
def test_d8_revert() -> None:
    svc = LedgerService(str(D8DB))
    cid = svc.create_cycle({"name": "D8 撤销确认"})["cycle"]["cycle_id"]
    fb = svc.freeze_batch(d2_body("INITIAL", cid, 10_000_000))
    bid = fb["batch"]["batch_id"]
    it = fb["order_items"][0]
    svc.record_transaction({"cycle_id": cid, "batch_id": bid,
                            "order_item_id": it["order_item_id"], "code": it["code"],
                            "name": it["name"], "side": "BUY", "qty": it["suggested_qty"],
                            "price_cents": it["reference_price_cents"], "confirmed": True})
    check("D8.1 确认后行状态 CONFIRMED",
          [i for i in svc.list_order_items(bid, latest_only=True)["order_items"]
           if i["order_item_id"] == it["order_item_id"]][0]["status"] == "CONFIRMED")
    try:
        svc.revert_confirmation(it["order_item_id"], {})
        check("D8.2 未传确认词 → 400 拒绝", False, "未被拒绝")
    except LedgerError as exc:
        check("D8.2 未传确认词 → 400 拒绝",
              exc.status == 400 and "撤销确认" in exc.message, exc.message)
    try:
        svc.revert_confirmation(it["order_item_id"], {"confirm_text": "删除"})
        check("D8.3 确认词错误 → 400", False, "未被拒绝")
    except LedgerError as exc:
        check("D8.3 确认词错误 → 400", exc.status == 400, exc.message)
    r = svc.revert_confirmation(it["order_item_id"], {"confirm_text": "撤销确认"})
    check("D8.4 传「撤销确认」后撤销（成交＋现金事件移除）",
          r["reverted"] is True and r["transactions_deleted"] == 1
          and r["cash_events_deleted"] == 1
          and r["order_item"]["status"] == "PENDING", r)
    check("D8.5 撤销后持仓重建为空、现金归零",
          svc.holdings(cid)["holdings"] == []
          and svc.cycle_summary(cid)["cash_balance_cents"] == 0)
    try:
        svc.revert_confirmation(it["order_item_id"], {"confirm_text": "撤销确认"})
        check("D8.6 非 CONFIRMED 行再撤销 → 400", False, "未被拒绝")
    except LedgerError as exc:
        check("D8.6 非 CONFIRMED 行再撤销 → 400", exc.status == 400, exc.message)
    # 重新确认后仍可再撤销（可反复退回）
    svc.record_transaction({"cycle_id": cid, "batch_id": bid,
                            "order_item_id": it["order_item_id"], "code": it["code"],
                            "name": it["name"], "side": "BUY", "qty": it["suggested_qty"],
                            "price_cents": it["reference_price_cents"], "confirmed": True})
    r2 = svc.revert_confirmation(it["order_item_id"], {"confirm_text": "撤销确认"})
    check("D8.7 重确认后可再撤销", r2["reverted"] is True)
    try:
        svc.revert_confirmation(999999, {"confirm_text": "撤销确认"})
        check("D8.8 未知 order_item → 404", False, "未 404")
    except LedgerError as exc:
        check("D8.8 未知 order_item → 404", exc.status == 404, exc.message)
    c2 = svc.create_cycle({"name": "D8 关闭周期"})["cycle"]["cycle_id"]
    b2 = svc.freeze_batch(d2_body("INITIAL", c2, 10_000_000))
    it2 = b2["order_items"][0]
    svc.record_transaction({"cycle_id": c2, "batch_id": b2["batch"]["batch_id"],
                            "order_item_id": it2["order_item_id"], "code": it2["code"],
                            "name": it2["name"], "side": "BUY", "qty": it2["suggested_qty"],
                            "price_cents": it2["reference_price_cents"], "confirmed": True})
    svc.record_transaction({"cycle_id": c2, "batch_id": b2["batch"]["batch_id"],
                            "order_item_id": None, "code": it2["code"],
                            "name": it2["name"], "side": "SELL", "qty": it2["suggested_qty"],
                            "price_cents": it2["reference_price_cents"], "confirmed": True})
    svc.close_cycle(c2)
    try:
        svc.revert_confirmation(it2["order_item_id"], {"confirm_text": "撤销确认"})
        check("D8.9 CLOSED 周期拒绝撤销 → 409", False, "未被拒绝")
    except LedgerError as exc:
        check("D8.9 CLOSED 周期拒绝撤销 → 409", exc.status == 409, exc.message)
    conn = connect(str(D8DB))
    try:
        rv = conn.execute("SELECT COUNT(*) FROM ledger_reverts").fetchone()[0]
        au = conn.execute("SELECT COUNT(*) FROM ledger_audit WHERE action='REVERT_CONFIRM'").fetchone()[0]
    finally:
        conn.close()
    check("D8.10 撤销授权＋审计行落盘（reverts=2/audit=2）", rv == 2 and au == 2,
          {"reverts": rv, "audit": au})


def test_d8_revert_http() -> None:
    port = free_port(8851)
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(D8DB)
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d8-server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("D8.H0 D8 服务启动可访问", up)
        if not up:
            return
        s, j = http_json_port(port, "POST", "/api/ledger/cycles", {"name": "D8 HTTP 撤销"})
        cyc = j["cycle"]["cycle_id"]
        s, j = http_json_port(port, "POST", "/api/ledger/batches/freeze",
                              d2_body("INITIAL", cyc, 10_000_000))
        hb = j["batch"]["batch_id"]
        hi = j["order_items"][0]["order_item_id"]
        http_json_port(port, "POST", "/api/ledger/transactions",
                       {"cycle_id": cyc, "batch_id": hb, "order_item_id": hi,
                        "code": "600111", "name": "虚构甲", "side": "BUY", "qty": 100,
                        "price_cents": 1370, "confirmed": True})
        s, j = http_json_port(port, "POST", "/api/ledger/order-items/%s/revert" % hi, {})
        check("D8.H1 HTTP 未传确认词 → 400", s == 400 and "撤销确认" in (j.get("error") or ""),
              {"status": s, "err": j.get("error")})
        s, j = http_json_port(port, "POST", "/api/ledger/order-items/%s/revert" % hi,
                              {"confirm_text": "撤销确认"})
        check("D8.H2 HTTP 传确认词 → 200 且行回 PENDING",
              s == 200 and j.get("reverted") is True
              and (j.get("order_item") or {}).get("status") == "PENDING",
              {"status": s})
        s, j = http_json_port(port, "GET", "/api/ledger/cycles/%s/summary" % cyc)
        check("D8.H3 撤销后 summary 持仓为空",
              s == 200 and j.get("holdings") == [], {"status": s})
        s, j = http_json_port(port, "POST", "/api/ledger/order-items/999999/revert",
                              {"confirm_text": "撤销确认"})
        check("D8.H4 HTTP 未知 order_item → 404", s == 404, j.get("error"))
        s, j = http_json_port(port, "GET", "/api/ledger/routes")
        check("D8.H5 routes 声明 order-items/<id>/revert",
              any("order-items/<id>/revert" in r for r in (j.get("routes", {}).get("POST") or [])))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("D8.H6 D8 服务进程干净退出", proc.returncode is not None, proc.returncode)


def test_d8_page_contract() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check("D8.P1 CONFIRMED 行有“撤销”按钮（dpRevertItem）",
          "dpRevertItem" in html and "撤销</button>" in html)
    check("D8.P2 撤销需输入“撤销确认”四字（typed prompt）",
          "撤销确认" in html and "请输入" in html)
    check("D8.P3 单只模式 CONFIRMED 行确认按钮变为撤销",
          "撤销确认" in html)

# ------------------------------------- D9) 回撤近似数据接线（用户拍板：近似＋交叉验证）
def test_d9_drawdown_file() -> None:
    doc = json.loads((ROOT / "cache" / "valuation" / "drawdown.json").read_text(encoding="utf-8"))
    check("D9.1 drawdown.json 在位且 asOf/fetchedAt/method 齐全",
          bool(doc.get("asOf")) and bool(doc.get("fetchedAt")) and bool(doc.get("method")),
          {"asOf": doc.get("asOf")})
    idx = doc.get("indices") or []
    check("D9.2 九指数全在文件内", len(idx) == 9, len(idx))
    bad = [r["code"] for r in idx
           if not (r.get("status") == "OK" and isinstance(r.get("drawdown"), (int, float))
                   and r.get("highestClose") and r.get("source"))]
    check("D9.3 九指数均有数值＋来源（无编造空洞）", bad == [], bad)
    check("D9.4 标普明确 ETF 代理标注",
          any(r["code"] == "SPCLLHCP" and r.get("etfProxy") is True for r in idx))
    check("D9.5 快照兜底项标 staleSnapshot＋日期",
          all((not r.get("staleSnapshot")) or "2026-08-07" in (r.get("source") or "")
              for r in idx))
    cks = doc.get("crossChecks") or []
    check("D9.6 crossChecks 交叉验证记录在位",
          len(cks) > 0 and all("code" in c for c in cks), len(cks))
    check("D9.7 回撤公式一致（display == current/highest-1）",
          all(abs(r["drawdown"] - (r["currentClose"] / r["highestClose"] - 1.0)) < 1e-6
              for r in idx if r.get("status") == "OK"))


def test_d9_drawdown_board() -> None:
    b = drawdown_board()
    check("D9.8 board 九指数 OK＋approx 标记＋asOf",
          b.get("status") == "OK" and b.get("approx") is True and bool(b.get("asOf"))
          and all(r["status"] == "OK" for r in b["indices"]),
          {"status": b.get("status"), "asOf": b.get("asOf")})
    check("D9.9 board 原因含来源说明（非空洞 NA）",
          all("近似数据" in (r.get("reason") or "") for r in b["indices"]))
    check("D9.10 board note 声明近似口径（宽基收盘/红利快照/ETF代理）",
          "近似数据" in (b.get("note") or "") and "ETF" in (b.get("note") or ""))


def test_d9_drawdown_http() -> None:
    port = free_port(8861)
    env = dict(os.environ)
    env["DIVIDEND_LEDGER_DB"] = str(TMP / "d9-drawdown.dev.db")
    env["PYTHONUNBUFFERED"] = "1"
    log = (TMP / "d9-server.log").open("w")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(port), "--no-open"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(60):
            try:
                if http_port(port, "GET", "/api/health", timeout=2)[0] == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.25)
        check("D9.H0 D9 服务启动可访问", up)
        if not up:
            return
        s, j = http_json_port(port, "GET", "/api/drawdown")
        check("D9.H1 /api/drawdown 200＋九指数 OK",
              s == 200 and len(j.get("indices") or []) == 9
              and all(x["status"] == "OK" for x in j["indices"]),
              {"status": s})
        dd = {x["code"]: x for x in j["indices"]}
        check("D9.H2 宽基有真实收盘/最高/回撤（非 NA）",
              all(dd[c]["currentClose"] and dd[c]["highestClose"]
                  and dd[c]["drawdown"] is not None for c in ("000300", "000905", "000852")))
        check("D9.H3 note/asOf 随接口下发",
              bool(j.get("asOf")) and "近似数据" in (j.get("note") or ""))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        check("D9.H4 D9 服务进程干净退出", proc.returncode is not None, proc.returncode)


def test_d9_page_contract() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check("D9.P1 脚注渲染回撤数据来源行（ddNote）",
          "ddNote" in html and "drawdownMeta.note" in html)

# ------------------------------------- D10) 宽基风险溢价 PE 口径反推（参考站同款公式）
def test_d10_rp_fallback() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check("D10.1 rp1 反推代码在位（100−PE分位，标估算）",
          "100-Number(r.v)" in html and "风险溢价(PE口径)反推" in html)
    m = re.search(r"const MARKET_DATA=(\{.*?\});", html, re.S)
    check("D10.2 MARKET_DATA 可解析", bool(m))
    if m:
        md = json.loads(m.group(1))
        exp = {"000300": (63.8, 36.2), "000905": (77.7, 22.3), "000852": (69.8, 30.2)}
        got = {c: (md[c]["public"]["pePct"], round(100 - md[c]["public"]["pePct"], 2))
               for c in exp}
        check("D10.3 宽基 PE 分位→rp1 反推值（36.2/22.3/30.2）", got == exp, got)
    check("D10.4 脚注声明 PE 口径反推＋股息率口径仍 NA",
          "100−PE分位公式反推估算" in html and "股息率口径无授权同口径来源" in html)

def main() -> int:
    try:
        test_migration()
        test_semantics()
        test_concurrency()
        test_wal_and_restart()
        test_backup_restore()
        test_d2_plans()
        test_d3_flow()
        test_d4_drawdown_algorithm()
        test_d4_page_contract()
        test_d4_http()
        test_http()
        test_d3_http_restart()
        test_d5_non_current_constituent()
        test_d5_quote_health()
        test_d5_drawdown_sampling()
        test_d5_page_contract()
        test_d5_holdings_http()
        test_d7_delete_batch()
        test_d7_page_contract()
        test_d7_http()
        test_d8_revert()
        test_d8_revert_http()
        test_d8_page_contract()
        test_d9_drawdown_file()
        test_d9_drawdown_board()
        test_d9_drawdown_http()
        test_d9_page_contract()
        test_d10_rp_fallback()
    finally:
        passed = sum(1 for _n, ok, _d in RESULTS if ok)
        failed = [n for n, ok, _d in RESULTS if not ok]
        print("\n================ D1..D10 实测矩阵汇总 ================")
        print("合计 %d 项：PASS %d / FAIL %d" % (len(RESULTS), passed, len(RESULTS) - passed))
        if failed:
            print("失败项：")
            for n in failed:
                print("  - " + n)
        print("临时目录（可整目录删除）：%s" % TMP)
        print("正式库/生产目录：全程未触碰")
    return 1 if any(not ok for _n, ok, _d in RESULTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
