# Dividend-Index IPO Base-Position Calculator V1.3

[简体中文](./README.md) | English

## What this is for

This closes the loop for one person, running entirely on a local machine: judge dividend-index valuations → verify constituents and weights against official sources → enter your capital → compute how much to buy of each stock, the theoretical share count, and the legally tradable share count/lot size → freeze an order plan → place orders with phone assistance → confirm each fill manually → trace real holdings and strategy cash. It manages the "base position" (底仓) you hold in the A-share market to qualify for new-share (IPO) subscriptions on the two exchanges.

The tool only plans, records, and cross-checks. It **makes no automatic decisions and places no automatic trades**, connects to no broker API, and uses no Supabase. The target environment is self-hosted on a Mac Mini and operated from a desktop browser.

## Quick start (Mac)

Double-click: `启动工具.command`

The browser opens automatically at: `http://127.0.0.1:8765/`

To shut the tool down: return to the terminal window and press `Ctrl+C`.

Command-line startup:

```bash
# Normal start (default port 8765, opens the browser automatically)
python3 server.py

# Specify a port / do not open the browser
python3 server.py --port 8765 --no-open

# Specify the ledger dev-database path (or set env var DIVIDEND_LEDGER_DB)
python3 server.py --db ./dev.db
```

> Running `index.html` directly by double-clicking is not recommended for daily use. That is a degraded mode: it can still read the in-package files and the browser cache, but the disk-persistent cache, the same-origin proxy for official XLS files, and the primary/backup quote feeds do not work reliably.

## The nine indices (3 broad-market + 6 dividend)

- 000300 CSI 300
- 000905 CSI 500
- 000852 CSI 1000
- H30269 CSI Dividend Low Volatility Index
- 930740 CSI 300 Dividend Low Volatility Index
- 930955 CSI Dividend Low Volatility 100 Index
- SPCLLHCP S&P China A-Share LargeCap Dividend Low Volatility 50
- 931468 CSI Dividend Quality Index
- 931446 CSI Dongfanghong Dividend Low Volatility Index

The valuation overview uses one fixed field order: index/code → latest close → highest close and its date → drawdown → PE/PB/dividend yield with their percentiles → joint interpretation → data date/source/fetch time → official verification. Next to each index the page keeps the corresponding **official index page/fact sheet, official compilation methodology, official constituents file, and official weights file (for CSI indices)** so a human can re-verify them.

## Drawdown (approximate method, shipped on D9)

Drawdown is fixed as `latest close / highest close of the same index − 1`, and both closes must come from **the same index close series**.

Since none of the nine indices currently has a licensed same-method ten-year close history, the highest close uses an approximation: `MAX(close)` over roughly the last 10 years of unadjusted closes from Tencent/East Money; indices whose fetch fails fall back to a reference-site snapshot, clearly labeled (with `asOf`, source, and crossChecks cross-verification records — see `cache/valuation/drawdown.json` and the per-page source footnotes). Broad-market indices approximate a real close series; dividend indices approximate via snapshot/ETF proxy — all are honestly labeled approximations, not officially dual-source-verified values.

## Valuation percentiles and risk premium

- Valuation comes in three layers (course / official / third-party), each labeled with its own method and date. Methods are never mixed and percentiles are never merged.
- Broad-market PE/PB/dividend-yield percentiles introduce public estimates under the Evidence Gate B exception (each cell marked "estimate" + source name + date + URL), displayed in a separate area from the course layer and the official layer.
- Broad-market risk premium: there is no course-template value, so it is reverse-engineered with the reference site's formula `100 − PE percentile` and marked "estimate" (currently 36.2 / 22.3 / 30.2 for 000300 / 000905 / 000852). The **dividend-yield variant has no licensed same-method source and still shows "no data" — it is not estimated and not filled in**.
- Any field without a reliable source shows "no data". No invented numbers, and no substitution of ETF / single-stock / intraday-high values as proxies.

## How the cache works

Three layers of protection:

1. **Project disk cache (primary)**: `cache/official/` stores the raw official weights XLS files; `cache/parsed/` stores parsed constituents JSON; `cache/quotes.json` stores the most recent successful quotes.
2. **In-package snapshots (fallback)**: verified snapshots for 930740 and SPCLLHCP are currently pre-bundled.
3. **Browser localStorage (second-tier speed-up)**: no longer the only cache, so clearing browser data does not delete the formal data in the `cache/` directory.

On the first formal networked launch, the page automatically checks which CSI indices lack a parsed cache and tries to fill them from the CSI (China Securities Index) official site. If the official site is temporarily unreachable later, old caches are never cleared.

Before a desktop agent refreshes the official raw-weights cache, it can run:

```bash
python3 server.py --prefetch-only --refresh
```

Then start the site so the page parses the official XLS files into `cache/parsed/`, and finish the cross-check and acceptance.

## Quote sources (three paths + five states)

The order is fixed:

**Tencent public quotes (primary) → East Money public quotes (backup) → local cache of the last successful quotes (fallback)**

Each stock row shows "quote source / time / data date / status". The status enum has five values: `LIVE` / `DEGRADED` / `CACHE` / `STALE_BLOCKED` / `MANUAL_OVERRIDE`.

The contract: one request has `timeout=3s`; at most 2 retries per source with a `0.5s → 1.5s` backoff; 3 consecutive failures of the same source within a 10-minute window marks it `DEGRADED` and switches to the next source; the local cache may be at most 72 hours old or span at most 3 trading days, beyond which it is `STALE_BLOCKED` (never pretending to be live); the same source must pass all checks twice consecutively to return to `LIVE`.

The two public feeds exist only for capital estimation — they are not broker execution quotes; real orders follow your broker's order book. Ordinary prices are **read-only** in the main table.

### Manual override area (advanced exception handling, hidden by default)

Only when all three quote paths are unavailable and a human price check is unavoidable, click "显示高级异常处理" (show advanced exception handling) to expand the by-default-hidden manual override area.

A manual override affects only this page's calculation display: it writes to local `localStorage` (key `divManualOverride`) and marks the row `MANUAL_OVERRIDE`; press Enter after typing to apply it, and clearing the input or clicking "清空全部手动覆盖" (clear all manual overrides) restores automatic quotes.

**Manual override prices never enter ledger pricing**: creating a frozen batch with any manually overridden stock is rejected with a prompt.

## Investment cycles and batches (the ledger loop)

The ledger keeps cycles (投资周期), batches (下单批次), order_item (per-stock line items), transactions (成交), and cash_ledger (strategy cash) in SQLite.

Within one cycle you can generate four batch types: `INITIAL` first position, `ADD` additional investment (buy-only, underweight names first), `REBALANCE` full rebalance (generating BUY/SELL plans together), and `EXIT` liquidation (per-line SELL).

A batch can be frozen into a plan snapshot that cannot silently change (storing weights version/date, quote source/time, target amounts, suggested share counts, deviations, and algorithm version). To update, you explicitly generate a new `revision`; refreshing quotes does not change a frozen batch's suggested share counts, and confirmed items cannot be rewritten.

**All batches only generate plans — nothing executes, orders, or sells automatically.** Only fills verified by the human get written into the ledger. Test batches can be deleted (deleting a CONFIRMED one requires typing "确认删除" plus an audit trail; CLOSED batches are refused).

## Order execution page (phone assistance)

Open section "六、下单执行" (order execution), choose the investment cycle and batch, and switch between checklist list and single-stock focus modes.

Each stock goes through four states: `PENDING` to order / `CONFIRMED` fill confirmed / `SKIPPED` / `REVIEW` pending review. You can copy the code/name/quantity/single-line record, and place the actual order by hand in the Galaxy (银河证券) app.

**Only "fill confirmed" writes to the real transaction ledger** (through the `record_transaction` linkage). `CONFIRMED` cannot be set directly via the status API, but can be undone by typing "撤销确认" (revoke confirmation) inline (which linked-deletes the transaction/cash events, returns the row to PENDING, and is refused for CLOSED batches plus audited).

Completion gate: the run passes only when everything is handled as fill-confirmed or skipped (any to-order or to-review item means not passed). Refreshing the page restores progress from the local service.

## Holdings and history page (read-only)

Section "七、持仓与历史" (holdings and history) is read-only. Holdings are **rebuilt from confirmed transactions by default** (view `v_holdings`), showing quantity, average price, cost, constituent status, and a source declaration.

It also shows the strategy cash balance and the cash-event ledger (an append-only event ledger that can be traced back).

Holdings that are no longer current constituents are kept visible and marked `STALE_CONSTITUENT`; no new BUY is allocated to them, and they are sold in full as usual during liquidation.

## Ledger dev database and isolation

- The ledger defaults to the dev database `./dev.db`; the path can be overridden with `--db <path>` or the `DIVIDEND_LEDGER_DB` environment variable.
- **Dev database and container database are isolated**: development/testing may only use temporary or dev databases such as `./dev.db` and must never touch production directories. Under Docker the ledger is fixed at `/data/ledger.db` inside the container (`DIVIDEND_LEDGER_DB`), which never mixes with the local dev database — see the next section.
- `.db` / `.db-wal` / `.db-shm` / `var/` / `DockerData/` / `DockerBackups/` are excluded by `.gitignore`, so database runtime files never enter Git; the static server refuses to expose the `db/` directory and `.db` files — the browser can reach the ledger only through the API.
- All demo data is fictional and can be cleared. For backup/restore use SQLite `.backup` or `VACUUM INTO`, and after restoring verify with `integrity_check` and `foreign_key_check`.
- Full regression: `python3 scripts/ledger_smoke_test.py` (creates a dev database in the system temp directory and never touches the production database or directories), currently **282/282 EXIT=0**.

## Docker deployment (optional, single-machine resident)

The repo ships a four-piece set — `Dockerfile`, `compose.yaml`, `.dockerignore`, and `docker/env.template`. Inside the container the service listens on port 8000; the host port defaults to 8771 (verified returning HTTP 200).

1. First prepare two **already-existing** host directories (a data directory and a backup directory; Compose never creates them silently).
2. Copy the template and fill in real values (private values go only into `.env.local`, which never enters Git):

```bash
cp docker/env.template docker/.env.local
# Fill PROJECT_SLUG / COMPOSE_PROJECT_NAME / APP_PORT / PUBLIC_APP_URL
#     APP_DATA_DIR / APP_BACKUP_DIR / IMAGE_TAG
```

3. Build and start (the four-piece set shipped in D11; the container health check runs every 30s):

```bash
docker compose --env-file docker/.env.local up -d
```

4. Open `http://127.0.0.1:<APP_PORT>/` (default `8771`).

The ledger inside the container is always written to `/data/ledger.db` and the quote cache to `/data/quotes.json`, both inside the data directory and fully isolated from the local `./dev.db`; the backup directory is mounted read-only at `/backups`.

## Formal maintenance

See:

- `更新日历与数据口径.md` (update calendar and data methods)
- `智能体更新提示词.md` (agent update prompts)
- `数据源与维护清单.json` (data source and maintenance checklist)

## Notes

- This tool is for reproducing the course method, verifying data, and estimating capital. It is not investment advice.
- Indices are reconstituted periodically and may also change ad hoc due to delisting, mergers, spin-offs, or ST/*ST designations (China's special-treatment warning labels); do not update them mechanically once a year only.
- "Current PE/PB/dividend yield" and their "percentiles" are different dimensions; percentiles especially depend on the calculation method. Course-template values must not be directly overwritten by third-party values computed differently.
