#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1 账本 JSON API 路由（全部挂在 /api/ledger/* 下）。

命名说明（重要）：V1.2 既有 `/api/holdings?code=<指数代码>` 表示“指数权重解析缓存”，
语义不可改变；因此 V1.3 账本持仓使用 `/api/ledger/holdings`，两者互不影响。

只读能力：
    GET /api/ledger/status[?check=1]      迁移版本、PRAGMA、表行数、可选 integrity/fk 检查
    GET /api/ledger/cycles
    GET /api/ledger/cycles/:id/summary    持仓重建 + 现金余额 + 批次/交易计数（D2）
    GET /api/ledger/batches?cycle_id=
    GET /api/ledger/batches/:id/progress  四态计数 + 完成门禁 progressing/blocked/done（D3）
    GET /api/ledger/order-items?batch_id=&revision=&latest=1
    GET /api/ledger/transactions?cycle_id=&code=&confirmed=
    GET /api/ledger/holdings?cycle_id=&include_zero=
    GET /api/ledger/cash?cycle_id=
写能力（人工核实后写入；一次一写事务）：
    POST /api/ledger/cycles
    POST /api/ledger/cycles/:id/close     清仓归零后 OPEN → CLOSED（D2）
    POST /api/ledger/batches
    POST /api/ledger/batches/preview      四种生命周期透明预览（不落库）（D2）
    POST /api/ledger/batches/freeze       冻结快照落 order_items + revision=1（D2）
    POST /api/ledger/batches/:id/revise   重算只增 revision，已确认项不改写（D2）
    POST /api/ledger/batches/:id/delete   删除测试批次（整批；含 CONFIRMED 需 confirm_text）（D7）
    POST /api/ledger/order-items
    POST /api/ledger/order-items/:id/state  四态流转 PENDING↔SKIPPED/REVIEW；CONFIRMED 不可逆（D3）
    POST /api/ledger/order-items/:id/revert  撤销已确认成交（回 PENDING，需 confirm_text；D8）
    POST /api/ledger/transactions     （必须 confirmed=true；联动 order_item → CONFIRMED）
    POST /api/ledger/cash
"""
from __future__ import annotations

import sqlite3
from urllib.parse import unquote

from .connection import LedgerError
from .service import LedgerService

PREFIX = "/api/ledger"
_SERVICE = LedgerService()

ROUTES = {
    "GET": ["/api/ledger/status", "/api/ledger/cycles", "/api/ledger/cycles/<id>/summary",
            "/api/ledger/batches", "/api/ledger/batches/<id>/progress",
            "/api/ledger/order-items",
            "/api/ledger/transactions", "/api/ledger/holdings", "/api/ledger/cash"],
    "POST": ["/api/ledger/cycles", "/api/ledger/cycles/<id>/close",
             "/api/ledger/batches", "/api/ledger/batches/preview",
             "/api/ledger/batches/freeze", "/api/ledger/batches/<id>/revise",
             "/api/ledger/batches/<id>/delete",
             "/api/ledger/order-items", "/api/ledger/order-items/<id>/state",
             "/api/ledger/order-items/<id>/revert",
             "/api/ledger/transactions", "/api/ledger/cash"],
}


def handles(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/") or path.startswith(PREFIX + "?")


def _segments(path: str) -> list[str]:
    rest = path[len(PREFIX):]
    return [seg for seg in unquote(rest).strip("/").split("/") if seg]


def _truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


def route(method: str, path: str, query: dict | None = None, body: dict | None = None):
    """返回 (http_status, obj)。所有异常在此收敛为 JSON，不向 HTTP 层抛出。"""
    query = dict(query or {})
    try:
        seg = _segments(path)
        if method == "GET":
            return _get(seg, query)
        if method == "POST":
            return _post(seg, body)
        return 405, {"ok": False, "error": "method not allowed", "allowed": list(ROUTES)}
    except LedgerError as exc:
        return exc.status, {"ok": False, "error": exc.message}
    except sqlite3.IntegrityError as exc:
        return 409, {"ok": False, "error": "数据库约束冲突：%s" % exc}
    except sqlite3.OperationalError as exc:
        return 503, {"ok": False, "error": "数据库错误：%s" % exc}
    except Exception as exc:  # 兜底：保持 JSON 契约，便于排障
        return 500, {"ok": False, "error": "ledger internal error: %s" % exc}


def _get(seg: list[str], query: dict):
    if seg in ([], ["status"]):
        return 200, {"ok": True, **_SERVICE.status(deep=_truthy(query.get("check"))),
                     "routes": ROUTES}
    if seg == ["routes"]:
        return 200, {"ok": True, "routes": ROUTES}
    if seg == ["cycles"]:
        return 200, {"ok": True, **_SERVICE.list_cycles()}
    if len(seg) == 3 and seg[0] == "cycles" and seg[2] == "summary":
        return 200, {"ok": True, **_SERVICE.cycle_summary(seg[1])}
    if seg == ["batches"]:
        return 200, {"ok": True, **_SERVICE.list_batches(query.get("cycle_id"))}
    if len(seg) == 3 and seg[0] == "batches" and seg[2] == "progress":
        return 200, {"ok": True, **_SERVICE.batch_progress(seg[1])}
    if seg == ["order-items"]:
        return 200, {"ok": True, **_SERVICE.list_order_items(
            query.get("batch_id"), query.get("revision"), _truthy(query.get("latest")))}
    if seg == ["transactions"]:
        confirmed = None
        if query.get("confirmed") is not None:
            confirmed = _truthy(query.get("confirmed"))
        return 200, {"ok": True, **_SERVICE.list_transactions(
            query.get("cycle_id"), query.get("code"), confirmed)}
    if seg == ["holdings"]:
        return 200, {"ok": True, **_SERVICE.holdings(query.get("cycle_id"),
                                                     _truthy(query.get("include_zero")))}
    if seg == ["cash"]:
        return 200, {"ok": True, **_SERVICE.list_cash(query.get("cycle_id"))}
    return 404, {"ok": False, "error": "unknown ledger endpoint", "routes": ROUTES}


def _post(seg: list[str], body):
    if not isinstance(body, dict):
        raise LedgerError("请求体必须是 JSON 对象")
    if seg == ["cycles"]:
        return 201, {"ok": True, **_SERVICE.create_cycle(body)}
    if len(seg) == 3 and seg[0] == "cycles" and seg[2] == "close":
        return 200, {"ok": True, **_SERVICE.close_cycle(seg[1], body)}
    if seg == ["batches"]:
        return 201, {"ok": True, **_SERVICE.create_batch(body)}
    if seg == ["batches", "preview"]:
        return 200, {"ok": True, **_SERVICE.preview_batch(body)}
    if seg == ["batches", "freeze"]:
        return 201, {"ok": True, **_SERVICE.freeze_batch(body)}
    if len(seg) == 3 and seg[0] == "batches" and seg[2] == "revise":
        return 200, {"ok": True, **_SERVICE.revise_batch(seg[1], body)}
    if len(seg) == 3 and seg[0] == "batches" and seg[2] == "delete":
        return 200, {"ok": True, **_SERVICE.delete_batch(seg[1], body)}
    if seg == ["order-items"]:
        return 201, {"ok": True, **_SERVICE.create_order_item(body)}
    if len(seg) == 3 and seg[0] == "order-items" and seg[2] == "state":
        return 200, {"ok": True, **_SERVICE.set_order_item_state(seg[1], body)}
    if len(seg) == 3 and seg[0] == "order-items" and seg[2] == "revert":
        return 200, {"ok": True, **_SERVICE.revert_confirmation(seg[1], body)}
    if seg == ["transactions"]:
        status = 200 if body.get("idempotency_key") else 201
        return status, {"ok": True, **_SERVICE.record_transaction(body)}
    if seg == ["cash"]:
        status = 200 if body.get("idempotency_key") else 201
        return status, {"ok": True, **_SERVICE.append_cash(body)}
    return 404, {"ok": False, "error": "unknown ledger endpoint", "routes": ROUTES}
