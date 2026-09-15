# RESEARCH_REVIEW（Phase1 专用；内部 role ID `product-reviewer` 不变）

- Plan Version（评的是哪版 PRODUCT_PLAN）：PRODUCT_PLAN_V1.0
- Review Round（第几轮）：第0轮（Research Review R1）
- Result：（FAIL＋关键外部事实、历史序列与回撤双源方案尚未闭环；SQLite 方向可行但验收边界未写实）
- P0 / P1 / P2：
  - P0：
    1. 九指数（沪深300/中证500/中证1000＋六红利）的历史 close、PE/PB/股息率分位必须建立逐指数 source registry：来源、授权/使用条件、覆盖起止日、价格口径、估值口径、更新责任、失效降级。当前 Plan 只列为待核验，不能支撑 DoD 或派 Builder。
    2. 930955 的 2026-09 调样后 closeweight 当前是否已更新，尚未由中证官方可审计页面/文件证明。官方可核验的是 2026-08-31 factsheet 快照，不能当作 9 月调样后权重。
    3. 回撤“最高收盘双源核验”不能只写抽样要求。必须定义同一指数、同一收盘序列、同一价格口径、日期对齐和容差；SPCLLHCP 的 ETF 代理不能与指数 close 混为同一序列。无法满足时应降级为暂无回撤。
    4. 腾讯→东方财富公开网页端点可用性已部分验证，但未验证官方授权、稳定 SLA、限流和响应契约；必须标为未版本化网页接口并加缓存/失效策略。
  - P1：
    1. 把“当前收盘”与“实时行情”分开定义；收盘回撤只能使用已闭市交易日的指数 close。
    2. 历史 PE/PB/股息率分位从 MVP 拆出，除非每个指数有可复现、合法且同口径序列；无授权序列统一显示暂无数据。
    3. 930955 增加生效日、缓存版本、旧快照保留和新快照验收：样本数、权重和、effective_date、source_url 全部通过才替换。
    4. SQLite DoD 增加 Mac Mini 实测：多连接读写、busy_timeout、WAL checkpoint、进程重启、备份含不含 -wal/-shm、恢复后完整性/外键检查。
    5. 将“确认已下单”全量改为“确认已成交/已卖出成交”，并明确部分成交/撤单首版不支持或另立 Change C。
  - P2：
    1. 中证A500、真实历史 sparkline、雷达图和风险溢价分位。
    2. macOS 定时备份/异地副本、费用税费、公司行动、券商导入和程序化交易适配。
- Key Assumptions（逐条列＋是否成立）：
  - 单用户、低并发、Mac 本机 HTTP 服务＋SQLite：基本成立；锁争用、备份和恢复仍需项目级实测。
  - Python 标准库可提供 SQLite：成立。本机实测 Python 3.9.6、macOS 26.6 arm64、SQLite 3.51.0，sqlite3 可用并可开启外键；WAL、恢复和并发不是自动成立。
  - 腾讯和东方财富可作为行情主备：部分成立；端点生态可用，但均属未版本化公开网页接口，不具备已证实的公开契约、SLA 或授权声明。
  - 官方可稳定提供九指数长期 close 与估值分位：不成立/未证实。官方 factsheet 能提供某日期快照和方法说明，但本次未找到覆盖九指数、可直接复现的十年估值分位授权序列。
  - 930955 2026-09 调样后 closeweight 已进入当前缓存：未验证，不能假定成立。
  - 两个独立来源足以证明最高收盘：不充分。只有指数身份、字段、交易日、价格口径和历史覆盖完全可比时才成立。
  - confirmed transaction 可代表真实持仓：只有 UI 明确为成交且用户人工核对时成立；现有材料仍有“已下单”歧义。
- Verified Facts（已验证事实＋证据）：
  - 中证官方 930955 factsheet 标注代码 930955、样本数 100、调样频率每季度，并给出截至 2026-08-31 的指标/成分权重快照；证明官方快照存在，但不证明 9 月调样后文件已更新。[930955 官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)
  - 上交所公告显示，2026 年三季度部分中证指数样本调整于 2026-09-11 收市后生效；该公告未提供 930955 调样后 closeweight 的可审计快照。[上交所三季度定期调整公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - 中证500官方 factsheet 可提供代码、调样频率、样本数及某日期 PE/PB/股息率快照；中证1000官方方法说明代码为 000852/399852 及选样逻辑。这些是定义/快照证据，不是历史估值分位序列。[中证500 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)；[中证1000编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf)
  - 腾讯公开行情端点本次直接返回了带时间戳的贵州茅台报价文本，说明端点当前可访问；返回为非 JSON、字段位置型文本。[腾讯 qt.gtimg.cn 实测端点](https://qt.gtimg.cn/q=sh600519)
  - 参考仓库 README 明确：付费连接器不可用；部分分位为估算/近三年或近五年近似；history 为示例走势；回撤取 MAX(high)；标普指数使用 ETF 代理。这些限制与 Plan 的“不得充数”判断一致，不能把该仓库数据当生产事实。[参考仓库 README](https://github.com/wanghoufan/a-share-index-valuation-report#readme)
  - Python 官方文档确认 sqlite3.connect timeout 及标准库接口；SQLite 官方文档确认 WAL 可持久化、读写并发仍可能返回 SQLITE_BUSY。[Python sqlite3 文档](https://docs.python.org/3.13/library/sqlite3.html)；[SQLite WAL 文档](https://www.sqlite.org/wal.html)
- External Sources（Web Search / Web Fetch / 官方文档 / 官方 GitHub / 第三方 / 社区反馈，附链接）：
  - 官方：中证指数 930955 factsheet、000905 factsheet、000852 编制方案、中证指数首页，用于确认指数身份、方法、快照能力和官方免责声明；未用于推断完整历史序列。[中证指数首页](https://www.csindex.com.cn/)
  - 官方：上交所三季度调样公告，用于确认部分指数 2026-09-11 生效；未找到其中含 930955 当前 closeweight 文件。[公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20260828_10830242.shtml)
  - 实测公开端点：腾讯报价成功；东方财富 push2/push2his 在 Web Fetch 环境触发安全限制，因此只能确认接口生态和格式说明，不能声称已完成东方财富 E2E 验证。[东方财富端点字段说明](https://github.com/WangYang-Rex/eastmoney-data-sdk/blob/main/docs/API_FIELDS.md)
  - 第三方兼容性记录明确指出腾讯/东方财富端点是 observed public endpoints、unversioned、无 upstream contract/SLA/rate-limit policy；只能作为 best-effort 行情源。[cnstock-cli compatibility](https://github.com/fatecannotbealtered/cnstock-cli/blob/main/docs/COMPATIBILITY.md)
  - 参考仓库：[GitHub README](https://github.com/wanghoufan/a-share-index-valuation-report#readme)
- Competitor Findings（竞品现状＋对本 Plan 的启示）：
  - 参考仓库在信息架构、数据与展示分离、时效提示和响应式呈现上是成功的相反做法：它显式标出数据局限。Plan 可借鉴结构，但应保留“数据等级/暂无数据”。
  - 其价格回撤使用 MAX(high)，且标普红利低波50使用 ETF 代理；这是本 Plan 需要反向修正的失败口径，不能作为收盘回撤实现。
  - 其估值分位依赖 Wind/理杏仁/雪球/同花顺公开披露或估算，README 已说明不是稳定权威通道；有页面有数字不等于有授权、可复现、可验收。
- Counter-evidence（反对证据＋成功的相反做法）：
  - 反对“官方数据完全不可得”：官方确实提供 factsheet、方法和日期化指标快照；成功做法是把它们当作带 as_of 的核验快照，不越界推导十年分位。
  - 反对“SQLite 在 Mac Mini 不可行”：本机实测标准库可用，Python 官方提供 timeout，SQLite 官方支持 WAL。成功做法是单写事务、短事务、显式 busy timeout、健康检查、可验证备份与恢复。
  - 反对“主备行情不能用”：腾讯端点本次可返回实时文本；成功做法是 best-effort、保存 fetchedAt、严格校验字段并允许缓存降级，不称其为官方稳定 API。
- Unverified Items（未验证项＋验证方法）：
  - 九指数历史 close 的完整覆盖、收盘定义、缺失交易日和授权：逐指数取得实际文件/接口响应，记录 URL、首末日期、字段和许可条件并生成覆盖报告。
  - 九指数 PE/PB/股息率历史分位：要求可复现原始序列及计算公式，分别验证滚动/静态口径、分位边界和日期。
  - 930955 调样后 closeweight：生效日后取得中证官方成分/权重文件，校验 effective_date >= 2026-09-11、100只样本、权重和约100%、与旧快照差异并保存 hash。
  - 东方财富实时/历史端点：在 Mac Mini 项目网络环境执行最小请求，记录响应、重试和连续失败；第三方文档不能替代 E2E。
  - 回撤双源：为每个指数指定两条独立且同为 index-close 的序列，比较交易日集合与最高值；ETF/个股/盘中 high 判定不合格并降级。
  - SQLite：在 Mac Mini 用临时开发库实测双浏览器读、连续写、重启、WAL checkpoint、backup/VACUUM INTO、恢复后完整性检查；不能触碰正式数据库。
- Required Fixes（Planner 必须改项，打回依据）：
  1. 增加逐指数 source registry 和可交付数据矩阵，将 close、估值绝对值、估值分位、回撤、权重分别列来源/授权/覆盖/日期/口径/失效等级；无证据明确为 NA。
  2. 将 930955 2026-09 调样后 closeweight 改成未决 P0，补充生效日后官方文件验收；验收前不得替换旧缓存或生成新计划。
  3. 重写 highestClose 双源方案：双源必须同一指数收盘序列；定义对齐、容差、抽样范围、失败降级；删除 ETF 代理可证明指数最高收盘的表述。
  4. 将腾讯/东方财富定位为未版本化公开网页行情源，新增契约不保证、字段校验、限流/超时、连续失败和缓存陈旧标记；不要称其为官方 API。
  5. 收紧回撤 DoD：只有 currentClose 与 highestClose 同源/同口径或通过双源核验才展示百分比，否则显示暂无数据及原因。
  6. 收紧估值分位 DoD：逐指数提供原始序列、公式、分位边界和授权证据；否则移出 V1.3 MVP 或明确 NA，不得用参考仓库/媒体估算填充。
  7. SQLite DoD 加入 Mac Mini 实测矩阵和恢复验收，包括 WAL 文件随库备份、busy_timeout、单写者策略、integrity_check、foreign_key_check 和异常中断恢复。
  8. 统一成交语义和状态机：删除“已下单”作为 confirmed 的含义；确认项只代表人工核实已成交，部分成交/撤单明确拒绝或 Change C。
  9. 将 Plan 当前 75/100 分项与本轮研究证据同步；外部事实与竞品验证、关键未决问题、技术验收未闭环时不得进入 Human Gate。
- Plan Readiness Score（分项打分＋合计，口径以 PRODUCT_PLAN.template.md 为准）：
  - 产品目标与用户需求（20）：16/20。闭环清楚，但下单/成交语义、费用和成交边界仍影响账本正确性。
  - 核心方案完整性（20）：13/20。流程、冻结、恢复和账本完整；数据注册表、双源细则和降级契约不足。
  - 外部事实与竞品验证（20）：6/20。参考仓库限制已核实、官方快照可得；九指数历史序列/分位授权、930955 调样后权重、东财 E2E 均未闭环。
  - 技术可行性（15）：11/15。Mac Mini 的 Python 3.9.6＋SQLite 3.51.0 能力成立；项目级并发、备份恢复和现有 API 回归未验证。
  - 风险与异常场景（10）：7/10。已识别很多风险，但行情端点契约、双源失败和成交语义仍留给开发阶段。
  - 开发范围与 DoD（10）：7/10。范围与测试夹具较全；外部数据研究与账本闭环仍过宽，验收条件需执行化。
  - 未决问题（5）：1/5。多个 blocking 事实/人类决策未关闭。
  - 合计：61/100
  - Gate：不满足 >=90、P0=0、blocking P1=0、关键事实已验证；不得进入 WAITING_HUMAN_APPROVAL，不得派 Builder。
- Human-only Decisions（只需人类拍板项）：
  1. 是否接受无合法、同口径历史序列时显示暂无数据，并把估值分位/回撤部分移出 MVP；建议接受。
  2. 是否接受腾讯/东方财富仅作为 best-effort 公开网页行情源，而非稳定/授权 API；建议接受并保留缓存降级。
  3. confirmed 是否严格代表已成交而非已报单；建议严格采用已成交。
  4. 是否批准首版不计费用、税费、分红、公司行动和部分成交；建议明确排除并另立 Change C。
  5. 是否批准在用户授权后进行 Mac Mini 正式目录/备份/定时任务配置；当前只能开发库验证。
- Next Action：（回 Planner 修订 / 进 WAITING_HUMAN_APPROVAL 找人）
  - 回 Planner：按 9 条 Required Fixes 修订 PRODUCT_PLAN_V1.0，先补 source registry、930955 生效后权重验收、同口径回撤双源方案和 SQLite 实测验收；修订后再进入下一轮 Research Review。当前不建议进 Human Gate，不派 Builder。

