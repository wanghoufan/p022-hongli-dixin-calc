# BUGS

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---:|---:|---|---|---|---|
| 无 | — | — | — | 未发现产品 bug | D6 QA 未进入正式测试 | 能力预检未通过，按 QA 卡硬门禁停止；环境限制不登记为产品 bug。 |

## 真机QA会话能力预检结果（每真机session正式用例前必填，PASS才进正式QA，否则停）

- 日期/任务名：2026-09-15 / D6 增量 QA（P0#11 自动化夹具全绿、P0#12 文档验收齐全）
- session ID：不适用（命令行/HTTP QA 能力预检；CUA 初始化超时）
- 模型精确ID：codex/gpt-5.6-luna
- Runtime：本窗口命令行
- 原生CUA是否实际注入（确认是否真实存在 `mcp__cua_repl.js`，无结果如实记“未注入”，禁伪称已存在）：已调用 `mcp__cua_repl.js` 的 `cua.getState()`；调用超时并重置 kernel，未取得可用 CUA 状态，未进入 UI Canary
- 可用工具精确名称：`python3`、`sqlite3`、`curl`、`orca`；`mcp__cua_repl.js` 调用入口存在但本次初始化未完成
- CLI备用入口是否存在（Bash→orca computer CLI）：`/opt/homebrew/bin/orca` 存在
- Orca Runtime（`orca status --json` 实时结果，禁沿用旧报告）：`state=stale_bootstrap`／`reachable=false`／`connectionState=disconnected`；`app.running=false`；`graph.state=not_running`
- 能力（`orca computer capabilities --json` 实时结果）：失败，`runtime_unavailable`（Could not connect to the running Orca app）
- 权限（`orca computer permissions --json` 实时结果）：失败，`runtime_unavailable`（Could not connect to the running Orca app）；Accessibility／Screenshots／Orca应用访问：未取得实时权限结果
- 读屏结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 截图结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 点击并恢复结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 输入并清除结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 滚动及可见位移结果：未执行；CUA 初始化失败且 Orca Runtime 不可达
- 界面恢复确认：未执行
- 最终结论：`BLOCKED_RUNTIME`
- 原始错误摘要：`cua.getState()` 调用超时并导致 kernel reset；实时 Orca 状态为 `reachable=false`、`connectionState=disconnected`、`app.running=false`；能力/权限均返回 `runtime_unavailable`；本地 `127.0.0.1:18765` socket 绑定返回 `PermissionError: [Errno 1] Operation not permitted`。
- 是否允许进入正式QA（全PASS才YES，否则NO即停）：NO

## D6 正式测试门禁

- 预检：FAIL（`BLOCKED_RUNTIME`）
- 正式测试：FAIL（未执行；预检未通过即停止）
- 未执行项目：独立重跑 `scripts/ledger_smoke_test.py`（209/209、PASS/FAIL/EXIT、临时目录清理与正式库残留检查）、V1.2 回归断言、D6 P0#11/P0#12 正式核验。
- 演示数据/正式库：未创建或写入；未触碰正式库/生产目录。
- 产品 bug 条数：0（仅取得环境能力阻塞证据，未取得产品行为证据）

## Fix Attempt Fingerprint

- Task ID: D6
- Root Cause Hypothesis: 当前受限执行环境禁止本地 socket 绑定，且 Orca Runtime 不可达，无法满足正式 HTTP/UI QA 所需的能力预检。
- Approach: 按 QA 卡实时检查工具清单、CUA 注入、Orca 状态/能力/权限，并执行本地 socket 绑定能力检查。
- Files Changed: 仅新增本文件；未修改业务代码。
- Verification: `python3` 3.9.6、SQLite 3.51.0、`curl`、`orca` 可用；`cua.getState()` 超时；Orca `reachable=false`、`connectionState=disconnected`；socket 绑定被沙箱拒绝。
- Failure Reason: 能力预检未通过，QA 卡要求停止正式测试。
- Difference From Previous Attempt: D6 新 session；本次实时复核 CUA 初始化与 Orca 状态，结论仍为环境阻塞，不将历史 smoke/reviewer 证据冒充本 session 正式 QA。
