# Dividend & IPO Base Position Calculator

How expensive the six dividend indices are today, how much base position to build, and whether to buy or sell next—all worked out in a panel that runs only in your own home.

[简体中文](./README.md)

## What it is

A single-host personal dividend base-position tool. It links "read valuations → set a plan → place orders manually on the phone → return and reconcile" into one loop, but it **only plans, records, and reconciles. It never auto-trades and never decides what to buy for you.**

Market data uses public quotes and official index materials, with a Tencent → Eastmoney → local-cache fallback chain; unavailable values are shown as NA rather than invented.

## What it does

- **Six dividend index dashboards**: index level, dividend yield, valuation percentile, and a ten-year series; gaps appear as NA instead of guesses.
- **Official constituents and weights**: cached official members and weights as a stock-selection reference.
- **Base-position sizing**: for budgets such as 100k or 200k, compute suggested share counts (A-shares in 100-share lots).
- **Build / add / rebalance / exit plans**: produce a freezable order plan that quote refreshes cannot silently change once frozen.
- **Phone-assisted ordering**: turn the plan into a checklist you can follow on your brokerage app, then log fills back into the panel.
- **Real holdings and strategy cash ledger**: record fill price, quantity, and cash movement, separating strategy capital from external capital.
- **Unfinished batch recovery**: continue an interrupted order batch instead of starting over.
- **Excel export**: export the current plan and holdings for independent checking.
- **Self-hosted with Docker**: data in local SQLite, with a read-only backup mount.

## Run it

### Docker (recommended)

```bash
# Both host directories must exist beforehand; missing values fail fast rather than creating silently
APP_DATA_DIR=/path/to/data \
APP_BACKUP_DIR=/path/to/backups \
PUBLIC_APP_URL=http://127.0.0.1:8771 \
docker compose up -d --build
open http://127.0.0.1:8771/
```

### Run locally

```bash
python3 server.py --port 8771     # standard library only, no extra dependencies
```

For first use, follow the "first launch" section of `docs/pm/PRODUCT_PLAN_V1.0.md` to confirm the data directory, project slug, and backup path.

## Data and privacy

- Holdings, plans, and fills live in local SQLite only; no broker connection and no account data upload.
- The repository's `dev.db` is a development sample; real data and backup directories must never be committed.
- Quotes and index materials come from public endpoints; when an endpoint fails the UI shows NA and existing records stay intact.

## Known limitations

- No auto-trading and no broker API; fills must be completed in your brokerage app and recorded back.
- Some indices lack a legitimate same-basis history, so the panel shows NA—that is data reality, not a defect.
- The first version excludes fees, corporate actions, partial fills, and cancellations.

## Layout

```text
index.html        # dashboard page
server.py         # local HTTP server (stdlib)
db/               # SQLite ledger and API
docker/           # deployment scripts
docs/             # product plan, reviews, data conventions, handoff, governance
```

See `更新日历与数据口径.md` for data conventions and refresh cadence, and `docs/pm/PRODUCT_PLAN_V1.0.md` for scope.
