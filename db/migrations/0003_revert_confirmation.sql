-- 0003_revert_confirmation.sql — D8 单行撤销确认（用户 2026-09-16 明确要求已确认可撤销）
-- 已发布 Migration（0001/0002）一律不回改，本文件只新增。
-- 新增 ledger_reverts 撤销授权表（transaction_ids 存 ',1,2,' 形式，触发器用 instr 精确匹配单笔）；
-- 两条 no-delete 触发器 DROP 后重建，在原 ledger_batch_deletions 授权之外，
-- 再允许“已写撤销授权”的单行回退删除；未授权路径仍 ABORT（不可变护栏不变）。

CREATE TABLE IF NOT EXISTS ledger_reverts (
  revert_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  order_item_id   INTEGER,
  cycle_id        INTEGER,
  batch_id        INTEGER,
  transaction_ids TEXT    NOT NULL DEFAULT '',
  detail          TEXT    NOT NULL DEFAULT '',
  created_at      TEXT    NOT NULL
);

DROP TRIGGER IF EXISTS trg_transactions_no_delete;
CREATE TRIGGER trg_transactions_no_delete
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

DROP TRIGGER IF EXISTS trg_cash_ledger_no_delete;
CREATE TRIGGER trg_cash_ledger_no_delete
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

PRAGMA user_version = 3;
