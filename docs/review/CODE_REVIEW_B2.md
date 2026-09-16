
# CODE REVIEW

- Task: B2（去 .bat / Windows 文案三处：index.html 32/338/498 行）
- Commit: 已推 00c62dc（当时工作区 diff 为 `git diff -- index.html` 三处纯文案删减；落盘时 `git status` 仅 `M index.html`）
- Reviewer: ORCA code-reviewer（本窗口直派）
- Result: PASS（P0=0；P1=0）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- 无。逐项复核（均为纯文案删减，无逻辑改动）：
  ① `index.html:32`（directFileWarning）：删 `或 <code>启动工具.bat</code>（Windows）`，保留 `启动工具.command（Mac）`；diff 行与工作区 `rg` 第 32 行一致；无其他分支引用该文案。
  ② `index.html:338`（initAllCaches alert）：`启动工具.command / .bat` → `启动工具.command`；diff 行与工作区第 338 行一致； surrounding fetch/prefetch/parse 逻辑零改动。
  ③ `index.html:498`（dpFreezeFromCalc dpNotice）：`启动工具.command/.bat` → `启动工具.command`；diff 行与工作区第 498 行一致；backendOK/cycle/holdings 三守卫顺序零改动。
- 残留排查：`rg "\.bat|Windows|启动工具" index.html` 中 `.bat` 零命中（`batch` 为账本批次变量，与 .bat 无关）；`Windows` 零命中；`启动工具` 仅剩 Mac/通用口径（32/338/498 已改＋561/564 行）。证据行见上。

## P2 / P3 Backlog Findings

- 无（P2=0；P3=0）。561/564 行 `启动工具` 未带 `.command` 后缀但属通用口径，不属本次三处范围，如需统一可另开任务。
