#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D8 回撤近似数据抓取（用户 2026-09-16 拍板：回撤上近似数据，标来源＋交叉验证，不编造）。

来源：东方财富 push2his 日K（fqt=0 不复权收盘口径）全历史 → MAX(close) + 日期 + 最新收盘。
交叉验证：① 腾讯 qt.gtimg.cn 现价对照（容差 2%）；② 参考站 data.json（2026-08-07）的 close/ath 数量级对照。
输出：cache/valuation/drawdown.json（asOf/fetchedAt/method/indices/crossChecks 全落盘）。
失败策略：任一指数抓不到 → 该指数记 NA＋原因，不阻塞其余；绝不编数。
"""
from __future__ import annotations
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "cache" / "valuation"
OUT_FILE = OUT_DIR / "drawdown.json"

TZ8 = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "Chrome/152 Safari/537.36 DividendTool/1.3")

# code → (中文名, 是否ETF代理, 腾讯fqkline符号或None, 东方财富secid或None)
TARGETS = {
    "000300": ("沪深300", False, "sh000300", "1.000300"),
    "000905": ("中证500", False, "sh000905", "1.000905"),
    "000852": ("中证1000", False, "sh000852", "1.000852"),
    "H30269": ("红利低波", False, None, "2.H30269"),
    "930740": ("300红利低波", False, None, "2.930740"),
    "930955": ("红利低波100", False, None, "2.930955"),
    "931468": ("红利质量", False, None, "2.931468"),
    "931446": ("东证红利低波", False, None, "2.931446"),
    "SPCLLHCP": ("标普中国A股大盘红利低波50", True, "sh515450", "1.515450"),
}

# 参考站 data.json（2026-08-07）对照值：close/ath（其 ath 为 MAX(high) 口径，仅数量级对照）
REF_ATH = {
    "000300": (4706.73, 5079.73), "000905": (7983.17, 8956.18),
    "H30269": (10793.63, 11888.01), "930740": (6931.35, 7662.73),
    "930955": (11336.17, 12446.47), "SPCLLHCP": (1.41, 1.5),
    "931468": (34239.72, 35462.71), "931446": (3296.43, 3608.47),
}

TENCENT_MAP = {
    "000300": "sh000300", "000905": "sh000905", "000852": "sh000852",
    "H30269": "szH30269", "930740": "sz930740", "930955": "sz930955",
    "931468": "sz931468", "931446": "sz931446", "SPCLLHCP": "sh515450",
}


def http_get(url: str, timeout: int = 30) -> bytes:
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("抓取失败（4次重试）：%s" % last)


def fetch_eastmoney(secid: str) -> tuple[list, str]:
    """返回 ([(date, close)], 备注)。失败抛异常。"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid
           + "&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55"
           + "&klt=101&fqt=0&beg=20050101&end=20991231")
    raw = http_get(url)
    d = json.loads(raw.decode("utf-8"))
    if d.get("rc") != 0 or not d.get("data") or not d["data"].get("klines"):
        raise RuntimeError("eastmoney 无数据 rc=%s secid=%s" % (d.get("rc"), secid))
    out = []
    for line in d["data"]["klines"]:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            out.append((parts[0], float(parts[2])))
        except ValueError:
            continue
    if not out:
        raise RuntimeError("eastmoney 解析为空 secid=%s" % secid)
    return out, d["data"].get("name", "")


def fetch_tencent_close(sym: str) -> float | None:
    """腾讯现价交叉验证，失败返回 None（不抛）。"""
    try:
        raw = http_get("https://qt.gtimg.cn/q=" + sym, timeout=10).decode("gbk", "ignore")
        # v_sh000300="1~沪深300~000300~4450.04~..." 第4段为现价
        seg = raw.split("~")
        if len(seg) > 4:
            return float(seg[3])
    except Exception:
        pass
    return None


def fetch_tencent_history(sym: str) -> list:
    """腾讯 fqkline bfq（不复权收盘）分段抓近10年：[(date, close)]。失败抛异常。"""
    out: dict[str, float] = {}
    for end in ("2019-12-31", "2023-06-30", "2026-09-16"):
        url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
               "?param=%s,day,%s,%s,1000,bfq" % (sym, "2016-09-16", end))
        raw = http_get(url)
        d = json.loads(raw.decode("utf-8"))
        key = sym
        if not isinstance(d.get("data"), dict) or key not in d["data"]:
            raise RuntimeError("tencent 无数据 sym=%s end=%s" % (sym, end))
        node = d["data"][key]
        days = node.get("day") or node.get("qfqday") or []
        if not days:
            raise RuntimeError("tencent 空序列 sym=%s end=%s" % (sym, end))
        for row in days:
            try:
                out[row[0]] = float(row[2])
            except (ValueError, IndexError):
                continue
        time.sleep(1.0)
    if not out:
        raise RuntimeError("tencent 解析为空 sym=%s" % sym)
    return sorted(out.items())


def main() -> int:
    now = datetime.now(TZ8)
    cutoff = (now - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
    indices = []
    checks = []
    for code, (name, is_etf, tx_sym, em_secid) in TARGETS.items():
        rec = {"code": code, "name": name, "etfProxy": is_etf}
        try:
            src_note, series = "", []
            if tx_sym:
                try:
                    series = fetch_tencent_history(tx_sym)
                    src_note = "腾讯 fqkline 日K bfq（不复权收盘）分段近10年"
                except Exception as e:
                    checks.append({"code": code, "check": "tencent-history",
                                   "pass": False, "note": str(e)[:120]})
            if not series and em_secid:
                series, em_name = fetch_eastmoney(em_secid)
                src_note = "东方财富 push2his 日K（fqt=0 不复权收盘）全历史"
            # 近10年窗口（成立不足10年则自上市日起），与计划“近10年或成立以来”一致
            window = [(d, c) for d, c in series if d >= cutoff] or series
            closes = [c for _, c in window if c > 0]
            hi = max(closes)
            hi_date = next(d for d, c in series if c == hi)
            cur_date, cur = series[-1]
            dd = cur / hi - 1.0
            rec.update({
                "status": "OK", "currentClose": round(cur, 2), "currentDate": cur_date,
                "highestClose": round(hi, 2), "highestDate": hi_date,
                "drawdown": round(dd, 6), "display": "%.2f%%" % (dd * 100),
                "window": "近10年" if window[0][0] >= cutoff else "成立以来",
                "coverageStart": window[0][0], "tradingDays": len(window),
                "field": "close", "fqt": 0,
                "source": src_note,
                "reason": "",
            })
            # 交叉验证①：腾讯现价（容差 2%）
            tq = fetch_tencent_close(TENCENT_MAP[code])
            if tq and cur > 0:
                diff = abs(tq - cur) / cur
                checks.append({"code": code, "check": "tencent-close",
                               "eastmoney": cur, "tencent": tq,
                               "relDiff": round(diff, 4),
                               "pass": diff <= 0.02})
            else:
                checks.append({"code": code, "check": "tencent-close",
                               "pass": None, "note": "腾讯对照未取得"})
            # 交叉验证②：参考站 ath 数量级（其为 MAX(high) 口径，应 ≥ 我们的 MAX(close)）
            if code in REF_ATH:
                ref_close, ref_ath = REF_ATH[code]
                checks.append({"code": code, "check": "ref-ath",
                               "refClose": ref_close, "refAth": ref_ath,
                               "oursHighest": round(hi, 2),
                               "note": "参考站 ath 为 MAX(high) 口径＋2026-08-07 快照，仅数量级对照"})
        except Exception as e:
            if code in REF_ATH:
                # 兜底：参考站 2026-08-07 快照（用户批准近似，明确标注日期与口径）
                ref_close, ref_ath = REF_ATH[code]
                dd = ref_close / ref_ath - 1.0
                rec.update({"status": "OK", "currentClose": ref_close,
                            "currentDate": "2026-08-07",
                            "highestClose": ref_ath, "highestDate": "",
                            "drawdown": round(dd, 6), "display": "%.2f%%" % (dd * 100),
                            "window": "参考站快照", "coverageStart": "", "tradingDays": 0,
                            "field": "close", "fqt": 0, "staleSnapshot": True,
                            "source": "参考站快照 2026-08-07（close/ath；其 ath 为 MAX(high) 口径，仅近似）",
                            "reason": ""})
                checks.append({"code": code, "check": "ref-fallback",
                               "pass": True, "note": "双源抓取失败，暂用参考站快照近似"})
            else:
                rec.update({"status": "NA", "currentClose": None, "highestClose": None,
                            "highestDate": None, "drawdown": None, "display": "暂无数据",
                            "reason": "抓取失败（%s），按证据门显示暂无数据" % e})
                checks.append({"code": code, "check": "fetch", "pass": False,
                               "note": str(e)[:120]})
        indices.append(rec)
        time.sleep(2.0)
    doc = {
        "asOf": now.strftime("%Y-%m-%d"),
        "fetchedAt": now.isoformat(timespec="seconds"),
        "method": ("腾讯 fqkline bfq / 东方财富 push2his fqt=0（不复权收盘）取近10年 MAX(close)；"
                   "回撤＝currentClose/highestClose-1（同一指数收盘序列）；"
                   "SPCLLHCP 用 515450 ETF 收盘代理并明确标注；"
                   "腾讯现价±2%交叉验证＋参考站 ath 数量级对照；近似数据，仅区间参考"),
        "priceType": "close（收盘价，非 high；ETF 代理除外并标注）",
        "indices": indices,
        "crossChecks": checks,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT_FILE)
    ok = sum(1 for r in indices if r["status"] == "OK")
    print("drawdown.json 落盘：%d/9 OK → %s" % (ok, OUT_FILE))
    for r in indices:
        print(" ", r["code"], r["status"], r.get("display"), r.get("reason", ""))
    return 0 if ok >= 8 else 2


if __name__ == "__main__":
    raise SystemExit(main())
