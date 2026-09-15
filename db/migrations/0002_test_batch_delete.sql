-- 0002_test_batch_delete.sql | Change B（D7）：删除测试批次（整批，受控 + 可审计）
-- 已发布 Migration 不回改；本文件为新增 Migration。
--
-- 目的：
--   允许“删除测试批次”整批移除该批次的 order_items / transactions / cash_ledger，
--   同时**保留**常规 append-only 语义：未被显式授权删除的批次，其 transactions /
--   cash_ledger 仍不可 DELETE（0001 的结构级护栏不变，只是增加了一个受控例外）。
--
-- 机制：
--   1) ledger_batch_deletions 记录“已授权删除”的 batch_id（无外键：batch 删除后仍保留留痕）。
--   2) ledger_audit 记录审计事件（谁、何时、删了什么）。
--   3) 替换 0001 的两条 no-delete 触发器：仅当 OLD.batch_id（或现金事件关联交易所属
--      batch）已写入 ledger_batch_deletions 时，才允许删除。

-- ---------------------------------------------------------------- 审计日志
CREATE TABLE IF NOT EXISTS ledger_audit (
  audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  action     TEXT    NOT NULL,
  entity     TEXT    NOT NULL,
  entity_id  INTEGER,
  detail     TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 删除授权/留痕
-- 无外键：批次删除后仍需保留“哪一批被删过”的事实，供审计追溯。
CREATE TABLE IF NOT EXISTS ledger_batch_deletions (
  batch_id        INTEGER PRIMARY KEY,
  cycle_id        INTEGER,
  confirmed_count INTEGER NOT NULL DEFAULT 0,
  detail          TEXT    NOT NULL DEFAULT '',
  deleted_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 受控护栏（替换）
-- 事实数据默认不可删除（纠错走反向事件）；仅当该批次已被显式授权删除时放行。
DROP TRIGGER IF EXISTS trg_transactions_no_delete;
CREATE TRIGGER trg_transactions_no_delete
BEFORE DELETE ON transactions
FOR EACH ROW WHEN NOT EXISTS (
  SELECT 1 FROM ledger_batch_deletions d WHERE d.batch_id = OLD.batch_id
)
BEGIN
  SELECT RAISE(ABORT, 'transactions is append-only');
END;

DROP TRIGGER IF EXISTS trg_cash_ledger_no_delete;
CREATE TRIGGER trg_cash_ledger_no_delete
BEFORE DELETE ON cash_ledger
FOR EACH ROW WHEN NOT EXISTS (
  SELECT 1 FROM ledger_batch_deletions d
  JOIN transactions t ON t.batch_id = d.batch_id
  WHERE t.transaction_id = OLD.transaction_id
)
BEGIN
  SELECT RAISE(ABORT, 'cash_ledger is append-only');
END;
