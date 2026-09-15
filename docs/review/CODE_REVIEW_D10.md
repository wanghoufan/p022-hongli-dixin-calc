
# CODE REVIEW

- Task: D10（宽基风险溢价 PE 口径反推 fallback）
- Commit: NA（非 git 仓库；基线 PRODUCT_PLAN_V1.0；smoke 282/282 EXIT=0，编排者代执行）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派）
- Result: 过（P0=0；P1=1 文案滞后随手可改，不阻断；P2=2）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- P1-1（文案滞后，不阻断）：`index.html:186` `VALUATION_META.wideNote` 仍写“宽基无课程模板风险溢价，故风险溢价列显示「暂无数据」”，与 D10 实际行为（PE 口径已反推有值、仅股息率口径仍 NA）及宽基脚注 `index.html:231` 不一致。改法：`wideNote` 改为“宽基无课程模板风险溢价，PE 口径按 100−PE分位反推估算显示，股息率口径仍显示「暂无数据」”，或直接引用脚注口径；`scripts/ledger_smoke_test.py` 可加一条 `wideNote` 不含“风险溢价列显示「暂无数据」”的断言。六项重点判定（均为 PASS）：
  ① 公式 `index.html:221` 为 `+(100-Number(r.v)).toFixed(2)`，prov=`公开估算·风险溢价(PE口径)反推＝100−PE分位`＋source=`公式反推（同参考站口径：国债扰动小，按 PE 分位反推）`，与参考站口径一致；
  ② 值正确：`MARKET_DATA`（`index.html:187`）pePct 63.8/77.7/69.8 → 36.2/22.3/30.2，`D10.3` 以 `round(100-pePct,2)` 独立验算通过；
  ③ 仅 fallback：`rpPe=(s&&s.peRpPct!=null)?课程值:反推`，六红利有 `s.peRpPct` 走课程分支不被覆盖，宽基 `sheet:null` 才走反推；`rpDy` 仍 `(s&&s.dyRpPct!=null)?…:null`；
  ④ 标估算＋悬停：反推分支 `est:true`，`vPctCell`（`:210`）渲染 `估算` 标签＋`title=口径｜来源`，脚注 `:231` 声明反推＋来源 URL/日期；
  ⑤ 股息率口径仍 NA：宽基 `rpDy=null` → `NA_TEXT`，脚注明示“股息率口径无授权同口径来源，仍显示「暂无数据」（不估算、不补造）”，未编数；
  ⑥ D7.P5 改近似契约属设计跟随非越界：`ledger_smoke_test.py:1641-1643` 由“全 NA”改为“PE 反推有值＋股息率仍 NA”，依据为证据门 B 例外（`PRODUCT_PLAN_V1.0.md:109` 用户拍板）＋`更新日历与数据口径.md:160`（2026-09-16 起生效）＋参考站方法，未碰后端/DB/旧接口。

## P2 / P3 Backlog Findings

- P2-1（可追溯小缺口）：反推 `rpPe` 的 hover `date/url` 为空（`:221` 传 `date:''`、`url:''`），B 例外①“来源名＋日期＋URL”靠底层 `pePct` 悬停与脚注补齐。建议：从 `pePct` 继承 `date/url`（如 `p.date/p.url`）或在 source 注明“日期/URL 见同行 PE 分位”，不阻断。
- P2-2（口径标注可加强）：反推未显式带 `period:'近 10 年（继承自 PE 分位）'`，而 `dyPct` 已带 `上市以来`。建议：给 `rpPe` 加 `period` 继承自 `pePct` 对应观察期，与 B 例外③对齐；smoke 加一条 `period` 断言。
