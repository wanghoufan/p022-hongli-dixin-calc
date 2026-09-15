# BUGS

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---:|---:|---|---|---|---|
| 无 | — | — | — | 未发现产品 bug | D3 QA 未进入正式测试 | 能力预检未通过，按 QA 卡硬门禁停止；环境限制不登记为产品 bug。 |

## 真机QA会话能力预检结果（每真机session正式用例前必填，PASS才进正式QA，否则停）

- 日期/任务名：2026-09-15 / D3 增量 QA（P0#8 checklist/单只/复制/四态/完成门禁；P0#9 进度恢复/confirmed/重复确认；D2 P1×2 修复）
- session ID：不适用（命令行/HTTP QA 能力预检）
- 模型精确ID：codex/gpt-5.6-luna
- Runtime：本窗口命令行
- 原生CUA是否实际注入（确认是否真实存在 `mcp__cua_repl.js`，无结果如实记“未注入”，禁伪称已存在）：未注入；本任务未执行真机 UI QA
- 可用工具精确名称：`python3`、`sqlite3`、`curl`、`orca`
- CLI备用入口是否存在（Bash→orca computer CLI）：`/opt/homebrew/bin/orca` 存在；未进入真机 CUA 流程
- Orca Runtime（`orca status --json` 实时结果，禁沿用旧报告）：未检查；命令行能力预检已失败，未进入真机 CUA 流程
- 能力（`orca computer capabilities --json` 实时结果）：未检查；命令行能力预检已失败
- 权限（`orca computer permissions --json` 实时结果）：未检查；命令行能力预检已失败
- 读屏结果：不适用
- 截图结果：不适用
- 点击并恢复结果：不适用
- 输入并清除结果：不适用
- 滚动及可见位移结果：不适用
- 界面恢复确认：不适用
- 最终结论：`NOT_VERIFIED`（命令行/HTTP QA 能力预检失败；非真机 CUA 结论）
- 原始错误摘要：`python3 --version`、`sqlite3 --version`、`command -v curl`、`command -v orca` 均成功；对 `127.0.0.1:8765` 与 `127.0.0.1:18765` 进行 socket 绑定测试均返回 `PermissionError: [Errno 1] Operation not permitted`。
- 是否允许进入正式QA（全PASS才YES，否则NO即停）：NO

## D3 正式测试门禁

- 预检：FAIL
- 正式测试：FAIL（未执行；预检未通过即停止）
- 未执行项目：独立重跑 `scripts/ledger_smoke_test.py`（确认总数/PASS/FAIL/EXIT）、D3.1-D3.17、D3.H1-H7、D2 P1×2 回归、旧 121 项、V1.2 首页/API 回归及正式库残留检查。
- 演示数据/正式库：未创建或写入；未触碰正式库/生产目录。
- 产品 bug 条数：0（仅取得环境能力阻塞证据，未取得产品行为证据）

## Fix Attempt Fingerprint

- Task ID: D3
- Root Cause Hypothesis: 当前受限执行环境禁止本地 socket 绑定，无法满足 HTTP 测试所需的能力预检。
- Approach: 只读检查命令行依赖，并分别尝试绑定 8765 与 18765 测试端口。
- Files Changed: 仅新增本文件；未修改业务代码。
- Verification: Python 3.9.6、SQLite 3.51.0、`curl`、`orca` CLI 可用；两个测试端口绑定均失败并返回 `Operation not permitted`。
- Failure Reason: 能力预检未通过，QA 卡要求停止正式测试。
- Difference From Previous Attempt: D3 首次独立记录；与 D2 相同的端口绑定限制再次复现。
