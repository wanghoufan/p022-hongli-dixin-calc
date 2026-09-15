# ACCEPTANCE D6｜红利打新底仓计算器 V1.3 验收报告

- Task：D6（文档对齐 + 验收报告 + 最终回归；P0#1#11#12）
- DEV_BASELINE：PRODUCT_PLAN_V1.0
- 日期：2026-09-15
- 制作：ORCA builder（opencode-go/deepseek-v4.1-flash，Runtime: opencode）
- 范围：只做文档与最终回归，不新增功能、不改算法逻辑、不动产品代码；禁 commit/push；全程仅用系统临时目录开发库，未触碰正式库/生产目录。
- 结论摘要：**自动化回归 209/209 EXIT=0（D1-D6 合计）**；文档四件对齐 + 本报告落盘；已知未决项 4 类（见下），均属外部/环境/授权边界，非产品 bug。

> 本报告为验收事实记录，不构成投资建议。演示数据均为虚构且可清除。

## 一、烟雾测试总数（D1-D6 实测矩阵）

运行命令：`python3 scripts/ledger_smoke_test.py`
运行环境：系统临时目录 `d1-ledger-matrix-*` 建开发库；服务端口 8799；正式库/生产目录全程未触碰。

| 阶段 | 覆盖内容（P0） | 累计用例 | 本轮结果 |
|---|---|---:|---|
| D1 | SQLite 迁移/schema/版本/隔离/WAL/不可变触发器 + `/api/ledger/*`（P0#5） | 79 | PASS 79 |
| D2 | 四生命周期计划引擎 + 冻结/revision + 数学不变量（P0#6#7） | 121 | PASS 121 |
| D3 | 下单执行页 + 四态/完成门禁 + 进度恢复（P0#8#9） | 146 | PASS 146 |
| D4 | 估值回撤看板 + 行情三路状态契约 + 手动覆盖隔离（P0#2#3#4） | 180 | PASS 180 |
| D5 | 持仓历史页 + 非当前成分 STALE_CONSTITUENT（P0#10） | 209 | PASS 209 |
| D6 | 文档对齐 + 验收报告（无新增用例，仅全量回归） | 209 | **PASS 209 / FAIL 0 / EXIT=0** |

- D6 阶段明细（按 smoke 脚本小节）：`1.x` 12 + `2.x` 22 + `3.x` 4 + `4.x` 7 + `5.x` 7 + `6.x` 27（含 6.19a/b/c）+ `D2.*` 33 + `D2.H*` 9 + `D3.*` 18 + `D3.H*` 7 + `D4.*` 16 + `D4.P*` 9 + `D4.H*` 9 + `D5.ST*` 8 + `D5.Q*` 7 + `D5.S*` 3 + `D5.P*` 6 + `D5.H*` 5 = **209**。
- 期间 FAIL 0，EXIT=0；临时目录可整目录删除，无正式库残留。

## 二、V1.2 回归项（原文能力保护，P0#1）

以下为 smoke 中显式标注的 V1.2 回归断言，D6 全量复跑均 PASS：

| 用例 | 断言 | 结果 |
|---|---|---|
| 6.1 | 服务启动可访问 | PASS |
| 6.2 | 首页 200 + 含 V1.2 界面标记 | PASS |
| 6.3 | `/api/health` 语义不变（`ok=true`、`version=1.2`） | PASS |
| 6.4 | `/api/cache-status` 语义不变（含 `indices`/`quotes`） | PASS |
| 6.5 | `/api/holdings?code=` 仍为指数权重缓存（旧语义） | PASS |
| 6.6 | 未知指数代码仍 400 | PASS |
| 6.7 | `/api/quotes` 无有效代码仍 400 | PASS |
| 6.8 | `/api/weight` 非中证权重指数仍 400 | PASS |
| 6.9 | `/api/save-parsed` 校验语义不变（异常入参 400） | PASS |
| 6.10 | 静态服务不暴露 `db/` 目录（403） | PASS |
| 6.11 | 静态服务不暴露 `.db` 文件（403） | PASS |
| D4.P9 | V1.2 区块未动（`initSelect` / `indexSelect` / `valuationRows` / SheetJS 第 3 行） | PASS |
| D4.H6 | `/api/quotes` 无有效代码仍 400（V1.2 回归） | PASS |
| D4.H7 | `/api/health` 语义不变（V1.2 回归） | PASS |
| D5.P6 | V1.2 / D1-D4 区块未动（SheetJS 第 3 行 / `initSelect` / `valuationTable` / `MANUAL_OVERRIDE`） | PASS |

配套证据（同目录/同批）：`docs/review/CODE_REVIEW_D1..D5.md`（逐阶段 P0=0）、`docs/qa/BUGS_D1..D5.md`（各阶段产品 bug 0 条）、`docs/model/TASK-MODEL-LOG.jsonl` 与 `docs/model/DISPATCH-LOG.jsonl`。

## 三、文档验收（P0#12 DoD 文档条）

| 文档 | 本轮动作 | 结果 |
|---|---|---|
| `README.md` | 增量一节「V1.3 增量（账本 · 下单执行 · 持仓历史 · 估值回撤 · 行情状态）」：cycles/batches、下单页、持仓页、回撤 NA、行情五态、手动覆盖区用法、启动命令、dev.db 说明；不改 V1.2 原有节 | 完成 |
| `CHANGELOG.md` | 新增 V1.3 条（D1-D5 改动摘要 + D6 + 209/209） | 完成 |
| `更新日历与数据口径.md` | 增量一节「V1.3 数据契约」：source registry NA 现状、930955 验收门未过、回撤 NA、行情 best-effort、维护边界 | 完成 |
| `智能体更新提示词.md` | 增量「V1.3 维护增量」：migration 不可回改、开发/生产隔离、备份恢复、数据契约不退化、回归验收 | 完成 |
| `docs/qa/ACCEPTANCE_D6.md` | 本验收报告 | 完成 |

## 四、已知未决项（不阻塞 D6 文档/回归收尾，需人类或后续链处理）

1. **QA 通道环境 FAIL×5（环境，非产品 bug）**
   D1-D5 每阶段 QA 能力预检均 FAIL：受限执行环境禁止本地 socket 绑定（`PermissionError: [Errno 1] Operation not permitted`），D4/D5 另加 Orca Runtime 不可达（`reachable=false`、`connectionState=disconnected`，`BLOCKED_RUNTIME`）。按 QA 卡硬门禁停止正式 QA，未取得产品行为证据，**产品 bug 0 条**。证据见 `docs/qa/BUGS_D1..D5.md`。supervisor 已按链独立重跑烟雾补位（逐阶段 EXIT=0）。

2. **真机 / 浏览器复验待用户**
   V1.2.1 曾通过 Playwright 真实浏览器端到端验证；V1.3 增量 UI（估值总览/下单执行页/持仓历史页/手动覆盖区）尚未在用户真实浏览器/手机复制流程复验。**待在用户环境下打开 `http://127.0.0.1:8765/` 人工复验**（收尾找人一次）。

3. **外部数据 P0 门未过**
   九指数历史 close/估值分位/风险溢价无授权同口径序列（Curl E01-E20 全 FAIL，hash NA）→ 回撤/分位统一 `NA`；930955 2026-09 生效后 closeweight 官方文件验收门未过 → 保留旧快照标 `stale/待核验`，不替换缓存、不生成新计划。属计划内 blocking P1，需 Research Reviewer/数据验收链后续核验。

4. **生产未授权**
   正式 Docker/SQLite 目录、`DockerData`/`DockerBackups`、生产数据库、容器、端口与定时调度均**未授权**，本版未创建、未迁移、未覆盖。当前交付仅本地开发/测试。

## 五、边界与安全声明

- 全程未 commit/push；未改产品代码/算法逻辑；未碰 secrets；未创建或写入正式库/生产目录。
- 账本只做计划、记录与核对，不自动下单、不自动卖出、不接券商接口；只有用户人工核实「已成交/已卖出成交」的记录才写入账本。
- 演示数据虚构、可清除，不影响真实数据。

---

*ACCEPTANCE_D6 由 ORCA builder 落盘，待 code-reviewer/qa/supervisor 收链复核。*

## 增补｜D7-D10（2026-09-16，用户验收返工＋Change B，不改 D6 结论）

| 阶段 | 内容 | 烟雾 |
|---|---|---:|
| D7 | 估值紧凑两表＋宽基公开估算＋行内确认/回车＋复制 toast＋删除测试批次（migration 0002/schema v2） | 242/242 |
| D8 | 单行撤销已确认成交（migration 0003/schema v3＋`ledger_reverts`）＋标签 nowrap | 262/262 |
| D9 | 回撤近似数据抓取接线（`fetch_drawdown.py`＋`drawdown.json` 9/9＋脚注来源行） | 278/278 |
| D10 | 宽基风险溢价 PE 口径反推（36.2/22.3/30.2，标估算） | 282/282 |

- 每阶段 reviewer 过（P0=0）、QA 通道环境 FAIL（bug 0）、supervisor 独立重跑补位；rework 0，无升级。证据见 `docs/review/CODE_REVIEW_D7..D10.md`、`docs/qa/BUGS_D7..D10.md`、双账本。
