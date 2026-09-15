# BUGS

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---:|---:|---|---|---|---|
| 无 | — | — | — | 未发现产品 bug | D4 QA 未进入正式测试 | 能力预检未通过，按 QA 卡硬门禁停止；环境限制不登记为产品 bug。 |

## 真机QA会话能力预检结果（每真机session正式用例前必填，PASS才进正式QA，否则停）

- 日期/任务名：2026-09-15 / D4 增量 QA（P0#2 统一字段/NA、P0#3 双源核验/失败 NA、P0#4 三路契约/手动隔离/只读）
- session ID：不适用（命令行/HTTP QA 能力预检）
- 模型精确ID：codex/gpt-5.6-luna
- Runtime：本窗口命令行
- 原生CUA是否实际注入（确认是否真实存在 `mcp__cua_repl.js`，无结果如实记“未注入”，禁伪称已存在）：未注入；本任务未执行真机 UI QA
- 可用工具精确名称：`python3`、`sqlite3`、`curl`、`orca`
- CLI备用入口是否存在（Bash→orca computer CLI）：`/opt/homebrew/bin/orca` 存在；未进入真机 CUA 流程
- Orca Runtime（`orca status --json` 实时结果，禁沿用旧报告）：`state=stale_bootstrap`／`reachable=false`／`connectionState=disconnected`
- 能力（`orca computer capabilities --json` 实时结果）：失败，`runtime_unavailable`（无法连接运行中的 Orca）
- 权限（`orca computer permissions --json` 实时结果）：失败，`runtime_unavailable`（无法连接运行中的 Orca）
- 读屏结果：不适用
- 截图结果：不适用
- 点击并恢复结果：不适用
- 输入并清除结果：不适用
- 滚动及可见位移结果：不适用
- 界面恢复确认：不适用
- 最终结论：`BLOCKED_RUNTIME`
- 原始错误摘要：依赖检查通过（Python 3.9.6、SQLite 3.51.0、`curl`、`orca` 均存在）；对 `127.0.0.1:8765` 与 `127.0.0.1:18765` 的 socket 绑定均返回 `PermissionError: [Errno 1] Operation not permitted`；Orca 状态为不可达且未运行。
- 是否允许进入正式QA（全PASS才YES，否则NO即停）：NO

## D4 正式测试门禁

- 预检：FAIL（`BLOCKED_RUNTIME`）
- 正式测试：FAIL（未执行；预检未通过即停止）
- 未执行项目：独立重跑 `scripts/ledger_smoke_test.py`（确认总数/PASS/FAIL/EXIT、无正式库残留）、D4.1-D4.16、D4.P1-P9、D4.H0-H8、旧 146 项与 V1.2 回归。
- 演示数据/正式库：未创建或写入；未触碰正式库/生产目录。
- 产品 bug 条数：0（仅取得环境能力阻塞证据，未取得产品行为证据）

## Fix Attempt Fingerprint

- Task ID: D4
- Root Cause Hypothesis: 当前受限执行环境禁止本地 socket 绑定，且 Orca runtime 未运行，无法满足正式 HTTP/UI QA 所需的能力预检。
- Approach: 按 QA 卡实时检查命令行依赖、Orca 状态/能力/权限，并分别尝试绑定 8765 与 18765 测试端口。
- Files Changed: 仅新增本文件；未修改业务代码。
- Verification: Python 3.9.6、SQLite 3.51.0、`curl`、`orca` 可用；两端口绑定均失败；Orca `reachable=false`、`connectionState=disconnected`。
- Failure Reason: 能力预检未通过，QA 卡要求停止正式测试。
- Difference From Previous Attempt: D4 首次独立记录；复现 D3 的端口绑定限制，并新增实时 Orca runtime 不可达证据。
