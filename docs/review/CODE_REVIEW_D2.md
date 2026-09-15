# CODE REVIEW

- Task: D2（四生命周期＋冻结/revision＋数学不变量，P0#6#7）
- Commit: N/A（工作区非 git 仓库；审查对象为工作区现状 db/service.py、db/repository.py、db/api.py、scripts/ledger_smoke_test.py D2 段；builder 自测 121/121 EXIT=0 未独立重跑，仅 py_compile 通过）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 过（P0=0；下述 P1×2、P2/P3×3 均为后续改进，不阻塞 D2 关闭；改法已精确到函数）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- [P0] 本轮 P0 无。重点判 7 项逐条结论：
  1. 追加低配优先：过。`_buy_only_rows` 按 `gap=target-current` 降序贪心、整手、`remaining` 扣减，只买不卖；`_allocate_by_weight` 最大余数法（`floors+按余数/权重排序补 remainder`）保证 `sum(targets)==portfolio_total`（service.py:188-201,481-510）。D2.9-D2.12 夹具（超配 600111 0 股、无 SELL 行、乙先补足）与算法一致，接受。
  2. SELL 只计划不执行：过。`preview_batch/_build_plan/freeze_batch/revise_batch/_rebalance_rows/_exit_rows` 全程只写 `batches/order_items`，无任何 `transactions/cash_ledger` 写入（service.py:363-639）；D2.16/D2.18 断言预览/计划后交易数不变。`revise_batch` 同样不写 transactions（仅 `batches.freeze+_insert_plan_items`）。
  3. 已确认项 revise 不改写：过。`revise_batch` 只 `INSERT` 新 revision 的 order_items，不 `UPDATE` 旧 revision 行；旧 revision 全保留，`preserved_confirmed_items` 仅读取（service.py:611-638）；D2.30-D2.31 覆盖。
  4. close 非空拒绝＋CLOSED 后拒绝：过。`close_cycle` 非空持仓 409、已 CLOSED 重复关 409（service.py:666-687）；`create_batch/freeze_batch/revise_batch` 均在同一写事务内查 `cycle status != OPEN → 409`（service.py:303-321,588-609,611-638）；D2.19/D2.23/D2.33/D2.H9 覆盖。
  5. 缺行情拒绝不补造数：过。`universe=成分∪持仓` 全量要求 quotes 命中，缺任一即 400（service.py:389-396）；D2.32/D2.H2 覆盖。
  6. cycle_summary 持仓重建来源：过。`cycle_summary/holdings` 均走 `TransactionRepository.holdings → v_holdings(confirmed transactions)`，并以 `holdings_rebuild_source/rebuild_source` 明示（service.py:640-664,789-801；repository.py:212-222）。
  7. D1 旧断言未被改坏：过。`record_transaction/append_cash/holdings` 确认语义、整手、禁裸空、现金符号、幂等、不可变触发器依赖均未动；`_assert_plan_invariants` 行/总额双校验保留且 `preview/freeze/revise` 全路径调用（service.py:204-219,459）；`db/api.py` 旧路由未改名，`/api/holdings` 旧语义回归由 6.2-6.9 覆盖；仅 py_compile 验证，未独立重跑 121 项。
- [P1-1] CLOSED 周期仍可经 `record_transaction/append_cash/create_order_item` 写入（service.py:334-361,699-787,821-858）。`record_transaction` 仅校验 `cycles.exists` 未校验 `status`；`append_cash` 同；`create_order_item` 只查 batch 存在不查所属 cycle 状态。已关闭周期追加交易/现金会污染“关闭后历史不变”语义。改法：`record_transaction` 与 `append_cash` 在 `write_tx` 内 `get/exists` 后加 `if cycle["status"] != "OPEN": raise LedgerError("cycle 已关闭…", status=409)`（需把 `exists` 改为 `get` 或新增取行）；`create_order_item` 在取到 batch 后追查其 cycle 并同样 409。不动其它逻辑，QA 加一条“close 后 record/append/create_order_item 均为 409”用例。
- [P1-2] `revise_batch` 允许用 payload 改写 kind/cycle_id（service.py:626-627 `setdefault` 不覆盖显式传值）。调用方可把 INITIAL 批次 revise 成 EXIT 计划，或用异 cycle 行情/持仓算出 plan 冻进原 batch，造成 `batches.kind` 与 `plan_json.kind` 不一致、持仓来源错乱。改法：`revise_batch` 内删除两行 `setdefault`，改为强制 `payload["cycle_id"]=batch["cycle_id"]; payload["kind"]=batch["kind"]`（或显式传入且不一致即 400），再调 `_build_plan`。QA 加“revise 传异 kind/cycle_id 被强制或 400”用例。

## P2 / P3 Backlog Findings

- [P2-1] `_rebalance_rows` 直接跳过不足一手/零缺口标的（`qty<=0: continue`，service.py:512-535），`target_total/actual_total` 只是“有动作行之和”而非全组合总额，小额偏离不可见。建议：保留补零行（qty=0、note 说明不足一手）或在 totals/warnings 中披露被跳过标的数量与金额；不变量本身成立，不阻塞。
- [P2-2] EXIT 计划 `leftover_cents=investable-actual_total` 在 SELL 金额为负时恒为正（service.py:446-454），语义无意义易误读。建议：EXIT 时 `leftover_cents=0` 或改名为预计回款额；纯展示问题。
- [P3-1] `BatchRepository.set_status/max_revision` 无 service/API 出口（死代码，repository.py:96-131，api.py 无对应路由）；`CycleRepository.close` 无 `WHERE status='OPEN'` 原子守卫（当前靠 service 事务内先查后写，单写者下成立）。建议：要么删除/接线 `set_status`，要么注明保留原因；`close` 加 `WHERE status='OPEN'` 并按 affected-rows 判 409。均为可回滚清理项。
