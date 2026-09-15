
# CODE REVIEW

- Task: D1
- Commit: n/a（本工作区无 git 仓库，无 commit 可引）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 打回（P0 真 bug 1 条必改；P1 测试脚本 2 条随同改；改法见下。改完重跑 scripts/ledger_smoke_test.py 至 76/76 后再送 QA）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- [P0] GET 查询串整数参数被 service 拒绝（对应 FAIL 6.18/6.19，真 bug，必改）。根因：`db/api.py::_get` 把 URL 查询串原文（`str`，如 `"1"`）直接传给 `LedgerService.holdings/list_cash/list_batches/list_order_items/list_transactions`，而 `db/service.py::_int_value` 要求 `isinstance(value, int)`，字符串一律抛 `LedgerError("字段 cycle_id 必须是整数")` → GET holdings/cash 带 `?cycle_id=` 必 400。已实测复现：`holdings(str(cid))` 与 `list_cash(str(cid))` 均抛该错，`holdings(int)` 正常。同文件同类潜伏：`list_batches(query.get("cycle_id"))`（`db/api.py:85`）、`list_order_items(query.get("batch_id"))`（`:87`）、`list_transactions(query.get("cycle_id"), ...)`（`:92-93`）同样传 `str`，带参查询必 400。改法（二选一，精确到函数）：① 在 `db/service.py::_int_value` 开头加字符串兼容：`if isinstance(value, str): s=value.strip(); if re.fullmatch(r"[+-]?\d+", s): value=int(s)`（`re` 已 import；注意先排除 `bool`，`None`/空串保持原 `required` 语义；`minimum/maximum` 校验保留）；或 ② 在 `db/api.py` 加 `_qint(v)` helper（`None`→`None`，纯数字串→`int`，非法→原样透传让 service 报 400），并在 `_get` 的 `batches/order-items/transactions/holdings/cash` 五处调用。修后重跑 6.18/6.19 及带参 `batches?cycle_id=`、`order-items?batch_id=`、`transactions?cycle_id=` 验收。
- [P1] FAIL 1.11 schema 指纹不一致是测试 artifact，非产品 bug（`scripts/ledger_smoke_test.py:58-67` + `db/migrate.py:34-40`）。实测：迁移库与 schema.sql 建库的 `sqlite_master` 键集合完全一致（19 个对象全对齐），唯一差异是 `table:schema_migrations` 建表语句空白：`... NOT NULL)`（runner 内 `REGISTRY_DDL` 无空格）vs `... NOT NULL )`（0001/schema.sql 换行归一化出空格）。语义等价。改法（只改测试，不动产品）：在 `fingerprint()` 归一化里再加一句括号空白归一（如 `re.sub(r"\s*([(),;])\s*", r"\1", norm)`，或直接去掉全部空白后比较），或从指纹中排除 `schema_migrations`（版本语义由 1.2/1.10 覆盖）。可选根治：统一 `REGISTRY_DDL` 文本与 0001/schema.sql 完全一致。
- [P1] FAIL 5.3 `.backup` 副本 WAL 残留是测试断言过严，非 `sqlite.md` 单文件边界违反（`scripts/ledger_smoke_test.py:389-399`）。产品侧合规：备份用 `.backup`/stdlib `backup API` + `VACUUM INTO`（`sqlite.md` §11 正解），未用裸 `cp` 活库。`-wal`/`-shm` 是测试自己用 `sqlite3.connect(path)` 打开备份副本做 `integrity_check`/`counts` 后、WAL 模式下残留的预期行为（读连接也会建 `-shm`；`close` 后未 checkpoint 即断言“无残留”必挂）。5.4 VACUUM 副本通过也佐证这是副本打开方式问题而非备份损坏。改法（只改测试）：断言前加 `PRAGMA wal_checkpoint(TRUNCATE); close()` 后再查；或把“无 WAL 残留”断言改为仅针对“刚备份、尚未打开验证前”的副本；`integrity=ok / fk=0 / 行数一致` 保留为主断言。

一致性核验（均通过，非 finding）：confirmed 语义（`service.record_transaction:265` 非 `True` 即 400，`repository.create:147` 硬写 `confirmed=1`，与计划“只有人工核实已成交/已卖出成交才写账本、部分成交/撤单拒绝”一致；Human Decision ④⑤落实：`price_cents/amount_cents` 至少其一、`amount=price×qty` 校验、`reference_price_cents` 保留）；不可变触发器 4 个齐全（已确认不可 UPDATE、transactions 不可 DELETE、cash_ledger 不可 UPDATE/DELETE，与 P0#7 一致）；追加账本（现金 `SUM` 聚合、`v_holdings/v_cash_balance` 重建，`avg_cost_cents` 派生）；幂等（`idempotency_key UNIQUE` + 重放短路，2.8 语义）；整手 100（`LOT_SIZE`，`qty/suggested_qty` 取模）；裸空拒绝（`holding_qty` + 409，且 check+insert 同一 `write_tx(BEGIN IMMEDIATE)` 串行化）；`.db`/静态暴露防护有效（`server.py:252-254` 拦 `db/var` 前缀 + `.db/.sqlite/.sqlite3/-wal/-shm` 后缀 + 越界 `relative_to`，6.10/6.11 逻辑成立）；旧 API 零回归（`server.py:185-206` 旧路由原地不动，ledger 分支后置且仅 `handles("/api/ledger...")`，旧 `/api/holdings` 指数权重语义 untouched，`api.py:4-6` 命名注释与之一致）；`.gitignore` 覆盖 `*.db/*.db-wal/*.db-shm/*.sqlite/*.sqlite3/var/DockerData/DockerBackups`，正式库 `guard_path`（`connection.py:54-61`）有效。

## P2 / P3 Backlog Findings

- [P2] 幂等并发竞态：`record_transaction/append_cash` 先 `find_by_idempotency_key` 再 `INSERT`，并发同键后者拿 `IntegrityError`→API 转 409 而非重放。单人低写场景可接受；后续可在 `api.py:68-69` 捕获 `idempotency_key` 唯一冲突后重读返回重放体。
- [P2] 触发器仅守 `OLD.confirmed=1` 的 UPDATE：service 永不产生 `confirmed=0` 行，仅直连 SQL 插入未确认行才可被改。D1 写入只走 service，可接受；后续可加 `CHECK(confirmed=1)` 或扩展触发器收口直写面。
- [P2] `holdings.avg_cost_cents` 在 `qty<=0` 时为 `None`/符号异常：service 拦裸空后正常路径 `qty>0`；仅直连 SQL 破坏才触发。展示层按 `None`→`NA` 处理即可。
- [P3] 路径口径小差异：`sqlite.md` §5 建议开发库 `var/dev.db`，而 `connection.py:19` 默认根 `dev.db`（均被 `.gitignore` 覆盖，无泄漏风险）。D1 不改；后续统一文档或默认路径时另立任务。

## 复验（2026-09-15）
- P0 `_int_value` 字符串兼容：落实（`db/service.py:64-81`，bool 先排、`str.strip()+fullmatch(r"[+-]?\d+")` 转 int、`None`/required 与 min/max 保留，与打回方案①一致）。
- P1 fingerprint 空白归一：落实（`scripts/ledger_smoke_test.py:67` 增加 `re.sub(r"\s*([(),;])\s*",r"\1",norm)`）。
- P1 5.3 断言前移：形式落实（`scripts/ledger_smoke_test.py:391-394` WAL 断言在 `connect` 之前，符合“仅针对尚未打开验证前副本”路径；未加 `wal_checkpoint(TRUNCATE)`，按所选路径不必需）。
- 新增 6.19a/b/c：存在（`:519/:528/:533`，分别覆盖 batches?cycle_id、order-items?batch_id、transactions?cycle_id 查询串）。
- 无计划外改动抽查：`server.py:250 relative_to` 防护、`connection.py:54 guard_path`、触发器 `OLD.confirmed=1`、`confirmed=1` 硬写、`.gitignore`（db-wal/shm、var/、DockerData/Backups）均在；无 `_qint` 第二路径污染。
- 结论：过（builder 称 smoke 79/79 EXIT=0，本轮未独立重跑，以代码静态复验为准）。
