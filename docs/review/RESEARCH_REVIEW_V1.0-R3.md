# RESEARCH_REVIEW（Phase1 专用；内部 role ID `product-reviewer` 不变）

- Plan Version（评的是哪版 PRODUCT_PLAN）：PRODUCT_PLAN_V1.0
- Review Round（第几轮）：第3轮（R3；确认性复核 R2 修订）
- Result：**FAIL**。R2 的 9 条 Required Fixes 中 **7/9 真闭环，2/9 仍是文字/部分闭环**。Plan 已显著接近可审查，但 registry 元数据仍有事实不一致，且 R2 结论被错误写成 9/9；剩余 blocking 不只有人类决策和外部数据验收，仍需回 Planner 修正。
- P0 / P1 / P2：
  - P0：
    1. 九指数历史 close、估值原始序列/分位授权和 930955 生效后 closeweight 仍未实际验收；Plan 正确保留 NA/门禁，但不能作为已完成事实。
  - P1：
    1. **Required Fix 1 部分未闭环**：registry URL 抽查可打开，但至少 H30269、000905 行把官方 factsheet 覆盖日写成 2025-10-31；当前同 URL 文件显示 2026-08-31。registry 的可审计字段因此不一致。
    2. **Required Fix 9 部分未闭环**：Plan 第 164 行把“R2 结论”写成 9/9，而已落盘 R2 报告结论是 5/9；状态同步存在，但结论同步错误。
    3. 外部数据验收仍是 blocking：实际历史序列、授权、双源序列和 930955 生效后官方文件未提供。
  - P2：A500、真实 sparkline/雷达图、费用税费/分红/公司行动、部分成交/撤单、生产调度等，按 Plan 维持非阻塞或 Change C。
- Key Assumptions（逐条列＋是否成立）：
  - 单用户、Mac Mini、本地 HTTP、低并发 SQLite：**基本成立**；标准库能力不等于项目级并发/恢复验收。[Python sqlite3 文档](https://docs.python.org/3.13/library/sqlite3.html)
  - `confirmed` 只代表人工核实已成交/已卖出成交：**成立**；文字与 R2 一致。
  - registry 中“URL 可打开”即等于字段已验证：**不成立**；还必须与文件实际日期、口径、授权、覆盖范围一致。
  - 930955 2026-09 的生效日可以预设为 2026-09-11：**不成立**；当前 Plan 已改为以官方文件自身 `effective_date` 为准，这一修订正确，但文件仍未取得。
  - 3 秒/2 次/退避/72 小时等阈值互相冲突：**未发现直接矛盾**；3 秒为单次请求超时，最多重试 2 次，退避 0.5→1.5 秒，10 分钟滚动窗口的 3 次失败和 72 小时缓存是不同层级条件。
- Verified Facts（已验证事实＋证据）：
  - Plan 第 63-80 行已形成逐指数表，身份/方法入口与 `NA` 分离；抽查 H30269、930740、930955、931468、931446、000905、000852 PDF 及 S&P 指数页均能打开。官方资料确实支持身份、样本数和日期化快照，不支持历史估值分位已存在。
  - 抽查结果发现 Plan 第 71 行的 000905 factsheet URL 当前内容标注 2026-08-31，而 Plan 写 2025-10-31；第 73 行 H30269 同样当前内容为 2026-08-31。该差异直接破坏 registry 的覆盖日期字段。[000905 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)；[H30269 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269factsheet.pdf)
  - 930955 官方 factsheet标明代码 930955、样本数 100、季度调样、快照日期 2026-08-31；没有证明 2026-09 生效后 closeweight 文件已取得。[930955 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)
  - Plan 第 83-84 行已写明 inner join、并集缺失率 0.5%、候选最高 20 个缺日、相对误差 0.10%、全量区间、端点/前后 5 日/随机 20 日抽查及 ETF/个股/high/代码错负例；该条已从文字要求变为可执行规则。
  - Plan 第 85 行的行情阈值可自洽：3 秒单次 timeout、最多重试 2 次、0.5→1.5 秒退避、10 分钟内连续 3 次失败降级、72 小时/3 交易日陈旧、连续 2 次成功恢复；这仍是待实现/实测的 DoD，不是已通过证据。
  - Plan 第 33、113-116 行已明确估值分位无证据只显示 NA、回撤失败只显示 NA、行情和 SQLite 验收条件；第 94 行已闭合 confirmed 语义。
  - Plan 第 164 行确实补入 R2/74/9 条修订摘要，但该摘要把 R2 的既有结论写为 9/9；与 `docs/review/RESEARCH_REVIEW_V1.0-R2.md` 的 5/9 不一致。
- External Sources（Web Search / Web Fetch / 官方文档 / 官方 GitHub / 第三方 / 社区反馈，附链接）：
  - 中证官方：930955、000905、H30269、930740、931468、931446 factsheet，以及 000852 方法文件；用于核对 URL 可达性、代码、样本数、调样频率和快照日期。[中证指数首页](https://www.csindex.com.cn/)
  - 上交所公告：所述科创50等指数调整于 2026-09-11 收市后生效；不能外推为 930955 调样已生效。[公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - S&P 官方页可打开，并明确指数为中国 A 股大盘低波高股息 50 指数；其页面列出的 515450 是关联 ETF 产品，不能作为指数 close 代理。[S&P 指数页](https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/)
  - 腾讯端点本次可访问，但只证明当前响应可得，不证明授权、SLA 或稳定契约。[腾讯端点](https://qt.gtimg.cn/q=sh600519)
  - SQLite/Python 官方文档：支持本地数据库和连接 timeout；不替代 Mac Mini 项目测试。[sqlite3 文档](https://docs.python.org/3.13/library/sqlite3.html)
- Competitor Findings（竞品现状＋对本 Plan 的启示）：
  - R2 已引用的参考仓库仍明确披露示例 history、估算分位和 ETF/全 A 代理；Plan 现在的 NA 与同指数 close 约束是正确的相反做法，但 registry 日期错误说明“有链接”仍不等于有证据闭环。[参考仓库 README](https://github.com/wanghoufan/a-share-index-valuation-report#readme)
  - S&P 官方页同时展示指数定义与关联产品，说明产品链接和指数序列必须分字段保存；Plan 已禁止把 515450 当 close 代理，这点正确。
- Counter-evidence（反对证据＋成功的相反做法）：
  - 反对“所有外部资料都不可用”：官方 factsheet/方法文件确实可访问并能支持身份、方法、样本数和 as-of 快照；成功做法是只把这些字段标为已证实，历史 close/分位仍为 NA。
  - 反对“阈值写得多就等于已验收”：3 秒、0.10%、72 小时等目前只是 Plan 规则，必须在后续开发/QA 用坏例和真实响应验证。
  - 反对“R2 口径 9/9 可直接沿用”：R2 报告明确是 5/9；本轮应按逐条复核结果更新，而不是把 Planner 修订声明当 Reviewer 结论。
- Unverified Items（未验证项＋验证方法）：
  - 逐行核正 registry：重新读取每个 URL 的实际文件日期、指数代码、方法/权重口径；修正 000905/H30269 等日期错配，记录抓取时间、hash 和授权依据。
  - 930955：取得官方文件并核对自身 `effective_date`、代码/名称、100 个样本、权重和容差、URL/hash、与旧快照差异；不要用上交所科创50公告代替。
  - 九指数历史 close/估值分位：实际获取原始序列，固定覆盖、交易日、公式、分位边界和授权，生成可复算证据。
  - highestClose：按第 83-84 行规则实现并用缺日、0.10% 超差、ETF/high/代码错负例验证失败降级。
  - 行情：在目标 Mac Mini 环境验证 3 秒 timeout、2 次重试、退避、3 次失败、72 小时/3 交易日陈旧和 2 次恢复；记录东财 E2E 响应。
  - SQLite：临时库验证双连接、busy_timeout、WAL checkpoint、重启、异常中断、backup/VACUUM INTO、integrity_check/foreign_key_check 和 WAL 文件边界。
- Required Fixes（Planner 必须改项，打回依据）：
  1. **修正 registry 事实字段**：至少更正第 71、73 行 factsheet 的实际 as-of 日期，并对所有“已验证覆盖/口径”做 URL 内容逐项对账；URL 可打开不能掩盖日期不一致。
  2. 930955 的 `effective_date` 门已正确改为文件自证；保留 P0，补文件取得后的实际验收记录。
  3. 双源 inner join、0.5%、候选最高 20、0.10%、抽样和负例规则已闭环；开发时照此验收。
  4. 行情阈值已闭环为计划规则；开发/QA 必须实测，不再新增歧义。
  5. 回撤失败 NA＋原因已闭环。
  6. 估值分位证据门前非 MVP/显示 NA 已闭环，建议保持 Functional Scope 与 DoD 同措辞。
  7. SQLite DoD 已闭环为计划要求；实际测试仍是开发前 P0 验收，不得提前宣称通过。
  8. confirmed 已成交语义已闭环。
  9. **修正 R2 状态同步**：Plan 第 164 行应如实区分“Planner 已补齐 9 条口径”与“R2 Reviewer 结论为 5/9”；本 R3 的最终闭环数、分数和结论在本报告后再更新，避免循环引用。
- Plan Readiness Score（分项打分＋合计，口径以 PRODUCT_PLAN.template.md 为准）：
  - 产品目标与用户需求（20）：18/20。闭环、计划/事实分离、成交语义和 NA 体验清楚；费用、交易单位、成交价仍待人确认。
  - 核心方案完整性（20）：18/20。registry 结构、双源算法、行情状态和 SQLite DoD 已具体化；registry 数据对账仍有错误。
  - 外部事实与竞品验证（20）：13/20。多个官方 URL/快照可核验，S&P 页面和腾讯可达；九指数历史序列/授权、东财 E2E、930955 生效后文件仍未完成。
  - 技术可行性（15）：14/15。阈值和 SQLite 验收矩阵可执行，但尚未实际开发/测试。
  - 风险与异常场景（10）：10/10。失败、陈旧、代理误用、成交歧义和数据缺失均有明确边界。
  - 开发范围与 DoD（10）：9/10。大部分 DoD 已执行化；registry 事实对账与 R2 状态记录需修正。
  - 未决问题（5）：3/5。仍有 5 项人类 blocking 决策、外部数据验收及正式环境授权。
  - 合计：**85/100**
  - Gate：不满足 `>=90`、P0=0、blocking P1=0、关键事实已验证；**FAIL，不得进入 WAITING_HUMAN_APPROVAL，不得派 Builder**。
- Human-only Decisions（只需人类拍板项）：
  1. 是否接受历史数据/估值分位/回撤无证据时显示 NA，并暂不承诺完整数值；建议接受。
  2. 是否接受腾讯/东方财富仅为 best-effort 未版本化网页源；建议接受。
  3. 是否确认 `project_slug=dividend-portfolio`、普通 A 股 100 股整手及特殊交易单位范围。
  4. 是否首版不计佣金、税费、分红、公司行动、部分成交/撤单；建议暂不计并另立 Change C。
  5. 实际成交价必填/可选/参考价；建议可选并保留 `reference_price`。
  6. 是否纳入 A500，以及何时授权正式 Docker/SQLite 目录、备份和调度。
- Next Action：（回 Planner 修订 / 进 WAITING_HUMAN_APPROVAL 找人）
  - **回 Planner 修订**：先修正 registry 实际日期/证据字段，纠正 R2 5/9 与 Planner 9/9 的状态口径；修订后再做 R4 确认。当前剩余 blocking **不只有人类决策＋外部数据验收**，因此不能进 Human Gate。
