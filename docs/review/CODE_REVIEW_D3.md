
# CODE REVIEW

- Task: D3（下单执行页＋四态/门禁＋进度恢复＋D2 P1×2修复，P0#8#9）
- Commit: N/A（工作区非 git 仓库；审查对象为工作区现状 db/service.py D3段、db/api.py、index.html“六、下单执行”区块＋D3增量脚本、scripts/ledger_smoke_test.py D3段；builder 自测 146/146 EXIT=0 未独立重跑，仅读码＋行号取证）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 过（P0=0；下述 P1×1 为测试补强非阻塞，P2/P3×3 为 backlog；改法已精确到函数）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- [P0] 本轮 P0 无。8 项重点判逐条结论：
  1. P1-1 三写 409 真落实（含 state 关周期）：过。`record_transaction` 写事务内 `cycle["status"] != "OPEN" → 409`（service.py:848-849）；`append_cash` 同式 409（service.py:951-952）；`create_order_item` 取 batch 追查其 cycle 非 OPEN → 409（service.py:359-363）；`set_order_item_state` 同式 409（service.py:397-398）。smoke D3.1/D3.2/D3.3/D3.3a 四条覆盖。
  2. P1-2 revise 异 kind/cycle 400/强制：过。`revise_batch` 内显式传异 cycle_id → 400（service.py:718-722）、异 kind → 400（service.py:723-726），随后强制 `payload["cycle_id"]=batch["cycle_id"]; payload["kind"]=batch["kind"]` 再 `_build_plan`（service.py:727-729）。D2 的 `setdefault` 可改写口已删除。smoke D3.4/D3.5/D3.6 覆盖。
  3. 四态机（CONFIRMED 只联动、不可逆转、非最新 revision 拒绝）：过。state 接口 `target == CONFIRMED → 409`（service.py:381-383）；已 CONFIRMED 行再流转 → 409（service.py:399-400）；非最新 revision 行 → 409（service.py:401-402，以 `items.max_revision(batch_id)` 判定，repository.py:127）；唯一 CONFIRMED 入口为 `record_transaction` 内 `items.set_status(order_item_id, "CONFIRMED")`（service.py:882-883）。smoke D3.11/D3.12/D3.14 覆盖联动与不可逆转。
  4. 完成门禁 done 条件与计划一致：过。`batch_progress` 按最新 revision 统计：`total==0 → blocked`、`review>0 → blocked`、`pending>0 → progressing`，否则 `done`（service.py:426-433），即 done ⟺ 全部 CONFIRMED/SKIPPED，与计划“全部处理为已确认成交/已跳过才通过”一致；`can_complete = gate == "done"`（service.py:448）。smoke D3.7/D3.9/D3.15 覆盖三态。
  5. 刷新恢复走服务端真相：过。`batch_progress` 每次直读库（无缓存，service.py:408-453）；前端 `dpLoadProgress/dpInit` 经 `GET /api/ledger/batches/:id/progress` 恢复（index.html:345-350,389-396），`dpLoadBatches` 默认定位首个非 done 批次（index.html:336-340）。smoke D3.17（新实例一致）与 D3.H6（服务重启前后一致）覆盖。
  6. 前端确认走 record_transaction＋幂等键防重：过。`dpConfirmItem` 经 `POST /api/ledger/transactions`（`confirmed:true`，`idempotency_key:'order-item:'+order_item_id`），有二次确认框、建议股数>0 与参考价守卫、`dpBusy` 防连点、重放提示（index.html:305-318）。后端重复确认（无键）→ 409（service.py:868-870，smoke D3.13）。
  7. V1.2 既有区块零改动：过。一～五区块、首屏 `xlsx.full.min.js`（index.html:3）、`initSelect`（index.html:120）、V1.2 `DOMContentLoaded` 接线（index.html:221）均在；D3 仅新增“六、下单执行”区块（index.html:62-103）与独立增量 `<script>`（index.html:223-413）；`server.py` 旧路由未动，仅委托 `/api/ledger/*` 给 `db.api`；smoke 6.x/D2 旧断言保留。
  8. D2 回归未被改坏：过。`_build_plan/_insert_plan_items/preview/freeze/revise`（service.py:456-739）与 D2 审查时一致，仅 revise 首部加 P1-2 守卫；`record_transaction/append_cash` 仅加关周期守卫，其余语义（整手/禁裸空/幂等/现金联动）未动。
- [P1] 非最新 revision 拒绝有代码无 smoke 用例（非阻塞，测试补强）。`set_order_item_state` 的 `revision != max_revision → 409`（service.py:401-402）无对应 smoke 断言（D3 段仅覆盖 CONFIRMED/重复确认/关周期）。改法：`test_d3_flow` 内 revise 后加一条——取 `list_order_items(batch, revision=1)` 旧行调 `set_order_item_state(old_id, {"status":"SKIPPED"})`，断言 `LedgerError.status == 409`；不碰业务代码。

## P2 / P3 Backlog Findings

- [P2-1] 幂等重放先于重复确认 409（设计使然，建议补断言）。`record_transaction` 内 `idempotency_key` 重放返回在 CONFIRMED-409 检查之前（service.py:863-870），故前端同一键 double-confirm 得 200 `idempotent_replay` 而非 409——防重写目标已达成（不产生第二笔 tx），前端亦有对应提示。建议：smoke 加一条“同幂等键二次确认返回 `idempotent_replay is True` 且交易数不变”；纯测试补强。
- [P2-2] `dpLoadBatches` 逐批次 N+1 进度 GET（index.html:336-340）。本地单用户规模可接受；批次多了首屏恢复变慢。建议：后续加 `GET /api/ledger/batches?cycle_id=` 附带各批次门禁摘要，或前端并发请求；可回滚优化项。
- [P3-1] D2 遗留 backlog 转结（D3 未动相关代码，未复验）：D2 P2-1（rebalance 跳过行不可见）、P2-2（EXIT leftover 语义）、P3-1（`set_status/max_revision` 接线与 `close` 原子守卫）。建议：后续版本按 D2 改法处理；不阻塞 D3 关闭。
