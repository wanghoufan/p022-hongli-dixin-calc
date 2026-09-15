-- schema.sql | 红利打新底仓计算器 V1.3 / D1 SQLite 结构快照
--
-- 用途：人类阅读 + 结构对照 + 空库快速建表（可进 Git）。
-- 权威来源：db/migrations/*.sql（已发布 Migration 不回改，新结构新增 Migration）。
-- 本文件必须与 migrations 应用后的结构等价；等价性由 scripts/ledger_smoke_test.py 校验。
-- 结构与口径约定见 db/migrations/0001_init.sql 头部说明。

PRAGMA user_version = 3;

-- ---------------------------------------------------------------- 版本表
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  name       TEXT    NOT NULL,
  applied_at TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 投资周期
CREATE TABLE IF NOT EXISTS cycles (
  cycle_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL DEFAULT '',
  status     TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  note       TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL,
  updated_at TEXT    NOT NULL,
  closed_at  TEXT
);

-- ---------------------------------------------------------------- 下单批次
CREATE TABLE IF NOT EXISTS batches (
  batch_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id          INTEGER NOT NULL REFERENCES cycles(cycle_id) ON DELETE CASCADE,
  kind              TEXT    NOT NULL CHECK (kind IN ('INITIAL','ADD','REBALANCE','EXIT')),
  status            TEXT    NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT','FROZEN','IN_PROGRESS','DONE','CANCELLED')),
  revision          INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  algorithm_version TEXT    NOT NULL DEFAULT '',
  plan_json         TEXT,
  frozen_at         TEXT,
  note              TEXT    NOT NULL DEFAULT '',
  created_at        TEXT    NOT NULL,
  updated_at        TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 逐只清单
CREATE TABLE IF NOT EXISTS order_items (
  order_item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id              INTEGER NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
  code                  TEXT    NOT NULL CHECK (code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'),
  name                  TEXT    NOT NULL DEFAULT '',
  market                TEXT    NOT NULL DEFAULT '' CHECK (market IN ('','SH','SZ')),
  side                  TEXT    NOT NULL CHECK (side IN ('BUY','SELL')),
  target_weight         REAL,
  reference_price_cents INTEGER CHECK (reference_price_cents IS NULL OR reference_price_cents > 0),
  suggested_qty         INTEGER NOT NULL DEFAULT 0 CHECK (suggested_qty >= 0 AND suggested_qty % 100 = 0),
  status                TEXT    NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING','CONFIRMED','SKIPPED','REVIEW')),
  revision              INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  note                  TEXT    NOT NULL DEFAULT '',
  created_at            TEXT    NOT NULL,
  updated_at            TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 交易账本
CREATE TABLE IF NOT EXISTS transactions (
  transaction_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id              INTEGER NOT NULL REFERENCES cycles(cycle_id) ON DELETE RESTRICT,
  batch_id              INTEGER REFERENCES batches(batch_id) ON DELETE SET NULL,
  order_item_id         INTEGER REFERENCES order_items(order_item_id) ON DELETE SET NULL,
  code                  TEXT    NOT NULL CHECK (code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'),
  name                  TEXT    NOT NULL DEFAULT '',
  side                  TEXT    NOT NULL CHECK (side IN ('BUY','SELL')),
  qty                   INTEGER NOT NULL CHECK (qty > 0 AND qty % 100 = 0),
  price_cents           INTEGER CHECK (price_cents IS NULL OR price_cents > 0),
  reference_price_cents INTEGER CHECK (reference_price_cents IS NULL OR reference_price_cents > 0),
  amount_cents          INTEGER NOT NULL CHECK (amount_cents > 0),
  confirmed             INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0,1)),
  confirmed_at          TEXT,
  source                TEXT    NOT NULL DEFAULT 'MANUAL_CONFIRM',
  note                  TEXT    NOT NULL DEFAULT '',
  idempotency_key       TEXT    UNIQUE,
  created_at            TEXT    NOT NULL,
  updated_at            TEXT    NOT NULL,
  CHECK (confirmed = 0 OR confirmed_at IS NOT NULL)
);

-- ---------------------------------------------------------------- 策略现金
CREATE TABLE IF NOT EXISTS cash_ledger (
  cash_event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id        INTEGER NOT NULL REFERENCES cycles(cycle_id) ON DELETE RESTRICT,
  transaction_id  INTEGER REFERENCES transactions(transaction_id) ON DELETE RESTRICT,
  event_type      TEXT    NOT NULL
                          CHECK (event_type IN ('OPENING','DEPOSIT','WITHDRAW','BUY','SELL','ADJUSTMENT')),
  amount_cents    INTEGER NOT NULL CHECK (amount_cents <> 0),
  note            TEXT    NOT NULL DEFAULT '',
  occurred_at     TEXT    NOT NULL,
  idempotency_key TEXT    UNIQUE,
  created_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 审计日志（0002）
-- D7「删除测试批次」的审计事件（谁、何时、删了哪些行数）。
CREATE TABLE IF NOT EXISTS ledger_audit (
  audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  action     TEXT    NOT NULL,
  entity     TEXT    NOT NULL,
  entity_id  INTEGER,
  detail     TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL
);

-- 删除授权/留痕（0002；无外键，批次删除后仍保留事实）。
CREATE TABLE IF NOT EXISTS ledger_batch_deletions (
  batch_id        INTEGER PRIMARY KEY,
  cycle_id        INTEGER,
  confirmed_count INTEGER NOT NULL DEFAULT 0,
  detail          TEXT    NOT NULL DEFAULT '',
  deleted_at      TEXT    NOT NULL
);

-- 撤销授权（0003；transaction_ids 存 ',1,2,' 形式供触发器 instr 精确匹配单笔）。
CREATE TABLE IF NOT EXISTS ledger_reverts (
  revert_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  order_item_id   INTEGER,
  cycle_id        INTEGER,
  batch_id        INTEGER,
  transaction_ids TEXT    NOT NULL DEFAULT '',
  detail          TEXT    NOT NULL DEFAULT '',
  created_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 索引
CREATE INDEX IF NOT EXISTS idx_batches_cycle          ON batches(cycle_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_order_items_batch      ON order_items(batch_id, order_item_id);
CREATE INDEX IF NOT EXISTS idx_order_items_code       ON order_items(code);
CREATE INDEX IF NOT EXISTS idx_transactions_cycle     ON transactions(cycle_id, transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_cycle_code ON transactions(cycle_id, code);
CREATE INDEX IF NOT EXISTS idx_transactions_batch     ON transactions(batch_id);
CREATE INDEX IF NOT EXISTS idx_cash_ledger_cycle      ON cash_ledger(cycle_id, cash_event_id);

-- ---------------------------------------------------------------- 重建视图
CREATE VIEW IF NOT EXISTS v_holdings AS
SELECT
  cycle_id,
  code,
  MAX(name) AS name,
  SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END)               AS qty,
  SUM(CASE WHEN side = 'BUY' THEN amount_cents ELSE -amount_cents END) AS net_cost_cents,
  SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END)                    AS buy_count,
  SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END)                   AS sell_count
FROM transactions
WHERE confirmed = 1
GROUP BY cycle_id, code;

CREATE VIEW IF NOT EXISTS v_cash_balance AS
SELECT cycle_id, SUM(amount_cents) AS balance_cents, COUNT(*) AS event_count
FROM cash_ledger
GROUP BY cycle_id;

-- ---------------------------------------------------------------- 不可变护栏
CREATE TRIGGER IF NOT EXISTS trg_transactions_confirmed_immutable
BEFORE UPDATE ON transactions
FOR EACH ROW WHEN OLD.confirmed = 1
BEGIN
  SELECT RAISE(ABORT, 'confirmed transaction is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_transactions_no_delete
BEFORE DELETE ON transactions
FOR EACH ROW WHEN NOT EXISTS (
  SELECT 1 FROM ledger_batch_deletions d WHERE d.batch_id = OLD.batch_id
) AND NOT EXISTS (
  SELECT 1 FROM ledger_reverts r
  WHERE instr(r.transaction_ids, ',' || OLD.transaction_id || ',') > 0
)
BEGIN
  SELECT RAISE(ABORT, 'transactions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_ledger_no_update
BEFORE UPDATE ON cash_ledger
BEGIN
  SELECT RAISE(ABORT, 'cash_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_ledger_no_delete
BEFORE DELETE ON cash_ledger
FOR EACH ROW WHEN NOT EXISTS (
  SELECT 1 FROM ledger_batch_deletions d
  JOIN transactions t ON t.batch_id = d.batch_id
  WHERE t.transaction_id = OLD.transaction_id
) AND NOT EXISTS (
  SELECT 1 FROM ledger_reverts r
  WHERE instr(r.transaction_ids, ',' || OLD.transaction_id || ',') > 0
)
BEGIN
  SELECT RAISE(ABORT, 'cash_ledger is append-only');
END;
