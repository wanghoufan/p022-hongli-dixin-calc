#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Service 层：业务规则、校验、幂等、单写事务编排（D1）。

规则要点：
- 写操作一律走 connection.write_tx（BEGIN IMMEDIATE），一请求一事务，一次一写者。
- transactions 只接受 confirmed=true（人工核实已成交/已卖出成交）。
- 普通 A 股 100 股整手；卖出不得超过该 cycle 已确认持仓（禁止裸空）。
- 现金为追加式事件账本；确认一笔交易时默认同步追加一条关联现金事件（幂等键 tx:<id>）。
- 持仓不落表，由 confirmed 交易聚合重建（v_holdings）。
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .connection import LedgerError, connect, pragma_snapshot, resolve_db_path, write_tx
from .migrate import apply_migrations, migration_status
from .repository import (
    BatchRepository,
    CashLedgerRepository,
    CycleRepository,
    LedgerAuditRepository,
    OrderItemRepository,
    TransactionRepository,
)

TZ8 = timezone(timedelta(hours=8))
LOT_SIZE = 100  # 普通 A 股整手（人类 APPROVED 2026-09-15）
PLAN_ALGORITHM_VERSION = "d2-1"  # 四生命周期计划算法版本（透明可追溯）

BATCH_KINDS = ("INITIAL", "ADD", "REBALANCE", "EXIT")
SIDES = ("BUY", "SELL")
# 下单行四态：CONFIRMED 仅由 record_transaction 联动写入，其余经 state 接口（D3）
ORDER_ITEM_STATES = ("PENDING", "CONFIRMED", "SKIPPED", "REVIEW")
# D7 删除测试批次：含 CONFIRMED 行的批次需人工输入该确认词（二次确认）。
DELETE_CONFIRM_TEXT = "确认删除"
# D8 撤销已确认成交：单行撤销需人工输入该确认词（二次确认）。
REVERT_CONFIRM_TEXT = "撤销确认"
CASH_EVENT_TYPES = ("OPENING", "DEPOSIT", "WITHDRAW", "BUY", "SELL", "ADJUSTMENT")
POSITIVE_ONLY = ("DEPOSIT", "SELL")
NEGATIVE_ONLY = ("WITHDRAW", "BUY")

_CODE_RE = re.compile(r"^\d{6}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

_MIG_LOCK = threading.Lock()
_MIGRATED_PATHS: set[str] = set()


def now_cn() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")


def _text(value, field: str, *, maxlen: int = 200, required: bool = False) -> str:
    if value is None:
        if required:
            raise LedgerError("缺少字段 %s" % field)
        return ""
    if not isinstance(value, str):
        raise LedgerError("字段 %s 必须是字符串" % field)
    value = value.strip()
    if required and not value:
        raise LedgerError("字段 %s 不能为空" % field)
    if len(value) > maxlen:
        raise LedgerError("字段 %s 超长（>%d）" % (field, maxlen))
    return value


def _int_value(value, field: str, *, minimum=None, maximum=None, required: bool = True):
    if isinstance(value, bool):
        raise LedgerError("字段 %s 必须是整数" % field)
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[+-]?\d+", text):
            value = int(text)
    if value is None:
        if required:
            raise LedgerError("缺少字段 %s" % field)
        return None
    if not isinstance(value, int):
        raise LedgerError("字段 %s 必须是整数" % field)
    if minimum is not None and value < minimum:
        raise LedgerError("字段 %s 必须 >= %s" % (field, minimum))
    if maximum is not None and value > maximum:
        raise LedgerError("字段 %s 必须 <= %s" % (field, maximum))
    return value


def _code(value) -> str:
    code = _text(value, "code", maxlen=6, required=True)
    if not _CODE_RE.match(code):
        raise LedgerError("code 必须是 6 位数字")
    return code


def _choice(value, field: str, allowed: tuple) -> str:
    text = _text(value, field, maxlen=20, required=True).upper()
    if text not in allowed:
        raise LedgerError("字段 %s 只允许 %s" % (field, "/".join(allowed)))
    return text


def _time_value(value, field: str, default: str) -> str:
    if value is None or value == "":
        return default
    text = _text(value, field, maxlen=40, required=True)
    if not _TIME_RE.match(text):
        raise LedgerError("字段 %s 需形如 2026-09-15T20:00:00+08:00" % field)
    return text


def _weight(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LedgerError("字段 target_weight 必须是数字")
    return float(value)


def _number(value, field: str, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LedgerError("字段 %s 必须是数字" % field)
    value = float(value)
    if minimum is not None and value < minimum:
        raise LedgerError("字段 %s 必须 >= %s" % (field, minimum))
    return value


def _normalize_weights(raw) -> tuple[list[dict], float]:
    """目标权重（当前指数成分/权重）：[{code,name,market,weight}]。"""
    if raw is None:
        return [], 0.0
    if not isinstance(raw, list):
        raise LedgerError("weights 必须是数组")
    out: list[dict] = []
    total = 0.0
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise LedgerError("weights[%d] 必须是对象" % i)
        code = _code(item.get("code"))
        if code in seen:
            raise LedgerError("weights 出现重复 code：%s" % code)
        seen.add(code)
        name = _text(item.get("name"), "name", maxlen=40) or code
        market = _text(item.get("market"), "market", maxlen=2).upper()
        if market not in ("", "SH", "SZ"):
            raise LedgerError("weights[%d].market 只允许 SH/SZ/空" % i)
        weight = item.get("weight", item.get("target_weight"))
        if weight is None:
            raise LedgerError("weights[%d] 缺少 weight" % i)
        weight = _number(weight, "weight", minimum=0.0)
        out.append({"code": code, "name": name, "market": market, "weight": weight})
        total += weight
    if not out:
        raise LedgerError("weights 不能为空（需当前指数成分权重，不补造数）")
    if total <= 0:
        raise LedgerError("weights 权重和必须为正")
    return out, total


def _normalize_quotes(raw) -> dict[str, dict]:
    """行情输入（含来源/时间）：数组或 {code: price_cents|{...}}；金额单位为分。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = []
        for code, v in raw.items():
            if isinstance(v, dict):
                items.append({"code": code, **v})
            else:
                items.append({"code": code, "price_cents": v})
    elif isinstance(raw, list):
        items = raw
    else:
        raise LedgerError("quotes 必须是对象或数组")
    out: dict[str, dict] = {}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise LedgerError("quotes[%d] 必须是对象" % i)
        code = _code(item.get("code"))
        price_cents = _int_value(item.get("price_cents"), "price_cents", minimum=1)
        out[code] = {
            "price_cents": price_cents,
            "source": _text(item.get("source"), "source", maxlen=80),
            "fetched_at": _text(item.get("fetched_at"), "fetched_at", maxlen=40),
        }
    return out


def _allocate_by_weight(total_cents: int, weights: list[dict]) -> list[int]:
    """按权重分配整数分目标，最大余数法保证 sum(targets) == total_cents。"""
    n = len(weights)
    if n == 0 or total_cents <= 0:
        return [0] * n
    weight_sum = sum(w["weight"] for w in weights)
    raw = [total_cents * w["weight"] / weight_sum for w in weights]
    floors = [int(x // 1) for x in raw]
    remainder = int(total_cents - sum(floors))
    order = sorted(range(n), key=lambda i: (raw[i] - floors[i], weights[i]["weight"]),
                   reverse=True)
    for i in order[:max(0, remainder)]:
        floors[i] += 1
    return floors


def _assert_plan_invariants(plan: dict) -> None:
    """P0#7 数学不变量：逐行/总额双校验（实际投入 − 理论目标）。"""
    rows = plan["rows"]
    for r in rows:
        if int(r["deviation_cents"]) != int(r["actual_amount_cents"]) - int(r["target_amount_cents"]):
            raise LedgerError(
                "数学不变量失败：行偏差 != 实际投入 - 理论目标（code=%s）" % r["code"])
    target_sum = sum(int(r["target_amount_cents"]) for r in rows)
    actual_sum = sum(int(r["actual_amount_cents"]) for r in rows)
    totals = plan["totals"]
    if int(totals["target_total_cents"]) != target_sum:
        raise LedgerError("数学不变量失败：理论总额 != 逐行理论目标之和")
    if int(totals["actual_total_cents"]) != actual_sum:
        raise LedgerError("数学不变量失败：实际总额 != 逐行实际投入之和")
    if int(totals["deviation_total_cents"]) != actual_sum - target_sum:
        raise LedgerError("数学不变量失败：偏差和 != 实际总额 - 理论总额")



class LedgerService:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    # ------------------------------------------------------------ 连接
    def ensure_migrated(self) -> None:
        key = str(resolve_db_path(self.db_path))
        with _MIG_LOCK:
            if key in _MIGRATED_PATHS:
                return
            conn = connect(self.db_path)
            try:
                apply_migrations(conn)
            finally:
                conn.close()
            _MIGRATED_PATHS.add(key)

    def _open(self) -> sqlite3.Connection:
        self.ensure_migrated()
        return connect(self.db_path)

    # ------------------------------------------------------------ 状态
    def status(self, deep: bool = False) -> dict:
        conn = self._open()
        try:
            st = migration_status(conn)
            snap = pragma_snapshot(conn)
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            counts = {}
            for t in tables:
                counts[t] = conn.execute("SELECT COUNT(*) AS n FROM %s" % t).fetchone()["n"]
            out = {
                "db_path": str(resolve_db_path(self.db_path)),
                "schema_version": st["user_version"],
                "applied_migrations": st["applied"],
                "pending_migrations": st["pending"],
                "pragmas": snap,
                "tables": tables,
                "row_counts": counts,
            }
            if deep:
                integrity = conn.execute("PRAGMA integrity_check").fetchall()
                out["integrity_check"] = [list(r)[0] for r in integrity]
                fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
                out["foreign_key_check"] = {"violations": len(fk_rows),
                                            "sample": [dict(r) for r in fk_rows[:5]]}
            return out
        finally:
            conn.close()

    # ------------------------------------------------------------ cycles
    def list_cycles(self) -> dict:
        conn = self._open()
        try:
            return {"cycles": CycleRepository(conn).list()}
        finally:
            conn.close()

    def create_cycle(self, payload: dict) -> dict:
        name = _text(payload.get("name"), "name", maxlen=120)
        note = _text(payload.get("note"), "note", maxlen=1000)
        conn = self._open()
        try:
            with write_tx(conn):
                cycle = CycleRepository(conn).create(name, note, now_cn())
            return {"cycle": cycle}
        finally:
            conn.close()

    # ------------------------------------------------------------ batches
    def list_batches(self, cycle_id=None) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1, required=False)
        conn = self._open()
        try:
            return {"batches": BatchRepository(conn).list(cycle_id)}
        finally:
            conn.close()

    def create_batch(self, payload: dict) -> dict:
        cycle_id = _int_value(payload.get("cycle_id"), "cycle_id", minimum=1)
        kind = _choice(payload.get("kind"), "kind", BATCH_KINDS)
        note = _text(payload.get("note"), "note", maxlen=1000)
        algorithm_version = _text(payload.get("algorithm_version"), "algorithm_version", maxlen=40)
        revision = _int_value(payload.get("revision"), "revision", minimum=1, required=False) or 1
        conn = self._open()
        try:
            with write_tx(conn):
                cycle = CycleRepository(conn).get(cycle_id)
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能新增批次", status=409)
                batch = BatchRepository(conn).create(
                    cycle_id, kind, note, algorithm_version, revision, now_cn())
            return {"batch": batch}
        finally:
            conn.close()

    # ------------------------------------------------------- order-items
    def list_order_items(self, batch_id=None, revision=None, latest_only=False) -> dict:
        batch_id = _int_value(batch_id, "batch_id", minimum=1, required=False)
        revision = _int_value(revision, "revision", minimum=1, required=False)
        conn = self._open()
        try:
            items = OrderItemRepository(conn).list(batch_id, revision, bool(latest_only))
            return {"order_items": items}
        finally:
            conn.close()

    def create_order_item(self, payload: dict) -> dict:
        batch_id = _int_value(payload.get("batch_id"), "batch_id", minimum=1)
        code = _code(payload.get("code"))
        name = _text(payload.get("name"), "name", maxlen=40)
        market = _text(payload.get("market"), "market", maxlen=2).upper()
        if market not in ("", "SH", "SZ"):
            raise LedgerError("字段 market 只允许 SH/SZ/空")
        side = _choice(payload.get("side"), "side", SIDES)
        target_weight = _weight(payload.get("target_weight"))
        reference_price_cents = _int_value(payload.get("reference_price_cents"),
                                           "reference_price_cents", minimum=1, required=False)
        suggested_qty = _int_value(payload.get("suggested_qty"), "suggested_qty",
                                   minimum=0, required=False) or 0
        if suggested_qty % LOT_SIZE:
            raise LedgerError("suggested_qty 必须为 %d 股整手" % LOT_SIZE)
        revision = _int_value(payload.get("revision"), "revision", minimum=1, required=False) or 1
        note = _text(payload.get("note"), "note", maxlen=500)
        conn = self._open()
        try:
            with write_tx(conn):
                batch = BatchRepository(conn).get(batch_id)
                if batch is None:
                    raise LedgerError("batch 不存在：%s" % batch_id, status=404)
                cycle = CycleRepository(conn).get(batch["cycle_id"])
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % batch["cycle_id"], status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能新增下单行", status=409)
                item = OrderItemRepository(conn).create(
                    batch_id, code, name, market, side, target_weight, reference_price_cents,
                    suggested_qty, revision, note, now_cn())
            return {"order_item": item}
        finally:
            conn.close()

    # ------------------------------------ 下单行四态机 / 完成门禁（D3）
    def set_order_item_state(self, order_item_id, payload: dict) -> dict:
        """人工四态流转：PENDING ↔ SKIPPED / REVIEW。

        - CONFIRMED 只能由 record_transaction 联动写入，本接口拒绝（409）。
        - 已 CONFIRMED 不可逆转（409）。
        - 只允许变更当前最新 revision 的下单行，避免旧 revision 残留行被误改。
        """
        order_item_id = _int_value(order_item_id, "order_item_id", minimum=1)
        target = _choice(payload.get("status"), "status", ORDER_ITEM_STATES)
        if target == "CONFIRMED":
            raise LedgerError("CONFIRMED 只能经 record_transaction 联动写入，不能经状态接口设置",
                              status=409)
        conn = self._open()
        try:
            with write_tx(conn):
                items = OrderItemRepository(conn)
                item = items.get(order_item_id)
                if item is None:
                    raise LedgerError("order_item 不存在：%s" % order_item_id, status=404)
                batch = BatchRepository(conn).get(item["batch_id"])
                if batch is None:
                    raise LedgerError("batch 不存在：%s" % item["batch_id"], status=404)
                cycle = CycleRepository(conn).get(batch["cycle_id"])
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % batch["cycle_id"], status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能变更下单行状态", status=409)
                if item["status"] == "CONFIRMED":
                    raise LedgerError("order_item 已 CONFIRMED，不可逆转", status=409)
                if int(item["revision"]) != items.max_revision(item["batch_id"]):
                    raise LedgerError("只能变更最新 revision 的下单行", status=409)
                item = items.set_status(order_item_id, target, now_cn())
            return {"order_item": item}
        finally:
            conn.close()

    # --------------------------------------------- 撤销已确认成交（D8 / Change B）
    def revert_confirmation(self, order_item_id, payload: dict | None = None) -> dict:
        """单行撤销已确认成交（用户 2026-09-16 明确要求已确认可撤销/清空）。

        - 仅 CONFIRMED 行可撤销，否则 400；周期 CLOSED 拒绝（409）。
        - 必须携带 confirm_text == '撤销确认'（二次确认），否则 400。
        - 受控回退：先写 ledger_reverts 单笔授权，再删该行联动的成交＋现金事件，
          行状态回 PENDING；全过程单写事务，异常整体回滚，并写 ledger_audit 审计事件。
        - 无联动成交的 CONFIRMED 行（脏数据）：仅回状态＋审计，不删事实。
        """
        order_item_id = _int_value(order_item_id, "order_item_id", minimum=1)
        payload = dict(payload or {})
        confirm_text = _text(payload.get("confirm_text"), "confirm_text", maxlen=20)
        conn = self._open()
        try:
            with write_tx(conn):
                items = OrderItemRepository(conn)
                item = items.get(order_item_id)
                if item is None:
                    raise LedgerError("order_item 不存在：%s" % order_item_id, status=404)
                batch = BatchRepository(conn).get(item["batch_id"])
                if batch is None:
                    raise LedgerError("batch 不存在：%s" % item["batch_id"], status=404)
                cycle = CycleRepository(conn).get(batch["cycle_id"])
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % batch["cycle_id"], status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能撤销已确认成交",
                                      status=409)
                if item["status"] != "CONFIRMED":
                    raise LedgerError("只有已确认成交（CONFIRMED）的行可撤销，当前状态=%s"
                                      % item["status"], status=400)
                if confirm_text != REVERT_CONFIRM_TEXT:
                    raise LedgerError("撤销已确认成交必须输入“%s”四字二次确认"
                                      % REVERT_CONFIRM_TEXT, status=400)
                txs = TransactionRepository(conn).list_by_order_item(order_item_id)
                tx_ids = [int(t["transaction_id"]) for t in txs]
                now = now_cn()
                detail = json.dumps({
                    "order_item_id": order_item_id, "batch_id": item["batch_id"],
                    "cycle_id": batch["cycle_id"], "code": item["code"],
                    "transactions": len(tx_ids), "transaction_ids": tx_ids,
                    "confirm_text": confirm_text,
                }, ensure_ascii=False)
                audit = LedgerAuditRepository(conn)
                audit.authorize_revert(order_item_id, batch["cycle_id"], item["batch_id"],
                                       tx_ids, detail, now)
                cash_deleted = CashLedgerRepository(conn).delete_by_tx_ids(tx_ids)
                tx_deleted = TransactionRepository(conn).delete_by_ids(tx_ids)
                item = items.set_status(order_item_id, "PENDING", now)
                entry = audit.record("REVERT_CONFIRM", "order_item", order_item_id,
                                     detail, now)
            return {
                "reverted": True, "order_item": item,
                "transactions_deleted": tx_deleted, "cash_events_deleted": cash_deleted,
                "audit": entry,
            }
        finally:
            conn.close()

    def batch_progress(self, batch_id) -> dict:
        """批次进度 + 完成门禁：按最新 revision 统计四态，返回 progressing/blocked/done。"""
        batch_id = _int_value(batch_id, "batch_id", minimum=1)
        conn = self._open()
        try:
            batch = BatchRepository(conn).get(batch_id)
            if batch is None:
                raise LedgerError("batch 不存在：%s" % batch_id, status=404)
            items_repo = OrderItemRepository(conn)
            revision = items_repo.max_revision(batch_id)
            items = items_repo.list(batch_id, latest_only=True)
            counts = {state: 0 for state in ORDER_ITEM_STATES}
            for it in items:
                if it["status"] in counts:
                    counts[it["status"]] += 1
            total = len(items)
            pending, confirmed = counts["PENDING"], counts["CONFIRMED"]
            skipped, review = counts["SKIPPED"], counts["REVIEW"]
            if total == 0:
                gate, reason = "blocked", "批次尚无下单行（可能尚未冻结）"
            elif review > 0:
                gate, reason = "blocked", "存在 %d 条待复核（REVIEW）行，须先处理" % review
            elif pending > 0:
                gate, reason = "progressing", "仍有 %d 条待下单（PENDING）行" % pending
            else:
                gate, reason = "done", "全部下单行已确认成交或跳过"
            cycle = CycleRepository(conn).get(batch["cycle_id"])
            batch_out = {k: v for k, v in batch.items() if k != "plan_json"}
            return {
                "batch": batch_out,
                "cycle": cycle,
                "revision": revision,
                "counts": counts,
                "total": total,
                "pending": pending,
                "confirmed": confirmed,
                "skipped": skipped,
                "review": review,
                "processed": confirmed + skipped,
                "confirmed_transactions": len(TransactionRepository(conn).list_by_batch(batch_id)),
                "gate": gate,
                "can_complete": gate == "done",
                "gate_reason": reason,
                "order_items": items,
            }
        finally:
            conn.close()

    # --------------------------------------------- 删除测试批次（D7 / Change B）
    def delete_batch(self, batch_id, payload: dict | None = None) -> dict:
        """整批删除测试批次：order_items + transactions + 关联现金事件。

        - CLOSED 周期拒绝（409）：关闭后的历史批次不可删。
        - 含 CONFIRMED 行的批次必须携带 confirm_text == '确认删除'（二次确认），否则 400。
        - 受控删除：先写 ledger_batch_deletions 授权，再删事实行（触发器据此放行）；
          全过程单写事务，异常整体回滚，并写 ledger_audit 审计事件。
        """
        batch_id = _int_value(batch_id, "batch_id", minimum=1)
        payload = dict(payload or {})
        confirm_text = _text(payload.get("confirm_text"), "confirm_text", maxlen=20)
        conn = self._open()
        try:
            with write_tx(conn):
                batches = BatchRepository(conn)
                batch = batches.get(batch_id)
                if batch is None:
                    raise LedgerError("batch 不存在：%s" % batch_id, status=404)
                cycle = CycleRepository(conn).get(batch["cycle_id"])
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % batch["cycle_id"], status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），拒绝删除批次", status=409)
                items = OrderItemRepository(conn).list(batch_id)
                confirmed = [i for i in items if i["status"] == "CONFIRMED"]
                # 事实成交（transactions）为准：record_transaction 允许不给 order_item_id，
                # 此时 order_item 仍 PENDING 但已写入 confirmed 成交，必须同样要求 typed 确认。
                txs = TransactionRepository(conn).list_by_batch(batch_id)
                confirmed_tx = [t for t in txs if int(t["confirmed"]) == 1]
                confirmed_facts = len(confirmed) + max(0, len(confirmed_tx) - len(confirmed))
                if confirmed_facts and confirm_text != DELETE_CONFIRM_TEXT:
                    raise LedgerError(
                        "批次含 %d 条已在账本的确认成交（order_item 已确认 %d 条 / 成交记录 %d 条），"
                        "必须输入“%s”四字才可删除"
                        % (confirmed_facts, len(confirmed), len(confirmed_tx), DELETE_CONFIRM_TEXT),
                        status=400)
                tx_ids = [int(t["transaction_id"]) for t in txs]
                detail = json.dumps({
                    "batch_id": batch_id, "cycle_id": batch["cycle_id"], "kind": batch["kind"],
                    "batch_status": batch["status"], "revision": batch["revision"],
                    "order_items": len(items), "confirmed_items": len(confirmed),
                    "confirmed_transactions": len(confirmed_tx), "confirmed_facts": confirmed_facts,
                    "transactions": len(tx_ids), "transaction_ids": tx_ids,
                    "confirm_text": confirm_text or "",
                }, ensure_ascii=False)
                now = now_cn()
                audit = LedgerAuditRepository(conn)
                audit.authorize_batch(batch_id, batch["cycle_id"], confirmed_facts, detail, now)
                cash_deleted = CashLedgerRepository(conn).delete_by_batch(batch_id)
                tx_deleted = TransactionRepository(conn).delete_by_batch(batch_id)
                items_deleted = OrderItemRepository(conn).delete_by_batch(batch_id)
                batches.delete(batch_id)
                entry = audit.record("DELETE_BATCH", "batch", batch_id, detail, now)
            return {
                "deleted": True, "batch_id": batch_id,
                "order_items_deleted": items_deleted, "transactions_deleted": tx_deleted,
                "cash_events_deleted": cash_deleted, "confirmed_items": len(confirmed),
                "confirmed_transactions": len(confirmed_tx), "confirmed_facts": confirmed_facts,
                "audit": entry,
            }
        finally:
            conn.close()

    # --------------------------------------------- 四生命周期计划（D2）
    def _build_plan(self, conn, payload: dict) -> dict:
        """透明计划：权重版本/日期、行情来源/时间、目标金额、建议数量、偏差、算法版本。"""
        kind = _choice(payload.get("kind"), "kind", BATCH_KINDS)
        cycle_id = _int_value(payload.get("cycle_id"), "cycle_id", minimum=1)
        if not CycleRepository(conn).exists(cycle_id):
            raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
        algorithm_version = (_text(payload.get("algorithm_version"), "algorithm_version",
                                   maxlen=40) or PLAN_ALGORITHM_VERSION)
        weight_version = _text(payload.get("weight_version"), "weight_version", maxlen=80)
        weight_date = _text(payload.get("weight_date"), "weight_date", maxlen=40)
        quote_source = _text(payload.get("quote_source"), "quote_source", maxlen=80)
        quote_fetched_at = _time_value(payload.get("quote_fetched_at"), "quote_fetched_at", now_cn())
        capital_cents = _int_value(payload.get("capital_cents"), "capital_cents",
                                   minimum=0, required=False) or 0
        lot = _int_value(payload.get("lot_size"), "lot_size", minimum=1, required=False) or LOT_SIZE
        if lot % LOT_SIZE:
            raise LedgerError("lot_size 必须是 %d 的整数倍" % LOT_SIZE)
        weights, weight_sum = _normalize_weights(payload.get("weights"))
        quotes = _normalize_quotes(payload.get("quotes"))

        held_rows = TransactionRepository(conn).holdings(cycle_id, include_zero=False)
        holding_qty = {r["code"]: int(r["qty"] or 0) for r in held_rows
                       if int(r["qty"] or 0) != 0}
        cash_balance = CashLedgerRepository(conn).balance_cents(cycle_id)

        constituent_codes = [w["code"] for w in weights]
        constituent_set = set(constituent_codes)
        stale_constituents = sorted(c for c in holding_qty if c not in constituent_set)

        universe = list(constituent_codes)
        for code in sorted(holding_qty):
            if code not in universe:
                universe.append(code)
        missing = [c for c in universe if c not in quotes]
        if missing:
            raise LedgerError(
                "缺少行情（不补造数，先补行情再生成计划）：%s" % ",".join(missing), status=400)
        price = {c: quotes[c]["price_cents"] for c in universe}
        holdings_mv = sum(holding_qty[c] * price[c] for c in holding_qty)
        current_value = {c: holding_qty.get(c, 0) * price[c] for c in universe}

        if kind == "EXIT":
            portfolio_total, investable = 0, 0
        elif kind == "INITIAL":
            portfolio_total = investable = capital_cents
        else:  # ADD / REBALANCE：持仓市值 + 策略现金 + 新增资金
            portfolio_total = holdings_mv + cash_balance + capital_cents
            investable = max(0, cash_balance + capital_cents)
        if portfolio_total < 0:
            portfolio_total = 0

        alloc = _allocate_by_weight(portfolio_total, weights)
        target_value = {w["code"]: alloc[i] for i, w in enumerate(weights)}
        for c in universe:
            target_value.setdefault(c, 0)

        name_map = {w["code"]: w["name"] for w in weights}
        market_map = {w["code"]: w["market"] for w in weights}
        weight_map = {w["code"]: w["weight"] for w in weights}
        for r in held_rows:
            name_map.setdefault(r["code"], r["name"] or r["code"])

        if kind in ("INITIAL", "ADD"):
            rows = self._buy_only_rows(universe, target_value, current_value, holding_qty, price,
                                       investable, lot, name_map, market_map, weight_map,
                                       constituent_set)
        elif kind == "REBALANCE":
            rows = self._rebalance_rows(universe, target_value, current_value, holding_qty, price,
                                        lot, name_map, market_map, weight_map, constituent_set)
        else:
            rows = self._exit_rows(sorted(holding_qty), holding_qty, price,
                                   name_map, market_map, weight_map)

        # 非当前成分（STALE_CONSTITUENT）：持仓中有不在当前成分 universe 的 code 时，
        # 该行加标记与原因；ADD/REBALANCE 不向其分配新 BUY（缺口只向在成分内低配分配），
        # EXIT 照常全仓 SELL；summary/holdings 保留显示。
        for r in rows:
            in_index = r["code"] in constituent_set
            r["constituent_status"] = "IN_INDEX" if in_index else "STALE_CONSTITUENT"
            r["stale_constituent"] = not in_index
            if in_index:
                r["constituent_reason"] = ""
                continue
            r["constituent_reason"] = (
                "非当前成分（不在当前指数权重 universe）：不分配新 BUY，缺口只向在成分内低配分配"
                + ("；EXIT 照常全仓 SELL" if kind == "EXIT" else ""))
            if r["side"] == "BUY":
                r["note"] = "非当前成分（STALE_CONSTITUENT）：不分配新 BUY；缺口只向在成分内低配分配"
            elif r["note"]:
                r["note"] = r["note"] + "；非当前成分（STALE_CONSTITUENT）"
            else:
                r["note"] = "非当前成分（STALE_CONSTITUENT）"

        target_total = sum(int(r["target_amount_cents"]) for r in rows)
        actual_total = sum(int(r["actual_amount_cents"]) for r in rows)
        plan = {
            "algorithm_version": algorithm_version,
            "kind": kind,
            "cycle_id": cycle_id,
            "generated_at": now_cn(),
            "weight_version": weight_version,
            "weight_date": weight_date,
            "quote_source": quote_source,
            "quote_fetched_at": quote_fetched_at,
            "lot_size": lot,
            "inputs": {"capital_cents": int(capital_cents), "weight_sum": round(weight_sum, 6),
                       "weight_count": len(weights)},
            "universe": {"constituents": len(constituent_codes), "holdings": len(holding_qty),
                         "stale_constituents": stale_constituents},
            "stale_constituents": stale_constituents,
            "totals": {
                "portfolio_total_cents": int(portfolio_total),
                "holding_value_cents": int(holdings_mv),
                "cash_balance_cents": int(cash_balance),
                "investable_cents": int(investable),
                "target_total_cents": int(target_total),
                "actual_total_cents": int(actual_total),
                "deviation_total_cents": int(actual_total - target_total),
                "leftover_cents": int(investable - actual_total),
            },
            "rows": rows,
            "warnings": [],
        }
        _assert_plan_invariants(plan)
        self._collect_warnings(plan, kind, weight_sum, investable)
        return plan

    def _collect_warnings(self, plan: dict, kind: str, weight_sum: float,
                          investable: int) -> None:
        warnings = plan["warnings"]
        if abs(weight_sum - 100.0) > 0.5:
            warnings.append("权重和=%.4f 非 100，已按权重和归一化分配目标" % weight_sum)
        if kind == "ADD":
            if any(r["side"] == "BUY" and int(r["suggested_qty"]) == 0
                   and int(r["target_value_cents"]) > int(r["current_value_cents"])
                   for r in plan["rows"]):
                warnings.append("部分低配受可投资金/整手限制未能买入（默认不卖超配）")
        if kind == "REBALANCE":
            buys = sum(int(r["actual_amount_cents"]) for r in plan["rows"] if r["side"] == "BUY")
            sells = -sum(int(r["actual_amount_cents"]) for r in plan["rows"] if r["side"] == "SELL")
            if buys > sells + max(0, plan["totals"]["cash_balance_cents"]):
                warnings.append("再平衡买入额超过卖出额+可用现金，执行前须人工确认资金")
        if kind == "EXIT":
            warnings.append("清仓计划仅生成逐笔 SELL，须人工逐笔确认成交后才写 transactions")
        stale = plan.get("stale_constituents") or []
        if stale:
            warnings.append("存在 %d 只非当前成分持仓（STALE_CONSTITUENT）：%s；不向其分配新 BUY，"
                            "持仓保留显示，EXIT 照常全仓 SELL" % (len(stale), ",".join(stale)))

    def _buy_only_rows(self, universe, target_value, current_value, holding_qty, price,
                       investable, lot, name_map, market_map, weight_map,
                       constituent_set) -> list[dict]:
        # 非当前成分不参与新 BUY 缺口分配（缺口只向在成分内低配分配）。
        gaps = {c: (int(target_value.get(c, 0)) - int(current_value.get(c, 0))
                    if c in constituent_set else 0) for c in universe}
        remaining = max(0, int(investable))
        allocated: dict[str, tuple[int, int]] = {}
        for c in sorted(universe, key=lambda x: gaps[x], reverse=True):
            if gaps[c] <= 0:
                continue
            lot_value = price[c] * lot
            lots = min(gaps[c] // lot_value, remaining // lot_value)
            qty = lots * lot
            spend = qty * price[c]
            allocated[c] = (qty, spend)
            remaining -= spend
        rows = []
        for c in universe:
            gap = gaps[c]
            cur = int(current_value.get(c, 0))
            if gap > 0:
                qty, spend = allocated.get(c, (0, 0))
                note = "" if qty > 0 else "低配但可投资金/整手不足，未买入"
                target_amount, actual_amount = gap, spend
            else:
                qty, spend = 0, 0
                note = "超配或无缺口：默认不卖，0 股"
                target_amount, actual_amount = 0, 0
            rows.append(self._row(c, "BUY", name_map, market_map, weight_map, price,
                                  holding_qty, target_value, cur, target_amount, actual_amount,
                                  qty, note))
        return rows

    def _rebalance_rows(self, universe, target_value, current_value, holding_qty, price, lot,
                        name_map, market_map, weight_map, constituent_set) -> list[dict]:
        rows = []
        for c in universe:
            gap = int(target_value.get(c, 0)) - int(current_value.get(c, 0))
            p = price[c]
            lot_value = p * lot
            cur = int(current_value.get(c, 0))
            if gap > 0:
                if c not in constituent_set:
                    continue  # 非当前成分不分配新 BUY
                qty = (gap // lot_value) * lot
                if qty <= 0:
                    continue
                rows.append(self._row(c, "BUY", name_map, market_map, weight_map, price,
                                      holding_qty, target_value, cur, gap, qty * p, qty,
                                      "再平衡：仅生成 BUY 计划，不自动执行"))
            elif gap < 0:
                held = holding_qty.get(c, 0)
                qty = min(((-gap) // lot_value) * lot, held)
                if qty <= 0:
                    continue
                rows.append(self._row(c, "SELL", name_map, market_map, weight_map, price,
                                      holding_qty, target_value, cur, gap, -(qty * p), qty,
                                      "再平衡：仅生成 SELL 计划，须人工确认"))
        return rows

    def _exit_rows(self, codes, holding_qty, price, name_map, market_map,
                   weight_map) -> list[dict]:
        rows = []
        for c in codes:
            qty = holding_qty.get(c, 0)
            if qty <= 0:
                continue
            cur = qty * price[c]
            rows.append(self._row(c, "SELL", name_map, market_map, weight_map, price, holding_qty,
                                  0, cur, -cur, -cur, qty,
                                  "清仓退出：逐笔 SELL 计划，须人工确认成交后才写 transactions"))
        return rows

    @staticmethod
    def _row(code, side, name_map, market_map, weight_map, price, holding_qty, target_value,
             current_value, target_amount, actual_amount, qty, note) -> dict:
        return {
            "code": code,
            "name": name_map.get(code, code),
            "market": market_map.get(code, ""),
            "side": side,
            "target_weight": weight_map.get(code),
            "reference_price_cents": price[code],
            "holding_qty": int(holding_qty.get(code, 0)),
            "current_value_cents": int(current_value),
            "target_value_cents": int(target_value.get(code, 0) if isinstance(target_value, dict)
                                      else target_value),
            "target_amount_cents": int(target_amount),
            "actual_amount_cents": int(actual_amount),
            "deviation_cents": int(actual_amount) - int(target_amount),
            "suggested_qty": int(qty),
            "note": note,
        }

    def _insert_plan_items(self, conn, batch_id: int, plan: dict, revision: int) -> list[dict]:
        repo = OrderItemRepository(conn)
        now = now_cn()
        return [repo.create(batch_id, r["code"], r["name"], r["market"], r["side"],
                            r["target_weight"], r["reference_price_cents"], r["suggested_qty"],
                            revision, r["note"], now) for r in plan["rows"]]

    def preview_batch(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise LedgerError("请求体必须是 JSON 对象")
        conn = self._open()
        try:
            plan = self._build_plan(conn, payload)
        finally:
            conn.close()
        return {"plan": plan}

    def freeze_batch(self, payload: dict) -> dict:
        cycle_id = _int_value(payload.get("cycle_id"), "cycle_id", minimum=1)
        note = _text(payload.get("note"), "note", maxlen=1000)
        conn = self._open()
        try:
            with write_tx(conn):
                cycle = CycleRepository(conn).get(cycle_id)
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能冻结新计划", status=409)
                plan = self._build_plan(conn, payload)
                batches = BatchRepository(conn)
                batch = batches.create(cycle_id, plan["kind"], note, plan["algorithm_version"],
                                       1, now_cn(), status="FROZEN")
                batch = batches.freeze(batch["batch_id"], 1, plan["algorithm_version"],
                                       json.dumps(plan, ensure_ascii=False), now_cn())
                items = self._insert_plan_items(conn, batch["batch_id"], plan, 1)
            return {"batch": batch, "order_items": items, "plan": plan, "revision": 1,
                    "frozen": True}
        finally:
            conn.close()

    def revise_batch(self, batch_id, payload: dict) -> dict:
        batch_id = _int_value(batch_id, "batch_id", minimum=1)
        payload = dict(payload or {})
        conn = self._open()
        try:
            with write_tx(conn):
                batches = BatchRepository(conn)
                batch = batches.get(batch_id)
                if batch is None:
                    raise LedgerError("batch 不存在：%s" % batch_id, status=404)
                cycle = CycleRepository(conn).get(batch["cycle_id"])
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % batch["cycle_id"], status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能重算计划", status=409)
                req_cycle = payload.get("cycle_id")
                if req_cycle is not None and \
                        _int_value(req_cycle, "cycle_id", minimum=1) != int(batch["cycle_id"]):
                    raise LedgerError("revise 不允许改写 cycle_id（原批次 cycle_id=%s）"
                                      % batch["cycle_id"], status=400)
                req_kind = payload.get("kind")
                if req_kind is not None and _choice(req_kind, "kind", BATCH_KINDS) != batch["kind"]:
                    raise LedgerError("revise 不允许改写 kind（原批次 kind=%s）" % batch["kind"],
                                      status=400)
                payload["cycle_id"] = batch["cycle_id"]
                payload["kind"] = batch["kind"]
                plan = self._build_plan(conn, payload)
                new_revision = int(batch["revision"]) + 1
                batch = batches.freeze(batch_id, new_revision, plan["algorithm_version"],
                                       json.dumps(plan, ensure_ascii=False), now_cn())
                items = self._insert_plan_items(conn, batch_id, plan, new_revision)
                all_items = OrderItemRepository(conn).list(batch_id)
            preserved = [i for i in all_items if i["status"] == "CONFIRMED"]
            return {"batch": batch, "order_items": items, "plan": plan, "revision": new_revision,
                    "preserved_confirmed_items": preserved}
        finally:
            conn.close()

    def cycle_summary(self, cycle_id) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1)
        conn = self._open()
        try:
            cycle = CycleRepository(conn).get(cycle_id)
            if cycle is None:
                raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
            txs = TransactionRepository(conn)
            holdings = txs.holdings(cycle_id, include_zero=False)
            for row in holdings:
                qty = int(row["qty"] or 0)
                net = int(row["net_cost_cents"] or 0)
                row["avg_cost_cents"] = int(round(net / qty)) if qty else None
            cash_repo = CashLedgerRepository(conn)
            return {
                "cycle": cycle,
                "holdings": holdings,
                "cash_balance_cents": cash_repo.balance_cents(cycle_id),
                "cash_event_count": len(cash_repo.list(cycle_id)),
                "batch_count": len(BatchRepository(conn).list(cycle_id)),
                "transaction_count": len(txs.list(cycle_id)),
                "holdings_rebuild_source": "v_holdings(confirmed transactions)",
            }
        finally:
            conn.close()

    def close_cycle(self, cycle_id, payload: dict | None = None) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1)
        conn = self._open()
        try:
            with write_tx(conn):
                cycles = CycleRepository(conn)
                cycle = cycles.get(cycle_id)
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
                if cycle["status"] == "CLOSED":
                    raise LedgerError("cycle 已关闭：%s" % cycle_id, status=409)
                holdings = TransactionRepository(conn).holdings(cycle_id, include_zero=False)
                nonzero = [h for h in holdings if int(h["qty"] or 0) != 0]
                if nonzero:
                    raise LedgerError(
                        "仍有未清仓持仓，拒绝关闭：%s" % ",".join(h["code"] for h in nonzero),
                        status=409)
                cycle = cycles.close(cycle_id, now_cn())
                balance = CashLedgerRepository(conn).balance_cents(cycle_id)
            return {"cycle": cycle, "holdings": [], "cash_balance_cents": balance}
        finally:
            conn.close()

    # ------------------------------------------------------ transactions
    def list_transactions(self, cycle_id=None, code=None, confirmed=None) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1, required=False)
        code = _code(code) if code else None
        conn = self._open()
        try:
            return {"transactions": TransactionRepository(conn).list(cycle_id, code, confirmed)}
        finally:
            conn.close()

    def record_transaction(self, payload: dict) -> dict:
        cycle_id = _int_value(payload.get("cycle_id"), "cycle_id", minimum=1)
        batch_id = _int_value(payload.get("batch_id"), "batch_id", minimum=1, required=False)
        order_item_id = _int_value(payload.get("order_item_id"), "order_item_id",
                                   minimum=1, required=False)
        code = _code(payload.get("code"))
        name = _text(payload.get("name"), "name", maxlen=40)
        side = _choice(payload.get("side"), "side", SIDES)
        qty = _int_value(payload.get("qty"), "qty", minimum=1)
        if qty % LOT_SIZE:
            raise LedgerError("qty 必须为 %d 股整手（%d 的整数倍）" % (LOT_SIZE, LOT_SIZE))
        if payload.get("confirmed") is not True:
            raise LedgerError(
                "只有用户人工核实“已成交/已卖出成交”才可写入账本（confirmed 必须为 true）；"
                "已下单/已报单/部分成交/撤单首版拒绝")
        price_cents = _int_value(payload.get("price_cents"), "price_cents",
                                 minimum=1, required=False)
        reference_price_cents = _int_value(payload.get("reference_price_cents"),
                                           "reference_price_cents", minimum=1, required=False)
        amount_cents = _int_value(payload.get("amount_cents"), "amount_cents",
                                  minimum=1, required=False)
        if price_cents is not None:
            computed = price_cents * qty
            if amount_cents is not None and amount_cents != computed:
                raise LedgerError("amount_cents 与 price_cents × qty 不一致")
            amount_cents = computed
        if amount_cents is None:
            raise LedgerError("成交价可选，但 price_cents 与 amount_cents 至少要有一个")
        source = _text(payload.get("source"), "source", maxlen=40) or "MANUAL_CONFIRM"
        note = _text(payload.get("note"), "note", maxlen=500)
        idem = _text(payload.get("idempotency_key"), "idempotency_key", maxlen=120) or None
        confirmed_at = _time_value(payload.get("confirmed_at"), "confirmed_at", now_cn())
        record_cash = payload.get("record_cash", True) is not False
        if not isinstance(payload.get("record_cash", True), bool):
            raise LedgerError("字段 record_cash 必须是布尔值")

        conn = self._open()
        try:
            with write_tx(conn):
                cycles = CycleRepository(conn)
                batches = BatchRepository(conn)
                items = OrderItemRepository(conn)
                txs = TransactionRepository(conn)
                cash = CashLedgerRepository(conn)

                cycle = cycles.get(cycle_id)
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能写入交易", status=409)
                if batch_id is not None:
                    batch = batches.get(batch_id)
                    if batch is None or batch["cycle_id"] != cycle_id:
                        raise LedgerError("batch 不属于该 cycle：%s" % batch_id, status=404)
                item = None
                if order_item_id is not None:
                    item = items.get(order_item_id)
                    if item is None:
                        raise LedgerError("order_item 不存在：%s" % order_item_id, status=404)
                    if batch_id is None:
                        batch_id = item["batch_id"]
                    if item["batch_id"] != batch_id:
                        raise LedgerError("order_item 不属于该 batch：%s" % order_item_id)
                if idem is not None:
                    existing = txs.find_by_idempotency_key(idem)
                    if existing is not None:
                        return {"transaction": existing, "idempotent_replay": True,
                                "balance_cents": cash.balance_cents(existing["cycle_id"])}
                if item is not None and item["status"] == "CONFIRMED":
                    raise LedgerError("该下单行已确认成交，禁止重复确认（order_item_id=%s）"
                                      % order_item_id, status=409)
                if side == "SELL":
                    held = txs.holding_qty(cycle_id, code)
                    if qty > held:
                        raise LedgerError("卖出数量 %d 超过已确认持仓 %d（禁止裸空）" % (qty, held),
                                          status=409)
                tx = txs.create(cycle_id=cycle_id, batch_id=batch_id, order_item_id=order_item_id,
                                code=code, name=name, side=side, qty=qty,
                                price_cents=price_cents,
                                reference_price_cents=reference_price_cents,
                                amount_cents=amount_cents, confirmed_at=confirmed_at,
                                source=source, note=note, idempotency_key=idem, now=now_cn())
                if order_item_id is not None and item.get("status") != "CONFIRMED":
                    items.set_status(order_item_id, "CONFIRMED", now_cn())
                cash_event = None
                if record_cash:
                    cash_event = cash.append(
                        cycle_id=cycle_id, transaction_id=tx["transaction_id"], event_type=side,
                        amount_cents=(-amount_cents if side == "BUY" else amount_cents),
                        note="auto:transaction:%s" % tx["transaction_id"],
                        occurred_at=confirmed_at, idempotency_key="tx:%s" % tx["transaction_id"],
                        now=now_cn())
                return {"transaction": tx, "cash_event": cash_event,
                        "balance_cents": cash.balance_cents(cycle_id)}
        finally:
            conn.close()

    # ---------------------------------------------------------- holdings
    def holdings(self, cycle_id=None, include_zero: bool = False) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1, required=False)
        conn = self._open()
        try:
            rows = TransactionRepository(conn).holdings(cycle_id, include_zero)
            for row in rows:
                qty = int(row["qty"] or 0)
                net = int(row["net_cost_cents"] or 0)
                row["avg_cost_cents"] = int(round(net / qty)) if qty else None
            return {"holdings": rows, "rebuild_source": "v_holdings(confirmed transactions)"}
        finally:
            conn.close()

    # -------------------------------------------------------------- cash
    def list_cash(self, cycle_id=None) -> dict:
        cycle_id = _int_value(cycle_id, "cycle_id", minimum=1, required=False)
        conn = self._open()
        try:
            repo = CashLedgerRepository(conn)
            events = repo.list(cycle_id)
            if cycle_id is None:
                balances = {r["cycle_id"]: r["balance_cents"] for r in conn.execute(
                    "SELECT cycle_id, balance_cents FROM v_cash_balance")}
                balance = None
            else:
                balances = None
                balance = repo.balance_cents(cycle_id)
            return {"cash_events": events, "balance_cents": balance, "balances": balances}
        finally:
            conn.close()

    def append_cash(self, payload: dict) -> dict:
        cycle_id = _int_value(payload.get("cycle_id"), "cycle_id", minimum=1)
        event_type = _choice(payload.get("event_type"), "event_type", CASH_EVENT_TYPES)
        amount_cents = _int_value(payload.get("amount_cents"), "amount_cents")
        if amount_cents == 0:
            raise LedgerError("amount_cents 不能为 0")
        if event_type in POSITIVE_ONLY and amount_cents < 0:
            raise LedgerError("%s 的 amount_cents 必须为正（资金流入）" % event_type)
        if event_type in NEGATIVE_ONLY and amount_cents > 0:
            raise LedgerError("%s 的 amount_cents 必须为负（资金流出）" % event_type)
        transaction_id = _int_value(payload.get("transaction_id"), "transaction_id",
                                    minimum=1, required=False)
        note = _text(payload.get("note"), "note", maxlen=500)
        occurred_at = _time_value(payload.get("occurred_at"), "occurred_at", now_cn())
        idem = _text(payload.get("idempotency_key"), "idempotency_key", maxlen=120) or None

        conn = self._open()
        try:
            with write_tx(conn):
                cycle = CycleRepository(conn).get(cycle_id)
                if cycle is None:
                    raise LedgerError("cycle 不存在：%s" % cycle_id, status=404)
                if cycle["status"] != "OPEN":
                    raise LedgerError("cycle 已关闭（CLOSED），不能追加现金事件", status=409)
                repo = CashLedgerRepository(conn)
                if idem is not None:
                    existing = repo.find_by_idempotency_key(idem)
                    if existing is not None:
                        return {"cash_event": existing, "idempotent_replay": True,
                                "balance_cents": repo.balance_cents(existing["cycle_id"])}
                if transaction_id is not None:
                    tx = TransactionRepository(conn).get(transaction_id)
                    if tx is None or tx["cycle_id"] != cycle_id:
                        raise LedgerError("transaction 不属于该 cycle：%s" % transaction_id,
                                          status=404)
                event = repo.append(cycle_id=cycle_id, transaction_id=transaction_id,
                                    event_type=event_type, amount_cents=amount_cents, note=note,
                                    occurred_at=occurred_at, idempotency_key=idem, now=now_cn())
                return {"cash_event": event, "balance_cents": repo.balance_cents(cycle_id)}
        finally:
            conn.close()
