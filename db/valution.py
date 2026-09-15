# -*- coding: utf-8 -*-
"""D4 估值回撤：同指数收盘序列「双源核验」框架（Python 标准库，无第三方依赖）。

规则（PRODUCT_PLAN_V1.0 P0#3，严格照抄，不放松）：
- sourceA / sourceB 必须分别声明同一 ``indexCode`` / ``indexName``、价格指数口径
  （``kind="price"``，非全收益/净收益）、``instrument="index"``（非 ETF/个股）、
  同一 ``currency``、`field="close"`（非盘中 high）。
- 身份校验通过后按交易日 inner join；只有两个来源都出现的交易日期进入计算。
- 并集缺失率 =（并集交易日 - inner join 交易日）/ 并集交易日，超过 0.5% 判定失败。
- 任一来源候选最高 20 个收盘日中，只要有日期不在 inner join 里，判定失败。
- 全部 joined 日期须满足 ``|a-b| / max(|a|,|b|) <= 0.10%``，否则判定失败。
- 任一项不通过：回撤为 NA（``None``），保留可读原因；绝不静默取较高值或补造数。

当前项目未取得任何授权且同口径的历史收盘序列，故 :func:`drawdown_board` 对
三宽基 + 六红利共九指数统一返回 NA + 原因（诚实展示，不是占位假数）。
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------- 阈值（锁死）
MISSING_RATE_LIMIT = 0.005      # 并集缺失率上限 0.5%
REL_TOLERANCE = 0.001           # 相对误差上限 0.10%
TOP_N = 20                      # 候选最高收盘日抽样个数
RANDOM_SAMPLE_SIZE = 20         # 计划要求：另抽查随机 20 个交易日
SAMPLE_SEED = 20260915          # 确定性种子（同输入必得同抽样，可审计）
PRICE_KINDS = {"price"}         # 只接受价格指数口径
INDEX_INSTRUMENTS = {"index"}   # 只接受指数本身
CLOSE_FIELDS = {"close"}        # 只接受收盘价字段

STATUS_OK = "OK"
STATUS_NA = "NA"

NA_DISPLAY = "暂无数据"

#: 九指数（三宽基 + 六红利），顺序与 PRODUCT_PLAN_V1.0 一致。
DRAWDOWN_INDICES: tuple[tuple[str, str], ...] = (
    ("000300", "沪深300"),
    ("000905", "中证500"),
    ("000852", "中证1000"),
    ("H30269", "红利低波"),
    ("930740", "300红利低波"),
    ("930955", "红利低波100"),
    ("SPCLLHCP", "标普中国A股大盘红利低波50"),
    ("931468", "红利质量"),
    ("931446", "东证红利低波"),
)

NO_SERIES_REASON = "未取得授权且同口径（价格指数·收盘）的历史收盘序列，双源核验不可执行"


# ------------------------------------------------------------------ 基础工具
def _num(value):
    """转 float；非有限/<=0 视为无效（收盘价必须为正）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")) or f <= 0:
        return None
    return f


def _norm_date(value):
    """归一化交易日为 ``YYYY-MM-DD``；无法识别返回 None。"""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    s = str(value or "").strip()
    if not s:
        return None
    s = s[:10].replace("/", "-").replace(".", "-")
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_series(series) -> dict[str, float]:
    """把多种写法归一成 ``{交易日: 收盘}``（忽略无效行）。

    支持：``{date: close}``、``[[date, close], ...]``、``[{"date":..., "close":...}, ...]``。
    """
    out: dict[str, float] = {}
    if not series:
        return out
    if isinstance(series, dict):
        items = series.items()
    else:
        items = []
        for row in series:
            if isinstance(row, dict):
                items.append((row.get("date") or row.get("tradeDate") or row.get("day"),
                              row.get("close") if "close" in row else row.get("value")))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                items.append((row[0], row[1]))
    for raw_date, raw_close in items:
        d = _norm_date(raw_date)
        v = _num(raw_close)
        if d and v is not None:
            out[d] = v
    return out


def na_result(reason: str, code: str = "", errors=None) -> dict:
    """统一的 NA 结果（回撤失败时使用，字段齐全便于 UI / 测试断言）。"""
    errs = list(errors or [])
    if reason and reason not in errs:
        errs.insert(0, reason)
    return {
        "ok": False,
        "status": STATUS_NA,
        "code": code,
        "display": NA_DISPLAY,
        "reason": reason,
        "errors": errs,
        "currentClose": None,
        "currentCloseDate": None,
        "highestClose": None,
        "highestDate": None,
        "drawdown": None,
        "joinedDays": None,
        "unionDays": None,
        "missingRate": None,
        "maxRelError": None,
        "topGapDates": [],
        "sampled": 0,
        "sampledRandom": [],
    }


# ------------------------------------------------------------------ 身份校验
def _identity_problems(src, label: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(src, dict):
        return ["%s 不是有效来源对象" % label]
    if not str(src.get("indexCode") or "").strip():
        problems.append("%s 缺少 indexCode" % label)
    if not str(src.get("indexName") or "").strip():
        problems.append("%s 缺少 indexName" % label)
    if str(src.get("instrument") or "").strip().lower() not in INDEX_INSTRUMENTS:
        problems.append("%s instrument=%s 不是指数本身（拒绝 ETF/个股代理）"
                        % (label, src.get("instrument")))
    if str(src.get("kind") or "").strip().lower() not in PRICE_KINDS:
        problems.append("%s kind=%s 不是价格指数（拒绝全收益/净收益序列）"
                        % (label, src.get("kind")))
    if not str(src.get("currency") or "").strip():
        problems.append("%s 缺少币种" % label)
    if str(src.get("field") or "").strip().lower() not in CLOSE_FIELDS:
        problems.append("%s field=%s 不是收盘价（拒绝盘中 high 等字段）"
                        % (label, src.get("field")))
    if not normalize_series(src.get("series")):
        problems.append("%s 收盘序列为空或无法解析" % label)
    return problems


# ------------------------------------------------------------------ 核心算法
def verify_drawdown(source_a, source_b, *, sample_seed: int = SAMPLE_SEED) -> dict:
    """按 P0#3 规则对两路收盘序列做核验并计算回撤。

    通过返回 ``ok=True`` 与数值；任一规则不通过返回 :func:`na_result` 结构（NA + 原因）。
    算法只做核验与计算，不联网、不读库、不写任何状态。
    """
    problems = _identity_problems(source_a, "sourceA") + _identity_problems(source_b, "sourceB")
    code = str((source_a or {}).get("indexCode") or (source_b or {}).get("indexCode") or "")
    if problems:
        return na_result("；".join(problems), code, problems)

    if str(source_a.get("indexCode")).strip() != str(source_b.get("indexCode")).strip():
        return na_result("双源 indexCode 不一致（%s vs %s），拒绝静默取较高值"
                         % (source_a.get("indexCode"), source_b.get("indexCode")), code)
    if str(source_a.get("indexName")).strip() != str(source_b.get("indexName")).strip():
        return na_result("双源 indexName 不一致（%s vs %s）"
                         % (source_a.get("indexName"), source_b.get("indexName")), code)
    if str(source_a.get("currency")).strip().upper() != str(source_b.get("currency")).strip().upper():
        return na_result("双源币种不一致（%s vs %s）"
                         % (source_a.get("currency"), source_b.get("currency")), code)

    sa = normalize_series(source_a.get("series"))
    sb = normalize_series(source_b.get("series"))
    joined = sorted(set(sa) & set(sb))
    union = sorted(set(sa) | set(sb))
    if not joined:
        return na_result("双源无共同交易日（inner join 为空），回撤不可计算", code)

    missing_rate = (len(union) - len(joined)) / float(len(union))
    if missing_rate > MISSING_RATE_LIMIT:
        return na_result("并集缺失率 %.4f%% 超过 0.5%%（并集 %d 日 / 交集 %d 日）"
                         % (missing_rate * 100, len(union), len(joined)), code)

    top_a = sorted(sa.keys(), key=lambda d: (-sa[d], d))[:TOP_N]
    top_b = sorted(sb.keys(), key=lambda d: (-sb[d], d))[:TOP_N]
    joined_set = set(joined)
    top_gap = sorted({d for d in (top_a + top_b) if d not in joined_set})
    if top_gap:
        return na_result("候选最高 %d 个收盘日存在缺日：%s"
                         % (TOP_N, ",".join(top_gap[:5])), code)

    max_rel = 0.0
    worst = ""
    for d in joined:
        a, b = sa[d], sb[d]
        denom = max(abs(a), abs(b))
        rel = abs(a - b) / denom if denom else 1.0
        if rel > max_rel:
            max_rel, worst = rel, d
        if rel > REL_TOLERANCE:
            return na_result("相对误差 %.4f%% 超过 0.10%%（%s：%s vs %s）"
                             % (rel * 100, d, a, b), code)

    highest_date = sorted(joined, key=lambda d: (-sa[d], d))[0]
    current_date = joined[-1]
    current_close = sa[current_date]
    highest_close = sa[highest_date]
    drawdown = current_close / highest_close - 1.0

    # 抽样复核点：端点 + 最高点前后各 5 个交易日 + 确定性随机 20 个交易日（全部来自
    # joined，可审计；随机抽样用固定种子，同输入必得同结果，仅用于 sampled/审计计数，
    # 不改变 pass/fail 门）。
    idx = joined.index(highest_date)
    sample = set(joined[:1] + joined[-1:])
    for off in range(-5, 6):
        j = idx + off
        if 0 <= j < len(joined):
            sample.add(joined[j])
    rng = random.Random(sample_seed)
    random_sample = sorted(rng.sample(joined, min(RANDOM_SAMPLE_SIZE, len(joined))))
    sample.update(random_sample)

    return {
        "ok": True,
        "status": STATUS_OK,
        "code": code,
        "display": "%.2f%%" % (drawdown * 100),
        "reason": "",
        "errors": [],
        "currentClose": current_close,
        "currentCloseDate": current_date,
        "highestClose": highest_close,
        "highestDate": highest_date,
        "drawdown": drawdown,
        "joinedDays": len(joined),
        "unionDays": len(union),
        "missingRate": missing_rate,
        "maxRelError": max_rel,
        "topGapDates": [],
        "sampled": len(sample),
        "sampledRandom": random_sample,
        "sampleSeed": sample_seed,
        "worstDate": worst,
        "sourceA": {"indexCode": source_a.get("indexCode"), "indexName": source_a.get("indexName"),
                    "kind": source_a.get("kind"), "instrument": source_a.get("instrument"),
                    "currency": source_a.get("currency"), "field": source_a.get("field")},
        "sourceB": {"indexCode": source_b.get("indexCode"), "indexName": source_b.get("indexName"),
                    "kind": source_b.get("kind"), "instrument": source_b.get("instrument"),
                    "currency": source_b.get("currency"), "field": source_b.get("field")},
    }


def _load_approx_board() -> dict:
    """D8 近似回撤数据（用户 2026-09-16 拍板：回撤上近似，标来源＋交叉验证，不编造）。

    读 ``cache/valuation/drawdown.json``（scripts/fetch_drawdown.py 生成）：
    腾讯 fqkline bfq / 东方财富 push2his fqt=0（不复权收盘）近10年 MAX(close)，
    失败指数用参考站 2026-08-07 快照兜底（明确标注）。文件缺失/损坏 → 返回 {}。
    """
    try:
        doc = json.loads(
            (Path(__file__).resolve().parent.parent / "cache" / "valuation"
             / "drawdown.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for rec in doc.get("indices", []):
        if rec.get("status") == STATUS_OK and rec.get("drawdown") is not None:
            out[rec["code"]] = rec
    out["_meta"] = {"asOf": doc.get("asOf", ""), "fetchedAt": doc.get("fetchedAt", ""),
                    "method": doc.get("method", "")}
    return out


def drawdown_board(indices=None, sources=None) -> dict:
    """九指数回撤看板（只读）。

    - 提供 ``sources={indexCode: (sourceA, sourceB)}`` 时逐指数走
      :func:`verify_drawdown`，通过才给出数值，否则仍是 NA + 原因。
    - 否则读近似数据文件（D8，用户已拍板近似＋交叉验证）：有记录的指数展示
      数值并标注来源/日期/ETF代理/快照，缺失仍 NA + 原因，绝不编数。
    """
    indices = list(indices or DRAWDOWN_INDICES)
    sources = sources or {}
    approx = _load_approx_board()
    meta = approx.pop("_meta", {})
    rows = []
    for code, name in indices:
        pair = sources.get(code)
        if pair:
            res = verify_drawdown(pair[0], pair[1])
        elif code in approx:
            a = approx[code]
            prox = "（ETF 收盘代理，非指数本身）" if a.get("etfProxy") else ""
            stale = "（参考站 2026-08-07 快照，非实时）" if a.get("staleSnapshot") else ""
            res = {"status": STATUS_OK, "display": a.get("display", ""),
                   "reason": "近似数据：%s%s%s；asOf %s" % (
                       a.get("source", ""), prox, stale, meta.get("asOf", "")),
                   "currentClose": a.get("currentClose"),
                   "currentCloseDate": a.get("currentDate"),
                   "highestClose": a.get("highestClose"),
                   "highestDate": a.get("highestDate"),
                   "drawdown": a.get("drawdown"),
                   "joinedDays": a.get("tradingDays", 0),
                   "unionDays": a.get("tradingDays", 0)}
        else:
            res = na_result(NO_SERIES_REASON, code)
        rows.append({
            "code": code,
            "name": name,
            "status": res["status"],
            "display": res["display"],
            "reason": res["reason"],
            "currentClose": res["currentClose"],
            "currentCloseDate": res["currentCloseDate"],
            "highestClose": res["highestClose"],
            "highestDate": res["highestDate"],
            "drawdown": res["drawdown"],
            "joinedDays": res["joinedDays"],
            "unionDays": res["unionDays"],
        })
    verified = any(r["status"] == STATUS_OK for r in rows)
    approx_only = verified and all(
        r["status"] != STATUS_OK or "近似数据" in (r.get("reason") or "") for r in rows)
    return {
        "ok": True,
        "verified": verified,
        "approx": approx_only,
        "status": STATUS_OK if verified else STATUS_NA,
        "display": NA_DISPLAY if not verified else "",
        "asOf": meta.get("asOf", "") if verified else "",
        "note": ("未取得授权且同口径的历史收盘序列，九指数回撤统一显示 %s；"
                 "取得双源序列后按 inner join / 缺失率 0.5%% / 相对误差 0.10%% 核验通过才展示数值。" % NA_DISPLAY)
                if not verified else (
                    "近似数据（用户已拍板）：宽基为腾讯/东方财富不复权收盘近10年 MAX(close)，"
                    "红利六只暂用参考站 2026-08-07 快照（其 ath 为 MAX(high) 口径），"
                    "标普用 515450 ETF 代理；仅区间参考，不做精确口径承诺。"
                    if approx_only else "双源核验通过，展示同源收盘序列回撤。"),
        "rules": {
            "missingRateLimit": MISSING_RATE_LIMIT,
            "relTolerance": REL_TOLERANCE,
            "topN": TOP_N,
            "formula": "currentClose / highestClose - 1（同一指数收盘序列）",
        },
        "indices": rows,
    }


__all__ = [
    "DRAWDOWN_INDICES", "NO_SERIES_REASON", "NA_DISPLAY", "MISSING_RATE_LIMIT",
    "REL_TOLERANCE", "TOP_N", "normalize_series", "na_result", "verify_drawdown",
    "drawdown_board",
]
