# BUGS

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---:|---:|---|---|---|---|
| 无 | — | — | — | 未发现产品 bug | D7 QA 未进入正式测试 | 能力预检未通过，按 QA 卡硬门禁停止；环境限制不登记为产品 bug。 |

## 真机QA会话能力预检结果（每真机session正式用例前必填；PASS才进正式QA，否则停）

- 日期/任务名：2026-09-15 / D7（Change B）增量 QA
- session ID：不适用（命令行/HTTP QA 能力预检；CUA 初始化超时）
- 模型精确ID：codex/gpt-5.6-luna
- Runtime：本窗口命令行
- 原生CUA是否实际注入：已调用 `mcp__cua_repl.js` 的 `cua.getState()`；调用超时并导致 kernel reset，未取得可用 CUA 状态，未进入 UI Canary
- 可用工具精确名称：`python3`、`curl`、`orca`；`mcp__cua_repl.js` 调用入口存在但本次初始化未完成
- CLI备用入口是否存在（Bash→orca computer CLI）：`/opt/homebrew/bin/orca` 存在
- Orca Runtime（实时）：`state=stale_bootstrap`／`reachable=false`／`connectionState=disconnected`；`app.running=false`；`graph.state=not_running`
- 能力（实时）：失败，`runtime_unavailable`（Could not connect to the running Orca app）
- 权限（实时）：失败，`runtime_unavailable`；Accessibility／Screenshots／Orca应用访问未取得实时结果
- 读屏结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 截图结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 点击并恢复结果：未执行
- 输入并清除结果：未执行
- 滚动及可见位移结果：未执行
- 界面恢复确认：未执行
- 最终结论：`BLOCKED_RUNTIME`
- 原始错误摘要：`cua.getState()` 超时并导致 kernel reset；Orca `reachable=false`、`connectionState=disconnected`、`app.running=false`；能力/权限均返回 `runtime_unavailable`；绑定 `127.0.0.1:18765` 返回 `PermissionError: [Errno 1] Operation not permitted`。
- 是否允许进入正式QA：NO

## D7 正式测试门禁

- 预检：FAIL（`BLOCKED_RUNTIME`）
- 正式测试：FAIL（未执行；预检未通过即停止）
- 未执行项目：独立重跑 `scripts/ledger_smoke_test.py`（目标总数 242，含 PASS/FAIL、EXIT、临时目录清理与正式库残留检查）；D7.1-D7.16、D7.P1-P9、D7.H0-H7；旧 209 项回归。
- 演示数据/正式库：未创建或写入；未触碰正式库/生产目录。
- 产品 bug 条数：0（仅取得环境能力阻塞证据，未取得产品行为证据）

## Fix Attempt Fingerprint

- Task ID：D7
- Root Cause Hypothesis：当前受限执行环境禁止本地 socket 绑定，且 Orca Runtime 不可达，无法满足正式 HTTP/UI QA 所需的能力预检。
- Approach：按 QA 卡实时检查 CUA 注入、Orca 状态/能力/权限，并执行本地 socket 绑定能力检查。
- Files Changed：仅新增本文件；未修改业务代码。
- Verification：`/opt/homebrew/bin/orca` 存在；Orca 状态为 `stale_bootstrap`、不可达；能力/权限为 `runtime_unavailable`；socket 绑定被沙箱拒绝；CUA 初始化超时。
- Failure Reason：能力预检未通过，QA 卡要求停止正式测试。
- Difference From Previous Attempt：D7 新 session；实时复核 CUA 初始化与 Orca 状态，结论仍为环境阻塞，不将历史 smoke/reviewer 证据冒充本 session 正式 QA。

