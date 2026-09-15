# BUGS

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---|---:|---|---|---|---|
| 无 | — | — | — | 未发现产品 bug | D1 QA 未进入正式测试 | 能力预检未通过，按 QA 卡硬门禁停止；不将环境限制登记为产品 bug。 |

## 真机QA会话能力预检结果（每真机session正式用例前必填，PASS才进正式QA，否则停）

> 判据：`ok=true/exit 0/工具调用成功`但无状态或像素变化一律记 `FAIL_UNVERIFIED_ACTION`；禁跨模型/跨Runtime/跨session拼PASS。

- 日期/任务名：2026-09-15 / D1 SQLite 账本骨架 QA
- session ID：不适用（非真机 CUA 测试；命令行能力预检）
- 模型精确ID：codex/gpt-5.6-luna
- Runtime：本窗口命令行
- 原生CUA是否实际注入（确认是否真实存在 `mcp__cua_repl.js`，无结果如实记“未注入”，禁伪称已存在）：未注入；本任务不执行真机 UI QA
- 可用工具精确名称：`python3`、`sqlite3`、`curl`
- CLI备用入口是否存在（Bash→orca computer CLI）：`orca` CLI 存在；未进入真机 CUA 流程
- Orca Runtime（`orca status --json` 实时结果，禁沿用旧报告）：未检查；本任务未进入真机 CUA 流程
- 能力（`orca computer capabilities --json` 实时结果）：未检查；本任务未进入真机 CUA 流程
- 权限（`orca computer permissions --json` 实时结果）：未检查；本任务未进入真机 CUA 流程
- 读屏结果：不适用
- 截图结果：不适用
- 点击并恢复结果：不适用
- 输入并清除结果：不适用
- 滚动及可见位移结果：不适用
- 界面恢复确认：不适用
- 最终结论（枚举只许 `PASS / BLOCKED_TOOL_NOT_INJECTED / BLOCKED_ORCA_APPROVAL / BLOCKED_RUNTIME / BLOCKED_OS_PERMISSION / FAIL_UNVERIFIED_ACTION / NOT_VERIFIED`，禁 `FAIL_MODEL_ACTION`）：NOT_VERIFIED（本任务为命令行 QA 能力预检；D1 正式测试门禁结论为 FAIL）
- 原始错误摘要：`python3 --version`、`sqlite3 --version`、`command -v curl` 均成功；尝试在 `127.0.0.1:8765` 与 `127.0.0.1:18765` 绑定测试端口均返回 `OSError: [Errno 1] Operation not permitted`。
- 是否允许进入正式QA（全PASS才YES，否则NO即停）：NO

## D1 正式测试门禁

- 预检：FAIL
- 正式测试：FAIL（未执行；预检未通过即停止）
- 未执行项目：`scripts/ledger_smoke_test.py` 79/79 独立重跑、V1.2 首页/API/旧 `/api/holdings`/SheetJS/initSelect 回归、静态服务 `.db` 抽查。
- 产品 bug 条数：0（当前仅有环境能力阻塞，未取得产品行为证据）

## Fix Attempt Fingerprint

- Task ID: D1
- Root Cause Hypothesis: 当前受限执行环境禁止本地 socket 绑定，无法满足服务启动能力预检。
- Approach: 只读检查命令行依赖并尝试绑定 8765 以外测试端口。
- Files Changed: 仅新增本文件；未修改业务代码。
- Verification: `python3`、`sqlite3`、`curl` 可用；两个测试端口绑定均失败并返回 `Operation not permitted`。
- Failure Reason: 能力预检未通过，QA 卡要求停止正式测试。
- Difference From Previous Attempt: 本次为 D1 QA 首次独立预检。
