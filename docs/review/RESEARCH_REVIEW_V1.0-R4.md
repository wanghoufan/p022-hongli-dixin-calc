# RESEARCH_REVIEW（Phase1 专用；内部 role ID `product-reviewer` 不变）

- Plan Version（评的是哪版 PRODUCT_PLAN）：PRODUCT_PLAN_V1.0
- Review Round（第几轮）：第4轮（R4；只复核 R3 指出的两项增量）
- Result：**FAIL**。两项中“000905/H30269 的 as-of 日期修正”已落实，“Round 行区分 Reviewer 结论与 Planner 动作”已落实；但抓取时间仍只有口径要求，没有逐条可审计的实际 `fetchedAt` 记录。R2 的 9 条当前闭环为 **8/9**，尚不能进 Human Gate。
- P0 / P1 / P2：
  - P0：
    1. 九指数实际历史 close、估值原始序列/分位授权、双源实际序列及 930955 生效后 closeweight 仍未外部验收；Plan 的 NA/门禁正确，但这不是已完成事实。
  - P1：
    1. **Required Fix 1 未完全闭环**：第 71、73 行已改为 2026-08-31，但只写“抓取时间须另记”，表格没有 `fetchedAt` 列或逐指数具体抓取时间、hash 记录位置。可打开 URL 不等于 registry 证据可审计。
    2. 外部数据验收仍 blocking：历史覆盖、授权、同口径双源和 930955 生效后文件未提供。
  - P2：A500、sparkline/雷达图、费用税费/分红/公司行动、部分成交/撤单、生产调度等仍按 Plan 为非阻塞或 Change C。
- Key Assumptions（逐条列＋是否成立）：
  - 单用户、Mac Mini、本地 HTTP、低并发 SQLite：**基本成立**；标准库能力仍不替代项目实测。[Python sqlite3 文档](https://docs.python.org/3.13/library/sqlite3.html)
  - `confirmed` 仅表示人工核实已成交/已卖出成交：**成立**。
  - H30269、000905 factsheet 当前 as-of 为 2026-08-31：**成立**；R4 已按官方文件复核。
  - 每个 registry 条目已有可追溯抓取时间：**不成立**；通用字段虽声明 `fetchedAt`，逐指数交付表没有实际值或明确落盘记录。
  - 双源与行情阈值自洽：**成立（作为计划规则）**；尚待开发/QA 实测。
- Verified Facts（已验证事实＋证据）：
  - Plan 第 71、73 行当前均写 factsheet 快照截至 2026-08-31，已纠正 R3 指出的 2025-10-31 错误；官方 PDF 当前也显示 2026-08-31。[000905 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)；[H30269 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269factsheet.pdf)
  - 第 64 行虽列出 `fetchedAt`，但第 68-78 行表格没有实际抓取时间字段/值；第 71、73 行的“抓取时间须另记”仍是要求，不是证据。
  - 抽查的 H30269、930740、930955、931468、931446、000905、000852 官方 PDF 及 S&P 指数页均可打开；官方资料支持身份、方法、样本数和快照日期，不支持历史分位已存在。[930955 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)；[930740 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930740factsheet.pdf)；[S&P 指数页](https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/)
  - 第 83-86 行的双源/930955/行情规则仍在位：inner join、0.5% 缺失、0.10% 相对误差、负例、3 秒、2 次重试、72 小时和 `effective_date` 门均已具体化。
  - 第 164 行已正确写成：R2 Reviewer **5/9**，Planner 后续完成 9 条口径动作；R3 Reviewer **7/9**，本轮修正日期并区分记录。该项已落实，但不得把 Planner 动作当 Reviewer PASS。
- External Sources（Web Search / Web Fetch / 官方文档 / 官方 GitHub / 第三方 / 社区反馈，附链接）：
  - 中证官方 factsheet/方法文件：抽查 URL 可达、代码/样本数/快照日期可对照；如 [930955 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)、[000905 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)。
  - 上交所三季度公告只证明公告所述科创50等指数 2026-09-11 收市后生效，不能代替 930955 生效后文件。[公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - S&P 官方页确认指数定义及关联 ETF 产品，支持“产品不等于指数 close”边界。[S&P 页面](https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/)
  - Python 官方文档支持 `sqlite3.connect(timeout=...)` 等能力；项目级 WAL/恢复仍须后续实测。[文档](https://docs.python.org/3.13/library/sqlite3.html)
- Competitor Findings（竞品现状＋对本 Plan 的启示）：
  - R2 已引用的参考仓库披露示例 history、估算分位和代理价格；Plan 的 NA、同指数 close 和禁止 ETF 代理做法正确，但本轮日期错配说明 registry 必须保存实际抓取证据，不可只保存链接。[参考仓库 README](https://github.com/wanghoufan/a-share-index-valuation-report#readme)
- Counter-evidence（反对证据＋成功的相反做法）：
  - 官方快照确实可用：H30269/000905/930955 文件均能提供身份和日期化指标；成功做法是记录 `asOf` 与真实 `fetchedAt`，并把历史 close/分位继续留 NA。
  - 阈值规则已经足够具体，不能因此推断已经执行；成功做法是后续用实际请求和坏例逐项留下结果。
  - “R2 9/9”是 Planner 动作汇总，不是 R2 Reviewer 结论；Plan 现已区分这一点，但 R4 仍应独立判闭环。
- Unverified Items（未验证项＋验证方法）：
  - registry 抓取时间：为每个实际 URL 增加 `fetchedAt`（含时区）与内容 hash，或明确统一证据日志的文件/记录 ID，并逐行可回溯。
  - 九指数历史 close/估值分位：取得原始序列、覆盖、公式、分位边界和授权，生成可复算记录。
  - 930955：取得官方生效后文件，核对自身 `effective_date`、代码/名称、100 个样本、权重和、hash 及新旧差异。
  - 双源/行情/SQLite：依第 83-86、114-116 行在开发/QA 实际测试，当前仍不可标为通过。
- Required Fixes（Planner 必须改项，打回依据）：
  1. **补齐可审计抓取证据**：把 `fetchedAt` 和 hash 纳入逐指数 registry 表，或在表中引用统一证据日志的明确记录；仅写“须另记”不算闭环。日期 2026-08-31 本身已正确。
  2. 930955 以官方文件自身 `effective_date` 为准的规则已闭环；实际文件验收仍是外部 P0。
  3. 双源 inner join/0.5%/候选最高 20/0.10%/抽样/负例已闭环为计划规则。
  4. 行情 3 秒/2 次/退避/10 分钟 3 次/72 小时/3 交易日/连续 2 次恢复已闭环为计划规则。
  5. 回撤失败 NA＋原因已闭环。
  6. 估值分位在证据门前非 MVP、显示 NA 已闭环。
  7. SQLite DoD 已具体化；开发/QA 实测仍未发生。
  8. `confirmed` 已成交语义已闭环。
  9. Round 行已区分 R2 的 Reviewer 5/9、Planner 9 条动作与 R3 Reviewer 7/9；此项已闭环，但 R4 结论不能被 Plan 自述替代。
- Plan Readiness Score（分项打分＋合计，口径以 PRODUCT_PLAN.template.md 为准）：
  - 产品目标与用户需求（20）：18/20。闭环、计划/事实分离、成交语义和 NA 体验清楚；费用、交易单位和成交价待人确认。
  - 核心方案完整性（20）：19/20。双源、行情、SQLite、registry 结构已具体化；逐条抓取证据仍缺。
  - 外部事实与竞品验证（20）：14/20。抽查官方 URL/快照和 S&P 页面可核验；九指数历史序列/授权、东财 E2E、930955 生效后文件仍未完成。
  - 技术可行性（15）：14/15。规则可执行，但尚未进入实现和项目级测试。
  - 风险与异常场景（10）：10/10。数据缺失、代理误用、陈旧、失败和成交边界均已写明。
  - 开发范围与 DoD（10）：9/10。DoD 执行化程度高；registry 证据日志仍待补。
  - 未决问题（5）：3/5。5 项人类 blocking 决策、外部数据验收和正式环境授权仍在。
  - 合计：**87/100**
  - Gate：不满足 `>=90`、P0=0、blocking P1=0、关键事实已验证；**FAIL，不得进入 WAITING_HUMAN_APPROVAL，不得派 Builder**。
- Human-only Decisions（只需人类拍板项）：
  1. 是否接受历史 close/估值分位/回撤无合法同口径证据时显示 NA；建议接受。
  2. 是否接受腾讯/东方财富仅为 best-effort 未版本化网页源；建议接受。
  3. 是否确认 `project_slug=dividend-portfolio`、普通 A 股 100 股整手及特殊交易单位范围。
  4. 是否首版不计佣金、税费、分红、公司行动、部分成交/撤单；建议暂不计并另立 Change C。
  5. 实际成交价必填/可选/参考价；建议可选并保留 `reference_price`。
  6. 是否纳入 A500，以及何时授权正式 Docker/SQLite 目录、备份和调度。
- Next Action：（回 Planner 修订 / 进 WAITING_HUMAN_APPROVAL 找人）
  - **回 Planner 修订**：补逐指数 `fetchedAt`/hash 可审计记录后再做 R5 确认。当前剩余 blocking 仍不只有人类决策＋外部数据验收，不能进 Human Gate。
