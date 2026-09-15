#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""红利打新底仓计算器 V1.2 本地服务
- 同源代理并持久化中证官方 closeweight XLS
- 主行情：腾讯公开行情；备用：东方财富公开行情；兜底：本地 quotes.json
- 不依赖第三方 Python 包
"""
from __future__ import annotations
import argparse, json, mimetypes, os, re, sys, threading, time, urllib.parse, urllib.request, webbrowser
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
OFFICIAL = CACHE / "official"
PARSED = CACHE / "parsed"
META = CACHE / "meta"
QUOTE_CACHE = Path(os.environ.get("DIVIDEND_QUOTE_CACHE") or (CACHE / "quotes.json"))
for p in (CACHE, OFFICIAL, PARSED, META): p.mkdir(parents=True, exist_ok=True)

# V1.3 D1 账本 API（/api/ledger/*）；旧接口语义不变。缺失时不拖垮 V1.2 服务。
try:
    from db import api as ledger_api
    LEDGER_IMPORT_ERROR = ""
except Exception as _e:  # pragma: no cover - 兜底
    ledger_api = None
    LEDGER_IMPORT_ERROR = str(_e)

# V1.3 D4 估值回撤核验（只读算法）；缺失时不拖垮 V1.2 服务。
try:
    from db import valution as drawdown_api
    DRAWDOWN_IMPORT_ERROR = ""
except Exception as _e:  # pragma: no cover - 兜底
    drawdown_api = None
    DRAWDOWN_IMPORT_ERROR = str(_e)

# 行情三路状态契约（PRODUCT_PLAN_V1.0 P0#4）
QUOTE_TIMEOUT = 3                  # 单次请求 timeout=3s
QUOTE_ATTEMPTS = 2                 # 每个源最多重试 2 次
QUOTE_BACKOFF = (0.5, 1.5)         # 退避 0.5s → 1.5s
DEGRADED_FAILS = 3                 # 10 分钟窗口内连续 3 次失败即 DEGRADED
DEGRADED_WINDOW = 600              # 10 分钟滚动窗口（秒）
RECOVER_AFTER = 2                  # 同一源连续 2 次全校验通过才由 DEGRADED/STALE 恢复 LIVE/FRESH
CACHE_MAX_AGE_SEC = 72 * 3600      # 缓存最大陈旧 72 小时
CACHE_MAX_TRADING_DAYS = 3         # 或跨越 3 个交易日
PRICE_MIN = 0.01                   # 普通行情价格下限（元）
PRICE_MAX = 1_000_000.0            # 普通行情价格上限（元）
DATADATE_MAX_AGE_DAYS = 10         # dataDate 超过该自然日数即视为无效（不计数、不恢复）
DEGRADED_STATES = ("DEGRADED", "STALE", "STALE_BLOCKED")
QUOTE_STATUSES = ("LIVE", "DEGRADED", "CACHE", "STALE_BLOCKED", "MANUAL_OVERRIDE")
_SOURCE_HEALTH = {}                # 进程内滚动健康度：同一窗口内连续失败次数
_HEALTH_LOCK = threading.Lock()

CSI_WEIGHT_URLS = {
    "H30269": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/H30269closeweight.xls",
    "930740": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/930740closeweight.xls",
    "930955": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/930955closeweight.xls",
    "931468": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/931468closeweight.xls",
    "931446": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/931446closeweight.xls",
}
KNOWN_CODES = set(CSI_WEIGHT_URLS) | {"SPCLLHCP"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152 Safari/537.36 DividendTool/1.2"
TZ8 = timezone(timedelta(hours=8))

def now_cn() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")

def parse_dt(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ8)
    except Exception:
        return None

def market_date(value) -> str:
    s = str(value or "")
    return s[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s) else ""

def age_seconds(value, now: datetime | None = None) -> int | None:
    dt = parse_dt(value)
    if dt is None: return None
    return max(0, int(((now or datetime.now(TZ8)) - dt).total_seconds()))

def trading_days_between(start, end) -> int:
    """统计 (start, end] 之间的工作日数量（简化交易日口径：周一至周五）。"""
    a, b = parse_dt(start), parse_dt(end)
    if a is None or b is None: return 0
    d, n = a.date(), 0
    while d < b.date():
        d = d + timedelta(days=1)
        if d.weekday() < 5: n += 1
    return n

def cache_quote_status(cached: dict, now: datetime | None = None) -> dict:
    """纯函数：判断本地缓存行情是 CACHE 还是 STALE_BLOCKED（不伪装实时）。"""
    now = now or datetime.now(TZ8)
    src_time = (cached or {}).get("fetched_at") or (cached or {}).get("market_time")
    if parse_dt(src_time) is None:
        return {"status": "STALE_BLOCKED", "stale": True, "cacheAgeSeconds": None,
                "cacheTradingDays": None, "cacheReason": "缓存缺少可解析时间戳，按陈旧处理"}
    age = age_seconds(src_time, now)
    td = trading_days_between(src_time, now)
    stale = age > CACHE_MAX_AGE_SEC or td > CACHE_MAX_TRADING_DAYS
    return {"status": "STALE_BLOCKED" if stale else "CACHE", "stale": stale,
            "cacheAgeSeconds": age, "cacheTradingDays": td,
            "cacheReason": ("缓存已 %d 秒/跨 %d 个交易日，超过 72 小时或 3 个交易日阈值，不得伪装实时"
                            % (age, td)) if stale else "使用最近成功本地缓存（未超陈旧阈值）"}

def error_code(exc: Exception) -> str:
    s = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timed out" in s or "timeout" in s: return "TIMEOUT"
    if "resolve" in s or "nodename" in s or "name or service" in s: return "DNS_FAIL"
    if "connection refused" in s: return "CONN_REFUSED"
    if "connection" in s: return "CONN_FAIL"
    if "http error" in s or "bad status" in s: return "HTTP_FAIL"
    if "json" in s or "decode" in s: return "PARSE_FAIL"
    return "SOURCE_FAIL"

def _quote_problem(code: str, x: dict, now: datetime) -> str:
    """单行行情字段范围 + dataDate 校验；返回问题描述，空串表示通过。"""
    if not isinstance(x, dict):
        return "%s 行情行不是对象" % code
    try:
        price = float(x.get("price"))
    except (TypeError, ValueError):
        return "%s 价格不可解析" % code
    if not (PRICE_MIN <= price <= PRICE_MAX):
        return "%s 价格 %.4f 超出范围 [%s, %s]" % (code, price, PRICE_MIN, PRICE_MAX)
    ref = x.get("market_time") or x.get("fetched_at")
    dt = parse_dt(ref)
    if dt is None:
        return "%s dataDate 缺失/不可解析" % code
    future = (dt - now).total_seconds()
    age_days = (now - dt).total_seconds() / 86400.0
    if future > 86400:
        return "%s dataDate 位于未来（%s）" % (code, market_date(ref))
    if age_days > DATADATE_MAX_AGE_DAYS:
        return "%s dataDate 过旧（%.1f 天，>%d 天）" % (code, age_days, DATADATE_MAX_AGE_DAYS)
    return ""


def split_valid_quotes(rows, now: datetime | None = None) -> tuple[dict, list[str]]:
    """把一次抓取结果拆成「字段范围/dataDate 全校验通过」的行与问题列表。

    坏 dataDate / 价格越界只剔除该行并记录问题，不当成成功计数（P1-1）。
    """
    now = now or datetime.now(TZ8)
    valid: dict = {}
    problems: list[str] = []
    if not rows:
        return valid, ["空结果（无有效行情行）"]
    for code, x in rows.items():
        problem = _quote_problem(code, x, now)
        if problem:
            problems.append(problem)
        else:
            valid[code] = x
    return valid, problems


def validate_quote_rows(rows, now: datetime | None = None) -> list[str]:
    """P1-1：HTTP/解析之外补字段范围 + dataDate 校验；返回问题列表（空=全校验通过）。"""
    return split_valid_quotes(rows, now)[1]


def note_source_result(name: str, ok: bool, err: str = "", now: datetime | None = None,
                       window_seconds: int | None = None) -> dict:
    """滚动健康度（P1-1 修复）：
    - 连续失败 >=3 次（10 分钟滚动窗口内）标 DEGRADED；
    - 恢复需同一源连续 2 次全校验通过，才由 DEGRADED/STALE 回到 LIVE/FRESH；
    - 连续计数按 windowSeconds 滚动窗口过期重置，旧窗口的失败/成功不累加。
    """
    now = now or datetime.now(TZ8)
    window = DEGRADED_WINDOW if window_seconds is None else int(window_seconds)
    with _HEALTH_LOCK:
        st = _SOURCE_HEALTH.setdefault(name, {"consecutiveFailures": 0, "consecutiveSuccesses": 0,
                                              "lastSuccessAt": "", "lastFailureAt": "",
                                              "lastError": "", "lastCheckedAt": "", "status": "UNKNOWN",
                                              "windowSeconds": window, "recoveredAfter": RECOVER_AFTER})
        prev_status = st.get("status") or "UNKNOWN"
        last = parse_dt(st.get("lastCheckedAt"))
        if last is not None and (now - last).total_seconds() > window:
            st["consecutiveFailures"] = 0
            st["consecutiveSuccesses"] = 0
            prev_status = "expired"
        if ok:
            st["consecutiveSuccesses"] += 1
            st["consecutiveFailures"] = 0
            st["lastSuccessAt"] = now.isoformat(timespec="seconds")
            st["lastError"] = ""
            if prev_status in DEGRADED_STATES:
                st["status"] = ("LIVE" if st["consecutiveSuccesses"] >= RECOVER_AFTER else prev_status)
            else:
                st["status"] = "LIVE"
        else:
            st["consecutiveFailures"] += 1
            st["consecutiveSuccesses"] = 0
            st["lastFailureAt"] = now.isoformat(timespec="seconds")
            st["lastError"] = err
            if prev_status in DEGRADED_STATES:
                st["status"] = prev_status
            else:
                st["status"] = "DEGRADED" if st["consecutiveFailures"] >= DEGRADED_FAILS else "LIVE"
        st["recoveredAfter"] = RECOVER_AFTER
        st["windowSeconds"] = window
        st["lastCheckedAt"] = now.isoformat(timespec="seconds")
        return dict(st)


def reset_source_health() -> None:
    """清空进程内源健康度（自检/测试用；正常生产流程不调用）。"""
    with _HEALTH_LOCK:
        _SOURCE_HEALTH.clear()

def source_health() -> dict:
    with _HEALTH_LOCK:
        return {k: dict(v) for k, v in _SOURCE_HEALTH.items()}

def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)

def atomic_json(path: Path, obj) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))

def load_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def http_get(url: str, timeout: int = 12, headers: dict | None = None) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())

def fetch_official_weight(code: str, refresh: bool = False) -> dict:
    if code not in CSI_WEIGHT_URLS: raise ValueError("not a CSI weight code")
    path = OFFICIAL / f"{code}closeweight.xls"
    meta_path = META / f"{code}.json"
    if path.exists() and not refresh:
        return {"ok": True, "path": path, "source": "official-cache", "cached_at": datetime.fromtimestamp(path.stat().st_mtime, TZ8).isoformat(timespec="seconds")}
    try:
        raw, hdr = http_get(CSI_WEIGHT_URLS[code], headers={"Referer": "https://www.csindex.com.cn/"})
        if len(raw) < 512: raise RuntimeError(f"官方文件异常偏小：{len(raw)} bytes")
        atomic_write(path, raw)
        meta = {"code": code, "url": CSI_WEIGHT_URLS[code], "fetched_at": now_cn(), "bytes": len(raw), "etag": hdr.get("ETag"), "last_modified": hdr.get("Last-Modified")}
        atomic_json(meta_path, meta)
        return {"ok": True, "path": path, "source": "official-live", **meta}
    except Exception as e:
        if path.exists():
            return {"ok": True, "path": path, "source": "official-cache-stale", "warning": str(e), "cached_at": datetime.fromtimestamp(path.stat().st_mtime, TZ8).isoformat(timespec="seconds")}
        return {"ok": False, "error": str(e), "url": CSI_WEIGHT_URLS[code]}

def parse_tencent(text: str, wanted: set[str]) -> dict:
    out = {}
    # var v_sh600000="...";
    for sid, body in re.findall(r'v_((?:sh|sz)\d{6})="([^"]*)"', text):
        code = sid[2:]
        if code not in wanted: continue
        a = body.split("~")
        try: price = float(a[3] or a[4])
        except Exception: continue
        if not (price > 0): continue
        mt = ""
        if len(a) > 30:
            ts = a[30].strip()
            if re.fullmatch(r"\d{14}", ts):
                mt = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
        out[code] = {"price": price, "source": "腾讯主源", "market_time": mt, "fetched_at": now_cn(), "stale": False}
    return out

def fetch_tencent(symbols: list[str], timeout: int = QUOTE_TIMEOUT) -> dict:
    out = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i+50]
        url = "https://qt.gtimg.cn/q=" + ",".join(chunk)
        raw, _ = http_get(url, timeout=timeout, headers={"Referer": "https://finance.qq.com/"})
        text = raw.decode("gbk", errors="ignore")
        out.update(parse_tencent(text, {x[2:] for x in chunk}))
    return out

def fetch_eastmoney(symbols: list[str], timeout: int = QUOTE_TIMEOUT) -> dict:
    # secid: 1=沪市, 0=深市。f124 通常为更新时间 Unix 秒。
    secids = [(("1." if x.startswith("sh") else "0.") + x[2:]) for x in symbols]
    out = {}
    for i in range(0, len(secids), 80):
        chunk = secids[i:i+80]
        q = urllib.parse.urlencode({
            "fltt": "2", "invt": "2", "fields": "f12,f14,f2,f124",
            "secids": ",".join(chunk), "ut": "bd1d9ddb04089700cf9c27f6f7426281"
        })
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + q
        raw, _ = http_get(url, timeout=timeout, headers={"Referer": "https://quote.eastmoney.com/"})
        j = json.loads(raw.decode("utf-8", errors="replace"))
        for x in ((j.get("data") or {}).get("diff") or []):
            code = str(x.get("f12") or "")
            try: price = float(x.get("f2"))
            except Exception: continue
            if not re.fullmatch(r"\d{6}", code) or not (price > 0): continue
            mt = ""
            try:
                ts = int(x.get("f124") or 0)
                if ts > 1_000_000_000: mt = datetime.fromtimestamp(ts, TZ8).strftime("%Y-%m-%d %H:%M:%S")
            except Exception: pass
            out[code] = {"price": price, "source": "东方财富备用", "market_time": mt, "fetched_at": now_cn(), "stale": False}
    return out

def normalize_symbols(raw: str) -> list[str]:
    out=[]
    for s in raw.split(","):
        s=s.strip().lower()
        if re.fullmatch(r"(?:sh|sz)\d{6}", s): out.append(s)
    # dedupe preserving order and cap
    return list(dict.fromkeys(out))[:300]

def fetch_with_backoff(fetch_fn, symbols: list[str]) -> tuple[dict, int, str]:
    """按 timeout=3s、最多 2 次、退避 0.5s→1.5s 抓取；返回 (数据, 尝试次数, 错误码)。"""
    attempts = 0
    last = ""
    for i in range(QUOTE_ATTEMPTS):
        attempts += 1
        try:
            return fetch_fn(symbols), attempts, ""
        except Exception as e:
            last = error_code(e)
            if i < QUOTE_ATTEMPTS - 1: time.sleep(QUOTE_BACKOFF[min(i, len(QUOTE_BACKOFF) - 1)])
    return {}, attempts, last

def quote_row(price, source, market_time, fetched_at, status, attempts, err, cache_age=None,
              cache=False, cache_reason="", cache_trading_days=None, now=None) -> dict:
    """统一行情行契约：source/status/dataDate/fetchedAt/ageSeconds/attempts/errorCode/cacheAgeSeconds/stale。"""
    now = now or datetime.now(TZ8)
    ref = market_time or fetched_at
    stale = bool(status == "STALE_BLOCKED")
    return {
        "price": price, "source": source, "market_time": market_time or "", "fetched_at": fetched_at or "",
        "fetchedAt": fetched_at or "", "dataDate": market_date(ref), "status": status,
        "attempts": attempts, "errorCode": err or "",
        "ageSeconds": age_seconds(ref, now), "cache": cache,
        "cacheAgeSeconds": cache_age, "cacheTradingDays": cache_trading_days,
        "stale": stale, "cacheReason": cache_reason, "manualOverride": False,
    }

def get_quotes(symbols: list[str]) -> dict:
    wanted_codes = {s[2:] for s in symbols}
    cache_doc = load_json(QUOTE_CACHE, {"quotes": {}, "saved_at": ""})
    cached = cache_doc.get("quotes") or {}
    now = datetime.now(TZ8)
    online = {}
    errors = []
    attempts_total = 0

    primary_raw, a1, e1 = fetch_with_backoff(fetch_tencent, symbols)
    attempts_total += a1
    primary, p1 = split_valid_quotes(primary_raw, now)
    primary_err = e1 or ";".join(p1[:3])
    primary_ok = (not e1) and (not p1)
    note_source_result("腾讯主源", primary_ok, primary_err, now)
    if not primary_ok:
        errors.append("腾讯:" + primary_err)
    online.update(primary)

    degraded = False
    missing_symbols = [s for s in symbols if s[2:] not in online]
    if missing_symbols:
        backup_raw, a2, e2 = fetch_with_backoff(fetch_eastmoney, missing_symbols)
        attempts_total += a2
        backup, p2 = split_valid_quotes(backup_raw, now)
        backup_err = e2 or ";".join(p2[:3])
        backup_ok = (not e2) and (not p2)
        note_source_result("东方财富备用", backup_ok, backup_err, now)
        if not backup_ok:
            errors.append("东方财富:" + backup_err)
        if backup: degraded = True
        online.update(backup)

    errs = ";".join(errors)
    result = {}
    for code, x in online.items():
        src = str(x.get("source") or "未知")
        status = "LIVE" if src == "腾讯主源" else "DEGRADED"
        result[code] = quote_row(x.get("price"), src, x.get("market_time"), x.get("fetched_at") or now_cn(),
                                 status, attempts_total, "", now=now)

    cached_used = 0
    for code in sorted(wanted_codes - set(result)):
        c = cached.get(code)
        if c and c.get("price"):
            cs = cache_quote_status(c, now)
            result[code] = quote_row(
                c.get("price"), "本地行情缓存（原:" + str(c.get("source", "未知")) + "）",
                c.get("market_time"), c.get("fetched_at"), cs["status"], attempts_total,
                errs or "ONLINE_UNAVAILABLE", cs["cacheAgeSeconds"], True, cs["cacheReason"],
                cs["cacheTradingDays"], now)
            cached_used += 1

    if online:
        merged = dict(cached)
        merged.update(online)
        atomic_json(QUOTE_CACHE, {"saved_at": now_cn(), "quotes": merged})
    return {"quotes": result, "online_count": len(online), "cached_count": cached_used,
            "requested": len(symbols), "errors": errors, "degraded": degraded,
            "attempts": attempts_total, "statuses": list(QUOTE_STATUSES),
            "sources": source_health(), "fetched_at": now_cn()}

def cache_status() -> dict:
    idx = {}
    for c in sorted(KNOWN_CODES):
        raw = OFFICIAL / f"{c}closeweight.xls"
        parsed = PARSED / f"{c}.json"
        meta = load_json(META / f"{c}.json", {})
        idx[c] = {"raw": raw.exists(), "parsed": parsed.exists(), "raw_mtime": datetime.fromtimestamp(raw.stat().st_mtime,TZ8).isoformat(timespec="seconds") if raw.exists() else "", "parsed_mtime": datetime.fromtimestamp(parsed.stat().st_mtime,TZ8).isoformat(timespec="seconds") if parsed.exists() else "", "official_fetched_at": meta.get("fetched_at", "")}
    q = load_json(QUOTE_CACHE, {"quotes": {}, "saved_at": ""})
    return {"cache_dir": str(CACHE), "indices": idx, "quotes": {"count": len(q.get("quotes") or {}), "saved_at": q.get("saved_at", "")}}

class Handler(BaseHTTPRequestHandler):
    server_version = "DividendTool/1.2"
    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt%args))
    def send_json(self, obj, status=200):
        raw=json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); path=u.path; qs=urllib.parse.parse_qs(u.query)
        if path=="/api/health": return self.send_json({"ok":True,"version":"1.2","time":now_cn()})
        if path=="/api/cache-status": return self.send_json(cache_status())
        if path=="/api/holdings":
            code=(qs.get("code") or [""])[0]
            if code not in KNOWN_CODES: return self.send_json({"error":"unknown code"},400)
            f=PARSED/f"{code}.json"
            if not f.exists(): return self.send_json({"error":"parsed cache missing"},404)
            return self.send_json(load_json(f,{}))
        if path=="/api/prefetch":
            refresh=(qs.get("refresh") or ["0"])[0]=="1"
            results={c:{k:v for k,v in fetch_official_weight(c,refresh).items() if k!="path"} for c in CSI_WEIGHT_URLS}
            return self.send_json({"results":results,"time":now_cn()})
        if path=="/api/weight":
            code=(qs.get("code") or [""])[0]; refresh=(qs.get("refresh") or ["0"])[0]=="1"
            if code not in CSI_WEIGHT_URLS: return self.send_json({"error":"not a CSI index"},400)
            x=fetch_official_weight(code,refresh)
            if not x.get("ok"): return self.send_json(x,502)
            raw=Path(x["path"]).read_bytes(); self.send_response(200); self.send_header("Content-Type","application/vnd.ms-excel"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.send_header("X-Data-Source",str(x.get("source",""))); self.send_header("X-Cache-Time",str(x.get("fetched_at") or x.get("cached_at") or "")); self.end_headers(); self.wfile.write(raw); return
        if path=="/api/quotes":
            symbols=normalize_symbols((qs.get("symbols") or [""])[0])
            if not symbols: return self.send_json({"quotes":{},"error":"no valid symbols"},400)
            return self.send_json(get_quotes(symbols))
        if path=="/api/drawdown":
            if drawdown_api is None:
                return self.send_json({"ok":False,"error":"valuation module unavailable","detail":DRAWDOWN_IMPORT_ERROR},500)
            return self.send_json(drawdown_api.drawdown_board())
        if ledger_api is not None and ledger_api.handles(path):
            status,obj=ledger_api.route("GET",path,{k:v[0] for k,v in qs.items()},None)
            return self.send_json(obj,status)
        if ledger_api is None and path.startswith("/api/ledger"):
            return self.send_json({"ok":False,"error":"ledger module unavailable","detail":LEDGER_IMPORT_ERROR},500)
        return self.serve_static(path)
    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/ledger"):
            if ledger_api is None: return self.send_json({"ok":False,"error":"ledger module unavailable","detail":LEDGER_IMPORT_ERROR},500)
            try:
                n=int(self.headers.get("Content-Length","0"))
                if n<=0 or n>2_000_000: raise ValueError("invalid body size")
                body=json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception as e:
                return self.send_json({"ok":False,"error":str(e)},400)
            qs=urllib.parse.parse_qs(u.query)
            status,obj=ledger_api.route("POST",u.path,{k:v[0] for k,v in qs.items()},body)
            return self.send_json(obj,status)
        if u.path!="/api/save-parsed": return self.send_json({"error":"not found"},404)
        try:
            n=int(self.headers.get("Content-Length","0"));
            if n<=0 or n>2_000_000: raise ValueError("invalid body size")
            d=json.loads(self.rfile.read(n).decode("utf-8")); code=str(d.get("code") or "")
            if code not in KNOWN_CODES: raise ValueError("unknown code")
            hs=d.get("holdings") or []
            if not (10 <= len(hs) <= 300): raise ValueError("holdings count abnormal")
            clean=[]
            for h in hs:
                c=str(h.get("code") or ""); w=float(h.get("weight") or 0)
                if not re.fullmatch(r"\d{6}",c) or not (0<w<100): continue
                clean.append({"code":c,"name":str(h.get("name") or c)[:40],"market":"SH" if str(h.get("market"))=="SH" else "SZ","weight":w,"star":bool(h.get("star"))})
            if len(clean)<10: raise ValueError("valid rows too few")
            sw=sum(x["weight"] for x in clean)
            if not (70 <= sw <= 130): raise ValueError(f"weight sum abnormal: {sw}")
            doc={"code":code,"date":str(d.get("date") or ""),"source":str(d.get("source") or "parsed"),"saved_at":now_cn(),"holdings":clean,"weight_sum":sw}
            atomic_json(PARSED/f"{code}.json",doc)
            return self.send_json({"ok":True,"count":len(clean),"weight_sum":sw,"saved_at":doc["saved_at"]})
        except Exception as e: return self.send_json({"error":str(e)},400)
    def serve_static(self, path: str):
        if path in ("","/"): path="/index.html"
        rel=Path(urllib.parse.unquote(path.lstrip("/")))
        target=(ROOT/rel).resolve()
        try: target.relative_to(ROOT)
        except ValueError: return self.send_json({"error":"forbidden"},403)
        # 数据库文件与 db/ 结构不经静态服务暴露（浏览器只能走 API）
        if (rel.parts and rel.parts[0] in ("db","var")) or target.suffix.lower() in (".db",".sqlite",".sqlite3") or target.name.endswith((".db-wal",".db-shm")):
            return self.send_json({"error":"forbidden"},403)
        if not target.is_file(): return self.send_json({"error":"not found"},404)
        raw=target.read_bytes(); mime=mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime+("; charset=utf-8" if mime.startswith("text/") else "")); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-cache"); self.end_headers(); self.wfile.write(raw)

def prefetch_cli(refresh=True) -> int:
    print("开始更新中证官方权重原始缓存…")
    ok=0
    for c in CSI_WEIGHT_URLS:
        r=fetch_official_weight(c,refresh)
        print(c, "OK" if r.get("ok") else "FAIL", r.get("source") or r.get("error"))
        ok += int(bool(r.get("ok")))
    print(f"完成：{ok}/{len(CSI_WEIGHT_URLS)}；缓存目录 {OFFICIAL}")
    return 0 if ok==len(CSI_WEIGHT_URLS) else 2

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--port",type=int,default=8765); ap.add_argument("--no-open",action="store_true"); ap.add_argument("--prefetch-only",action="store_true"); ap.add_argument("--refresh",action="store_true"); ap.add_argument("--db",default=None,help="账本开发库路径（默认 ./dev.db 或环境变量 DIVIDEND_LEDGER_DB）"); args=ap.parse_args()
    if args.db: os.environ["DIVIDEND_LEDGER_DB"]=str(Path(args.db).expanduser())
    if args.prefetch_only: raise SystemExit(prefetch_cli(args.refresh or True))
    srv=ThreadingHTTPServer(("127.0.0.1",args.port),Handler); url=f"http://127.0.0.1:{args.port}/"
    print("\n红利打新底仓计算器 V1.2 正式长期版")
    if ledger_api is not None:
        try:
            st=ledger_api.route("GET","/api/ledger/status",{},None)[1]
            print(f"账本(D1) 开发库：{st.get('db_path')}（schema v{st.get('schema_version')}）")
        except Exception as e:
            print(f"账本(D1) 初始化异常：{e}")
    else:
        print(f"账本(D1) 未加载：{LEDGER_IMPORT_ERROR}")
    print("地址:",url); print("关闭：在本窗口按 Ctrl+C\n")
    if not args.no_open: threading.Timer(0.8,lambda:webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    finally: srv.server_close()
if __name__=="__main__": main()
