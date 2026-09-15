
# CODE REVIEW

- Task: D9（回撤近似数据抓取＋接线：用户 2026-09-16 拍板近似＋交叉验证）
- Commit: NA（工作区无 git；审查对象为 D9 增量文件现状）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 过（P0=0；下述 P1×1、P2×3 均不阻断，可进 QA）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- P0-① 近似数据无编造（已实测）：`cache/valuation/drawdown.json` 9/9 `status=OK` 且每条均有 `source`＋`currentDate`；宽基 3 条为腾讯 fqkline bfq 近10年实抓（currentDate 2026-09-15，crossChecks tencent-close relDiff=0.0 pass=true）；红利 5 条＋标普为参考站 2026-08-07 快照兜底（`staleSnapshot=true`，source 明确写“其 ath 为 MAX(high) 口径，仅近似”）；标普 `etfProxy=true` 明确标注；失败路径回 NA（000852 无 REF 兜底则走 NA，fetch_drawdown.py:199-204）。独立重算 9 条 `drawdown == current/highest-1` 误差 <1e-6 全过。
- P0-② verify_drawdown 双源框架未被放宽（已实测）：`db/valution.py:160-259` 阈值锁死（0.5%/0.10%/top20/price+index+close 身份校验）原文未动；独立抽查 ETF/个股代理、high 字段、代码不一致负例仍被拒绝（ok=False）；smoke D4.1-D4.14 负例断言（缺失率/容差/最高日缺日/8 类身份负例）全部保留未删减。
- P0-③ display 公式一致（已实测）：`fetch_drawdown.py:155,159,188,192` 与 `valution.py:217,236` 均为 `current/highest-1`（同一序列）；文件 D9.7 与 board 透传 display，未重算篡改；前端 `index.html:216` 用 `dd.drawdown*100` 渲染，与文件值同源。
- P0-④ D4.15/D4.H1 改为近似契约属用户批准的设计跟随，非掩盖回归：口径 `更新日历与数据口径.md §3`＋HANDOFF Stage ID 均记录用户 2026-09-16 拍板“回撤上近似＋交叉验证”；D4.15（ledger_smoke_test.py:1141）仍断言 9 指数＋逐项 `reason` 含“近似数据”，D4.H1（:1222）仍断言 9 指数 OK，且 D4.1-D4.14 严格负例与 D4.16 规则锁死断言并存——严格门未删，只增近似分支。
- P0-⑤ 前端 ddNote 渲染来源行（已确认）：`index.html:230` 定义 `ddNote`（`drawdownMeta.note＋as-of`），:231-232 写入 `valuationFootnoteWide` 与 `valuationFootnoteDiv`；`loadDrawdownBoard`（:198）正常/异常分支均赋值 note，失败显示“回撤核验数据不可用”而非空白；D9.P1 断言存在。
- P0-⑥ 无近似文件回退 NA（已实测）：`_load_approx_board`（valution.py:269-274）文件缺失/损坏异常返回 `{}`；mock 缺失文件实测 `drawdown_board()` 9 指数全 NA＋drawdown None＋verified=False，走 `na_result(NO_SERIES_REASON)`（:315-316），不崩、不编数。
- P1-1（不阻断，下轮修）：逐项来源仅脚注级披露，行内不可见。OK 行的 `title`（index.html:216）只含最高收盘/日期，`reason`（含 source/ETF 代理/stale）未渲染到行内；快照项 `highestDate=""` 时行内显示“最高收盘 x（）”空括号。改法：`renderValuation` 的 `rowHtml` 中 `ddTxt` 的 title 追加 `dd.reason`（即 board 透传的“近似数据：…asOf…”），快照项 `highestDate` 为空时显示“日期未知（快照无最高日）”。

## P2 / P3 Backlog Findings

- P2-1：`fetch_drawdown.py:153` 的 `hi_date` 在全序列中取首个等于最高值的日期，而 `hi` 取自 10 年窗口；若同值在窗口外先出现则日期错配。改法：同函数内改为 `next(d for d,c in window if c == hi)`。
- P2-2：快照兜底 `highestDate=""`（drawdown.json 6 条）为空串而非 null，语义模糊。改法：`fetch_drawdown.py:189-196` 兜底分支写 `"highestDate": None`，并在 `_load_approx_board`/`drawdown_board` 透传时保持 None，前端空值时按 P1-1 文案渲染。
- P2-3：`fetch_drawdown.py:55-65 http_get` 用 timeout=30s＋4 次重试（退避 2/4/6/8s），与行情契约（timeout=3s、最多 2 次、0.5s→1.5s）不一致。历史回撤抓取可用更宽松参数，但建议在文件头 docstring 加一句“本参数仅适用于回撤历史批量抓取，不适用于行情三路契约”，防后人误抄。
