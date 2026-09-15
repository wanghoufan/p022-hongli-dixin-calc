#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repository 层：只写 SQL，不含业务规则（规则在 service.py）。

所有写操作都在调用方给出的单写事务（connection.write_tx）内执行；
本层不自行 BEGIN / COMMIT。
"""
from __future__ import annotations

import sqlite3

CYCLE_FIELDS = "cycle_id, name, status, note, created_at, updated_at, closed_at"
BATCH_FIELDS = ("batch_id, cycle_id, kind, status, revision, algorithm_version, "
                "plan_json, frozen_at, note, created_at, updated_at")
ORDER_ITEM_FIELDS = ("order_item_id, batch_id, code, name, market, side, target_weight, "
                     "reference_price_cents, suggested_qty, status, revision, note, "
                     "created_at, updated_at")
TRANSACTION_FIELDS = ("transaction_id, cycle_id, batch_id, order_item_id, code, name, side, "
                      "qty, price_cents, reference_price_cents, amount_cents, confirmed, "
                      "confirmed_at, source, note, idempotency_key, created_at, updated_at")
CASH_FIELDS = ("cash_event_id, cycle_id, transaction_id, event_type, amount_cents, note, "
               "occurred_at, idempotency_key, created_at")


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


class CycleRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT %s FROM cycles ORDER BY cycle_id" % CYCLE_FIELDS))

    def get(self, cycle_id: int) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM cycles WHERE cycle_id = ?" % CYCLE_FIELDS, (cycle_id,)).fetchone())

    def exists(self, cycle_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone() is not None

    def create(self, name: str, note: str, now: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO cycles (name, status, note, created_at, updated_at) "
            "VALUES (?, 'OPEN', ?, ?, ?)", (name, note, now, now))
        return self.get(int(cur.lastrowid))

    def close(self, cycle_id: int, now: str) -> dict | None:
        """OPEN → CLOSED（清仓后关闭；closed_at/updated_at 落盘）。"""
        self.conn.execute(
            "UPDATE cycles SET status = 'CLOSED', closed_at = ?, updated_at = ? "
            "WHERE cycle_id = ?", (now, now, cycle_id))
        return self.get(cycle_id)


class BatchRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self, cycle_id: int | None = None) -> list[dict]:
        if cycle_id is None:
            return _rows(self.conn.execute(
                "SELECT %s FROM batches ORDER BY batch_id" % BATCH_FIELDS))
        return _rows(self.conn.execute(
            "SELECT %s FROM batches WHERE cycle_id = ? ORDER BY batch_id" % BATCH_FIELDS,
            (cycle_id,)))

    def get(self, batch_id: int) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM batches WHERE batch_id = ?" % BATCH_FIELDS, (batch_id,)).fetchone())

    def create(self, cycle_id: int, kind: str, note: str, algorithm_version: str,
               revision: int, now: str, status: str = "DRAFT") -> dict:
        cur = self.conn.execute(
            "INSERT INTO batches (cycle_id, kind, status, revision, algorithm_version, note, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cycle_id, kind, status, revision, algorithm_version, note, now, now))
        return self.get(int(cur.lastrowid))

    def freeze(self, batch_id: int, revision: int, algorithm_version: str, plan_json: str,
               now: str, status: str = "FROZEN") -> dict | None:
        """落冻结快照：plan_json + frozen_at + revision；revision 只增不减。"""
        self.conn.execute(
            "UPDATE batches SET revision = ?, algorithm_version = ?, plan_json = ?, "
            "frozen_at = ?, status = ?, updated_at = ? WHERE batch_id = ?",
            (revision, algorithm_version, plan_json, now, status, now, batch_id))
        return self.get(batch_id)

    def set_status(self, batch_id: int, status: str, now: str) -> dict | None:
        self.conn.execute(
            "UPDATE batches SET status = ?, updated_at = ? WHERE batch_id = ?",
            (status, now, batch_id))
        return self.get(batch_id)

    def delete(self, batch_id: int) -> int:
        """受控删除批次行（D7 删除测试批次；调用方已在本事务内写入删除授权）。"""
        cur = self.conn.execute("DELETE FROM batches WHERE batch_id = ?", (batch_id,))
        return int(cur.rowcount)


class OrderItemRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self, batch_id: int | None = None, revision: int | None = None,
             latest_only: bool = False) -> list[dict]:
        if batch_id is None:
            return _rows(self.conn.execute(
                "SELECT %s FROM order_items ORDER BY order_item_id" % ORDER_ITEM_FIELDS))
        if latest_only:
            rev = self.max_revision(batch_id)
            if rev <= 0:
                return []
            return _rows(self.conn.execute(
                "SELECT %s FROM order_items WHERE batch_id = ? AND revision = ? "
                "ORDER BY order_item_id" % ORDER_ITEM_FIELDS, (batch_id, rev)))
        if revision is not None:
            return _rows(self.conn.execute(
                "SELECT %s FROM order_items WHERE batch_id = ? AND revision = ? "
                "ORDER BY order_item_id" % ORDER_ITEM_FIELDS, (batch_id, revision)))
        return _rows(self.conn.execute(
            "SELECT %s FROM order_items WHERE batch_id = ? ORDER BY revision, order_item_id"
            % ORDER_ITEM_FIELDS, (batch_id,)))

    def max_revision(self, batch_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(revision), 0) AS r FROM order_items WHERE batch_id = ?",
            (batch_id,)).fetchone()
        return int(row["r"] or 0)

    def set_status(self, order_item_id: int, status: str, now: str) -> dict | None:
        self.conn.execute(
            "UPDATE order_items SET status = ?, updated_at = ? WHERE order_item_id = ?",
            (status, now, order_item_id))
        return self.get(order_item_id)

    def count_by_status(self, batch_id: int) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM order_items WHERE batch_id = ? GROUP BY status",
            (batch_id,)).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    def get(self, order_item_id: int) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM order_items WHERE order_item_id = ?" % ORDER_ITEM_FIELDS,
            (order_item_id,)).fetchone())

    def delete_by_batch(self, batch_id: int) -> int:
        """删除该批次全部 revision 的下单行（D7；调用方已写删除授权）。"""
        cur = self.conn.execute("DELETE FROM order_items WHERE batch_id = ?", (batch_id,))
        return int(cur.rowcount)

    def create(self, batch_id: int, code: str, name: str, market: str, side: str,
               target_weight, reference_price_cents, suggested_qty: int, revision: int,
               note: str, now: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO order_items (batch_id, code, name, market, side, target_weight, "
            "reference_price_cents, suggested_qty, status, revision, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)",
            (batch_id, code, name, market, side, target_weight, reference_price_cents,
             suggested_qty, revision, note, now, now))
        return self.get(int(cur.lastrowid))


class TransactionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self, cycle_id: int | None = None, code: str | None = None,
             confirmed: bool | None = None) -> list[dict]:
        sql = "SELECT %s FROM transactions WHERE 1=1" % TRANSACTION_FIELDS
        args: list = []
        if cycle_id is not None:
            sql += " AND cycle_id = ?"
            args.append(cycle_id)
        if code is not None:
            sql += " AND code = ?"
            args.append(code)
        if confirmed is not None:
            sql += " AND confirmed = ?"
            args.append(1 if confirmed else 0)
        sql += " ORDER BY transaction_id"
        return _rows(self.conn.execute(sql, args))

    def get(self, transaction_id: int) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM transactions WHERE transaction_id = ?" % TRANSACTION_FIELDS,
            (transaction_id,)).fetchone())

    def find_by_idempotency_key(self, key: str) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM transactions WHERE idempotency_key = ?" % TRANSACTION_FIELDS,
            (key,)).fetchone())

    def create(self, *, cycle_id: int, batch_id, order_item_id, code: str, name: str, side: str,
               qty: int, price_cents, reference_price_cents, amount_cents: int,
               confirmed_at, source: str, note: str, idempotency_key, now: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO transactions (cycle_id, batch_id, order_item_id, code, name, side, qty, "
            "price_cents, reference_price_cents, amount_cents, confirmed, confirmed_at, source, "
            "note, idempotency_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
            (cycle_id, batch_id, order_item_id, code, name, side, qty, price_cents,
             reference_price_cents, amount_cents, confirmed_at, source, note,
             idempotency_key, now, now))
        return self.get(int(cur.lastrowid))

    def holding_qty(self, cycle_id: int, code: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END), 0) AS qty "
            "FROM transactions WHERE confirmed = 1 AND cycle_id = ? AND code = ?",
            (cycle_id, code)).fetchone()
        return int(row["qty"] or 0)

    def list_by_batch(self, batch_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT %s FROM transactions WHERE batch_id = ? ORDER BY transaction_id"
            % TRANSACTION_FIELDS, (batch_id,)))

    def delete_by_batch(self, batch_id: int) -> int:
        """删除该批次交易（D7；仅当 ledger_batch_deletions 已授权，否则触发器 ABORT）。"""
        cur = self.conn.execute("DELETE FROM transactions WHERE batch_id = ?", (batch_id,))
        return int(cur.rowcount)

    def list_by_order_item(self, order_item_id: int) -> list[dict]:
        """该下单行联动写入的全部成交（D8 撤销用）。"""
        return _rows(self.conn.execute(
            "SELECT %s FROM transactions WHERE order_item_id = ? ORDER BY transaction_id"
            % TRANSACTION_FIELDS, (order_item_id,)))

    def delete_by_ids(self, tx_ids: list[int]) -> int:
        """按单笔删除成交（D8；仅当 ledger_reverts 已授权对应单笔，否则触发器 ABORT）。"""
        if not tx_ids:
            return 0
        q = ",".join("?" for _ in tx_ids)
        cur = self.conn.execute(
            "DELETE FROM transactions WHERE transaction_id IN (%s)" % q, list(tx_ids))
        return int(cur.rowcount)

    def holdings(self, cycle_id: int | None = None, include_zero: bool = False) -> list[dict]:
        sql = ("SELECT cycle_id, code, name, qty, net_cost_cents, buy_count, sell_count "
               "FROM v_holdings")
        args: list = []
        if cycle_id is not None:
            sql += " WHERE cycle_id = ?"
            args.append(cycle_id)
        if not include_zero:
            sql += (" AND" if cycle_id is not None else " WHERE") + " qty <> 0"
        sql += " ORDER BY cycle_id, code"
        return _rows(self.conn.execute(sql, args))


class CashLedgerRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self, cycle_id: int | None = None) -> list[dict]:
        if cycle_id is None:
            return _rows(self.conn.execute(
                "SELECT %s FROM cash_ledger ORDER BY cash_event_id" % CASH_FIELDS))
        return _rows(self.conn.execute(
            "SELECT %s FROM cash_ledger WHERE cycle_id = ? ORDER BY cash_event_id" % CASH_FIELDS,
            (cycle_id,)))

    def balance_cents(self, cycle_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS bal FROM cash_ledger WHERE cycle_id = ?",
            (cycle_id,)).fetchone()
        return int(row["bal"] or 0)

    def find_by_idempotency_key(self, key: str) -> dict | None:
        return _row(self.conn.execute(
            "SELECT %s FROM cash_ledger WHERE idempotency_key = ?" % CASH_FIELDS, (key,)).fetchone())

    def append(self, *, cycle_id: int, transaction_id, event_type: str, amount_cents: int,
               note: str, occurred_at: str, idempotency_key, now: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO cash_ledger (cycle_id, transaction_id, event_type, amount_cents, note, "
            "occurred_at, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cycle_id, transaction_id, event_type, amount_cents, note, occurred_at,
             idempotency_key, now))
        return _row(self.conn.execute(
            "SELECT %s FROM cash_ledger WHERE cash_event_id = ?" % CASH_FIELDS,
            (int(cur.lastrowid),)).fetchone())

    def delete_by_batch(self, batch_id: int) -> int:
        """删除该批次交易所关联的现金事件（D7；触发器同受 ledger_batch_deletions 授权约束）。"""
        cur = self.conn.execute(
            "DELETE FROM cash_ledger WHERE transaction_id IN "
            "(SELECT transaction_id FROM transactions WHERE batch_id = ?)", (batch_id,))
        return int(cur.rowcount)

    def delete_by_tx_ids(self, tx_ids: list[int]) -> int:
        """按单笔删除现金事件（D8；仅当 ledger_reverts 已授权对应单笔，否则触发器 ABORT）。"""
        if not tx_ids:
            return 0
        q = ",".join("?" for _ in tx_ids)
        cur = self.conn.execute(
            "DELETE FROM cash_ledger WHERE transaction_id IN (%s)" % q, list(tx_ids))
        return int(cur.rowcount)


class LedgerAuditRepository:
    """D7 审计与删除授权（ledger_audit / ledger_batch_deletions）。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def authorize_batch(self, batch_id: int, cycle_id, confirmed_count: int, detail: str,
                        now: str) -> None:
        """先写删除授权，再删 transactions/cash_ledger（触发器据此放行）。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO ledger_batch_deletions "
            "(batch_id, cycle_id, confirmed_count, detail, deleted_at) VALUES (?, ?, ?, ?, ?)",
            (batch_id, cycle_id, int(confirmed_count), detail, now))

    def authorize_revert(self, order_item_id, cycle_id, batch_id: int,
                           tx_ids: list[int], detail: str, now: str) -> None:
        """先写单行撤销授权，再删事实行（触发器据此按单笔放行）。"""
        idlist = "," + ",".join(str(int(t)) for t in tx_ids) + "," if tx_ids else ""
        self.conn.execute(
            "INSERT INTO ledger_reverts "
            "(order_item_id, cycle_id, batch_id, transaction_ids, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_item_id, cycle_id, batch_id, idlist, detail, now))

    def record(self, action: str, entity: str, entity_id, detail: str, now: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO ledger_audit (action, entity, entity_id, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (action, entity, entity_id, detail, now))
        return _row(self.conn.execute(
            "SELECT audit_id, action, entity, entity_id, detail, created_at FROM ledger_audit "
            "WHERE audit_id = ?", (int(cur.lastrowid),)).fetchone())
