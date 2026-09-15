-- 0001_init.sql | 红利打新底仓计算器 V1.3 / D1 SQLite 账本骨架
-- 已发布 Migration 不回改；结构变更一律新增 migration。
--
-- 全库约定（与 PRODUCT_PLAN_V1.0 一致）：
--   1. 时间统一 ISO8601 文本，本机时区 +08:00（如 2026-09-15T20:00:00+08:00）。
--   2. 金额统一整数“分”（cents），不落浮点；股数为整数。
--   3. confirmed 仅代表“用户人工核实已成交 / 已卖出成交”，不代表已下单、已报单。
--      部分成交、撤单首版拒绝写入（另立 Change C）。
--   4. 持仓由 confirmed transactions 聚合重建（见视图 v_holdings），不落冗余持仓表。
--   5. 策略现金为追加式事件账本（cash_ledger），只允许 INSERT，禁止 UPDATE / DELETE。
--   6. 交易与现金为“事实”数据，禁止删除；纠错用反向事件，不用改写历史。
--   7. 普通 A 股按 100 股整手（qty % 100 = 0）。
--   8. 首版不计佣金、税费、分红、公司行动。

-- ---------------------------------------------------------------- 版本表
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  name       TEXT    NOT NULL,
  applied_at TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 投资周期
-- 一次投资周期 = 一个 cycle；清仓结束后 CLOSED，新一轮另建 cycle。
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
-- 一个 cycle 可有多个 batch（首次建仓/追加/再平衡/清仓）。
-- plan_json / revision / frozen_at 为 P0#7 冻结与 revision 预留列，D1 只建结构。
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
-- 计划数据：可由计划重算生成新 revision；真实成交只认 transactions。
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
-- 只有 confirmed=1 的记录进入持仓重建；已确认记录不可改写、不可删除。
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
-- 追加式事件账本：余额 = SUM(amount_cents)；amount_cents 为带符号金额（买出为负、卖出为正）。
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

-- ---------------------------------------------------------------- 索引
CREATE INDEX IF NOT EXISTS idx_batches_cycle          ON batches(cycle_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_order_items_batch      ON order_items(batch_id, order_item_id);
CREATE INDEX IF NOT EXISTS idx_order_items_code       ON order_items(code);
CREATE INDEX IF NOT EXISTS idx_transactions_cycle     ON transactions(cycle_id, transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_cycle_code ON transactions(cycle_id, code);
CREATE INDEX IF NOT EXISTS idx_transactions_batch     ON transactions(batch_id);
CREATE INDEX IF NOT EXISTS idx_cash_ledger_cycle      ON cash_ledger(cycle_id, cash_event_id);

-- ---------------------------------------------------------------- 重建视图
-- 持仓 = SUM(confirmed BUY) - SUM(confirmed SELL)，可随时重建，不落冗余表。
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

-- 现金余额：纯聚合，不存不可追溯的“当前余额”。
CREATE VIEW IF NOT EXISTS v_cash_balance AS
SELECT cycle_id, SUM(amount_cents) AS balance_cents, COUNT(*) AS event_count
FROM cash_ledger
GROUP BY cycle_id;

-- ---------------------------------------------------------------- 不可变护栏
-- 已确认交易不可改写（P0#7 不可变确认的结构级兜底）。
CREATE TRIGGER IF NOT EXISTS trg_transactions_confirmed_immutable
BEFORE UPDATE ON transactions
FOR EACH ROW WHEN OLD.confirmed = 1
BEGIN
  SELECT RAISE(ABORT, 'confirmed transaction is immutable');
END;

-- 事实数据不可删除（纠错走反向事件）。
CREATE TRIGGER IF NOT EXISTS trg_transactions_no_delete
BEFORE DELETE ON transactions
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
BEGIN
  SELECT RAISE(ABORT, 'cash_ledger is append-only');
END;
