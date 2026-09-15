# RESEARCH_REVIEW（Phase1 专用；内部 role ID `product-reviewer` 不变）

- Plan Version（评的是哪版 PRODUCT_PLAN）：PRODUCT_PLAN_V1.0
- Review Round（第几轮）：第2轮（Research Review R2；复核 R1 的 9 条 Required Fixes）
- Result：**FAIL**。Plan 已把多数风险写成约束和验收门，但 9 条 Required Fixes 只有 **5/9 真闭环**；剩余不只人类决策和外部数据验收，还有 Planner 必须补齐的可执行口径与本轮评分同步，因此不得进 Human Gate，不得派 Builder。
- P0 / P1 / P2：
  - P0：
    1. **FR-外部数据未闭环**：九指数实际历史 close、估值序列/分位授权与覆盖仍全为 `NA`；930955 2026-09 调样后 closeweight 仍无对应官方文件证据。Plan 已写门禁，但尚未提供可审计数据交付物。
    2. **FR-回撤验收口径未执行化**：`app/` 级别可实现的双源同指数约束已写，但日期对齐规则、数值容差、异常/缺失处理的具体阈值与样例仍没有定值。
  - P1：
    1. source registry 只有字段定义和 9 行空矩阵，不是“逐指数 source registry 已填实”；每个字段的 URL、授权依据、覆盖起止日、口径和失效等级仍缺。
    2. 腾讯/东方财富仍缺限流、重试/退避、连续失败窗口、缓存最大陈旧时间和恢复条件等可测试契约。
    3. Plan 的 R2 研究轮次与 Readiness 尚未同步：第 158 行仍写 R1/61，分项仍合计 76，不能作为当前研究结论。
  - P2：中证 A500、sparkline/雷达图/风险溢价分位、费用税费/分红/公司行动、部分成交/撤单、生产备份策略等，按 Plan 维持非阻塞或 Change C 范围。
- Key Assumptions（逐条列＋是否成立）：
  - 单用户、Mac Mini、本地 HTTP、低并发 SQLite：**基本成立**；Python 标准库确实提供 sqlite3，`timeout` 可等待锁，但项目级 WAL/恢复/并发仍须实测。[Python sqlite3 官方文档](https://docs.python.org/3.13/library/sqlite3.html)
  - 计划与事实分离，`confirmed` 仅表示人工核实已成交/已卖出成交：**成立（文字已修正）**；部分成交/撤单明确排除。
  - 九指数均可取得合法、长期、同口径 close 与 PE/PB/股息率分位：**不成立/未证实**；矩阵当前全为 `NA`，不能把“将来填实”当作现状能力。
  - 930955 的 2026-09 调样后文件可用且应以 2026-09-11 为验收下限：**未成立**。官方 factsheet 只证明 930955、季度调样、100 只样本及 2026-08-31 快照；上交所公告证明的是科创50等指数的 9 月 11 日生效，不能外推为 930955 文件已发布。[930955 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)；[上交所三季度调整公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - 两个独立来源天然足以证明最高收盘：**不成立**；仍需同一指数、同一字段、同一交易日集合、同一价格口径及明确容差。
  - 腾讯/东方财富可作为稳定且授权的行情 API：**不成立**；最多是 best-effort 网页源。腾讯端点当前可返回报价文本，但这不证明授权、SLA 或字段契约。[腾讯报价端点](https://qt.gtimg.cn/q=sh600519)
- Verified Facts（已验证事实＋证据）：
  - Plan 第 63-79 行新增了 registry 字段和九指数矩阵，并明确无证据字段为 `NA`；这证明“防造数骨架”存在，但也直接证明 Required Fix 1 的“填实”尚未完成。
  - Plan 第 34、108 行已禁止 ETF/个股代理混入指数收盘回撤，要求同指数双源、交易日/字段/价格口径一致，核验失败显示 NA；Required Fix 5 的降级方向已闭环。
  - Plan 第 35、109 行已把腾讯/东方财富称为未版本化公开网页源，并列出超时、HTTP、解析、字段、连续失败和缓存陈旧；但尚未给出可执行的具体时间/次数阈值。
  - Plan 第 80 行的 930955 验收门包含 `effective_date`、样本数 100、权重和、URL/hash、调入调出差异；这是合格的验收框架，不是当前事实证明。
  - 中证 500 官方 factsheet 提供代码 000905、样本数 500、2026-08-31 指标快照；中证 1000 官方方法提供代码 000852/399852 和编制方法。两者支持身份/快照字段，不支持九指数十年估值分位。[中证500 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)；[中证1000编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf)
  - R1 指出的 SQLite 方向仍仅是能力事实：官方文档说明 SQLite 是轻量磁盘数据库，`connect(timeout=...)` 可等待锁；不能替代 Plan 要求的 Mac Mini 项目验收。[Python sqlite3 官方文档](https://docs.python.org/3.13/library/sqlite3.html)
- External Sources（Web Search / Web Fetch / 官方文档 / 官方 GitHub / 第三方 / 社区反馈，附链接）：
  - 中证官方：930955 factsheet（2026-08-31）、000905 factsheet、000852 编制方案，用于核对指数身份、样本数、调样/快照能力；未用于推断历史序列或 9 月权重。
  - 上交所官方三季度调整公告：明确公告所述科创50等指数于 2026-09-11 收市后生效；未证明 930955 在该公告覆盖范围内。[公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - 腾讯公开端点：本次 Web Fetch 可读到响应，但响应为位置型文本；只能证明当前可访问，不能证明官方授权、稳定性或 SLA。[端点](https://qt.gtimg.cn/q=sh600519)
  - SQLite/Python 官方文档：支持本地数据库、连接超时和事务能力；不替代本项目的并发、WAL、备份恢复实测。[sqlite3 文档](https://docs.python.org/3.13/library/sqlite3.html)
- Competitor Findings（竞品现状＋对本 Plan 的启示）：
  - R1 引用的参考仓库仍只能作为信息架构反例：其 README 已披露示例 history、估算分位、ETF/全 A 代理等边界；Plan 这轮继续坚持 NA 和不得代理是正确方向，但不能因“写了限制”就宣称数据验收完成。[参考仓库 README](https://github.com/wanghoufan/a-share-index-valuation-report#readme)
  - 成功做法应是每张卡同时展示 `asOf/source/status`，并在数据未满足同口径证据门时显示 NA；Plan 已写产品原则，但 registry 尚未产生可交付记录。
- Counter-evidence（反对证据＋成功的相反做法）：
  - 反对“官方没有任何数据”：930955/000905 factsheet 确实给出身份、样本数和日期化基本面快照；成功做法是把它们限定为快照，不越界生成十年分位。[930955 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)
  - 反对“写 NA 就没有产品价值”：当前收盘、官方快照和缓存状态仍可展示；但最高收盘/回撤/估值分位必须按字段独立可用，不能为了卡片完整而补数字。
  - 反对“加入双源字样即可验收”：没有定值 tolerance、交易日 join 规则和缺失降级样例，开发者仍会自行解释，故 Fix 3 尚未闭环。
- Unverified Items（未验证项＋验证方法）：
  - 九指数逐字段 registry：为每个指数实际填入 URL/原始文件、授权依据、覆盖起止日、as-of、价格/估值口径、fallback 和失效等级；逐行检查非 NA 证据。
  - 九指数历史估值分位：取得原始 PE/PB/股息率序列，固定静态/滚动窗口、分位边界、交易日对齐、缺失处理和授权，生成可复算样例。
  - 930955 调样后 closeweight：向中证官方取得生效后的 930955 文件，核对是否确属该指数、effective_date、样本数 100、权重和容差、URL/hash、与旧快照差异；不能用科创50公告替代。
  - 双源最高收盘：每个指数提供两条同源类型的 index-close 序列，明确交易日 inner join/缺日策略、数值容差、抽样/全量范围和失败文案；ETF/个股代理必须负例测试。
  - 腾讯/东方财富：在目标 Mac Mini 网络环境记录最小请求、HTTP/解析/字段坏例、限流/重试/退避、连续失败窗口、缓存陈旧阈值和恢复；第三方字段文档不能替代请求实测。
  - SQLite：在临时开发库完成双连接读写、busy_timeout、WAL checkpoint、重启、异常中断、`.backup`/`VACUUM INTO`、`integrity_check`/`foreign_key_check` 及 WAL 文件边界验收。
- Required Fixes（Planner 必须改项，打回依据）：
  1. **部分闭环，必须补**：把第 67-78 行空矩阵变成可交付 registry；至少明确每个指数当前阶段哪些字段有证据、哪些为 NA，以及 URL/授权/覆盖/口径/失效等级。不能只保留通用字段表。
  2. **框架闭环，事实未闭环**：保留 930955 P0 门，但不得把 `2026-09-11` 当作已被 930955 官方证实的生效日；补“如何确认该公告是否覆盖 930955”的来源判定，并提供生效后官方文件再验收。
  3. **未闭环，必须补**：给 highestClose 双源方案写出确定的日期 join、缺失日策略、数值容差、全量/抽样范围、身份校验和降级负例；不要只写“定义容差”。
  4. **部分闭环，必须补**：给腾讯/东方财富写可测试的 timeout、重试/退避、限流应对、连续失败窗口、缓存最大陈旧时间、恢复条件和状态字段；仍标为未版本化网页源。
  5. **闭环**：currentClose/highestClose 同口径或双源通过才展示回撤，否则 NA＋原因；保留负例验收。
  6. **基本闭环，建议澄清**：明确 PE/PB/股息率分位在证据门前不属于可用 MVP 数值，只能显示 NA；在 Functional Scope/DoD 使用同一措辞，避免“统一展示”被理解为必须有数字。
  7. **闭环为计划要求**：SQLite 实测矩阵、WAL/锁/备份/恢复及完整性检查已列入 DoD；开发前仍须实际验收，不能在 Plan 阶段声称已通过。
  8. **闭环**：`confirmed` 只表示人工核实已成交/已卖出成交，部分成交/撤单不进 confirmed。
  9. **未闭环，必须补**：将本轮 R2 结论、9 条闭环状态、外部证据缺口和新的 Readiness Score 同步到 Plan 的 Research Review Round；不能继续写 R1/61 和自评 76 作为当前状态。
- Plan Readiness Score（分项打分＋合计，口径以 PRODUCT_PLAN.template.md 为准）：
  - 产品目标与用户需求（20）：17/20。计划/事实、成交语义、四生命周期和本地单用户边界清楚；交易单位、费用和成交价仍待人确认。
  - 核心方案完整性（20）：15/20。账本、冻结、恢复、NA 降级和数据门已覆盖；registry 仍是空骨架，双源算法和行情失败契约不够执行化。
  - 外部事实与竞品验证（20）：10/20。已核实官方快照、身份和网页端点可访问；九指数实际历史序列/授权、930955 调样后权重和东财 E2E 仍未闭环。
  - 技术可行性（15）：13/15。Python/SQLite 方向合理，Plan 已列实测矩阵；项目级并发、备份恢复和 API 回归尚未执行。
  - 风险与异常场景（10）：9/10。禁止造数、双源失败、缓存陈旧、成交语义和生产授权边界清楚；行情阈值仍不具体。
  - 开发范围与 DoD（10）：8/10。P0/P1/P2 和多数 DoD 清晰；source registry 与研究验收尚未形成可交付物，R2 状态未同步。
  - 未决问题（5）：2/5。人类仍需拍板 5 项 blocking，另有外部数据验收和 3 条 Planner 口径缺口。
  - 合计：**74/100**
  - Gate：不满足 `>=90`、P0=0、blocking P1=0、关键事实已验证；**FAIL，不得进入 WAITING_HUMAN_APPROVAL，不得派 Builder**。
- Human-only Decisions（只需人类拍板项）：
  1. 是否接受无合法、同口径历史序列时显示 NA，并暂不承诺完整估值分位/回撤；建议接受。
  2. 是否接受腾讯/东方财富只做 best-effort 未版本化网页行情源；建议接受并保留缓存降级。
  3. 是否确认 `project_slug=dividend-portfolio`，以及普通 A 股 100 股整手与特殊交易单位范围。
  4. V1.3 是否暂不计佣金、税费、分红、公司行动和部分成交；建议暂不计，另立 Change C。
  5. 实际成交价必填/可选/参考价的选择；建议可选并保留 `reference_price` 标记。
  6. 是否首版纳入中证 A500、何时授权正式 Docker/SQLite 目录、备份和调度；均非当前开发放行条件。
- Next Action：（回 Planner 修订 / 进 WAITING_HUMAN_APPROVAL 找人）
  - **回 Planner 修订**：先补齐逐指数 registry 可交付记录、双源回撤定值算法、行情失败阈值，并同步 R2/74 分与 5/9 闭环状态；修订后再做 R3 Research Review。当前剩余 blocking **不只是人类决策与外部数据验收**，因此不能进 Human Gate。
