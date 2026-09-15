
# CODE REVIEW

- Task: D8（单行撤销已确认成交＋标签换行修复）
- Commit: 工作树（非 git 仓库；基线 PRODUCT_PLAN_V1.0，HANDOFF DEVELOP-D8）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 过（P0=0；下述 P2/P3 仅 backlog，不阻断）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- 无（P0=0，P1=0）。逐项结论：
- ① 撤销受控：`db/service.py:revert_confirmation` 仅 CONFIRMED 可撤（400，含状态名）、CLOSED 拒绝（409）、`confirm_text == REVERT_CONFIRM_TEXT（"撤销确认"）` 否则 400；顺序为先 `authorize_revert` 写 `ledger_reverts` 单笔授权 → `delete_by_tx_ids` 删现金 → `delete_by_ids` 删成交 → 行回 PENDING → `ledger_audit(REVERT_CONFIRM)`，全程同一 `write_tx` 单写事务，异常整体回滚。符合“先授权再删事实＋审计”。
- ② 未授权护栏仍成立：`0003_revert_confirmation.sql` / `schema.sql:167-197` 两条 no-delete 触发器为原 `ledger_batch_deletions` 授权 `AND` 新增 `ledger_reverts` 的 `instr(transaction_ids, ','||OLD.transaction_id||',')` 单笔放行；逗号包裹避免 `1` 误配 `11`。smoke `2.17-2.20` 直接 SQL UPDATE/DELETE 仍断言 `immutable/append-only` ABORT，未被删除或放宽；旧 revision/他人批次行无对应授权仍 ABORT。
- ③ 只删本行：`list_by_order_item(order_item_id)` 取本行联动 `tx_ids` → `delete_by_tx_ids/delete_by_ids` 按 `transaction_id IN (...)` 删除，不带 `batch_id` 整批条件，不碰其他行/其他批次；`order_item_id IS NULL` 的事实成交不受影响（正确保留）。
- ④ 重建归零：持仓/现金均由 `v_holdings(confirmed)/SUM(cash_ledger)` 重建（`service.py:holdings/list_cash/cycle_summary`），撤销删掉该行唯一的成交＋自动现金事件后归零；smoke `D8.5/H3` 已断言 `holdings==[]` 且现金余额为 0。
- ⑤ 前端门禁：`index.html:376` 撤销按钮仅 `cur==='CONFIRMED'` 渲染；`dpRevertItem:428-431` 非 CONFIRMED 直接 return＋`window.prompt` typed“撤销确认”四字；单只模式 `412-414` CONFIRMED 行确认键变为“撤销确认”并走同一 `dpRevertItem`。后端仍做全量校验，前端仅为入口收敛。
- ⑥ `.vtag nowrap`：`index.html:19` `.vtag{...white-space:nowrap}` 标签内部不再劈半；标签仍为行内 span，随数值换行是预期行为，P0 诉求（标签字符被拦腰截断）已解决。
- ⑦ smoke 未被削弱：`1.1-1.3/1.7/1.9/1.11-1.12` 仅 `v2→v3` 版本递进（`ledger_reverts` 表＋触发器指纹等价仍断言，触发器数仍为 4）；`D4.P1/P2` 仅加“D7 起拆两表”限定，仍断言宽基表列顺序与三宽基＋六红利分区＋`valuationDivTable` 在位（延续 D7 结论）；D8 新增 `D8.1-D8.10/H0-H6/P1-P3` 均为正向增强断言，无旧断言删除。

## P2 / P3 Backlog Findings

- P2-1（test-strength，非代码缺陷）：`D8.P3` 仅断言 `"撤销确认" in html`，未断言单只模式按钮分支逻辑（`dpFocusConfirmBtn` 按 `CONFIRMED` 切文案/走 `dpRevertItem`）；建议后继收紧为特征串（如 `dpFocusConfirmBtn`＋`dpRevertItem(it.order_item_id)` 同段断言）。
- P2-2（UX 不一致）：单只模式 `index.html:415` `suggested_qty<=0` 时确认键 disabled，连 CONFIRMED 行的“撤销确认”也被禁用；列表视图撤销按钮无此限制。后继可将禁用条件改为仅非 CONFIRMED 行生效。
- P3-1（可维护性）：`revert_confirmation` 未像 `set_order_item_state` 那样校验“仅最新 revision 可操作”；旧 revision 的 CONFIRMED 行仍可被撤销（按 `order_item_id` 删其联动事实，语义自洽但易混淆）。后继可在 service 层加 revision 一致性提示或文档说明。
- P3-2（次序微调）：`revert_confirmation` 先判 CLOSED（409）后判非 CONFIRMED（400）；对 CLOSED 周期内 PENDING 行调用返回 409 而非 400。行为正确，仅错误归因可二选一，后继如需对齐“状态优先”口径再改。
