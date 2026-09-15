# PRODUCT_PLAN（Phase1）｜红利打新底仓计算器 V1.3

- Plan Version：PRODUCT_PLAN_V1.0
- PROJECT_PHASE：PLAN
- Product Goal：在不退化 V1.2 六大红利指数、官方成分/权重缓存、腾讯→东方财富→本地缓存行情和 10 万/20 万底仓测算能力的前提下，增量升级为单人本地个人红利底仓管理工具，完成“估值与市场环境→首次建仓/追加/再平衡/清仓→冻结下单计划→手机辅助下单→人工确认→真实持仓与策略现金追溯→未完成批次恢复”闭环。系统只做计划、记录和核对，不自动决定或执行真实证券交易。
- Target Users：
  - 在 Mac Mini 上自托管、通过桌面浏览器操作、使用银河证券手机 APP 人工下单的单一投资者。
  - 按指数权重建立打新底仓、长期追加或调仓，重视官方数据、来源日期、离线兜底和可追溯性。
  - 不面向公网多用户、机构交易团队、高频/自动交易或需要实时跨设备协作的用户。
- Problem：
  - V1.2 能完成指数比较、成分读取、行情获取和单次资金测算，但建议买入与真实持仓尚未形成可追溯边界。
  - 单次计算没有冻结、恢复的下单批次，刷新或重启后无法可靠延续逐只处理进度。
  - 缺少投资周期、确认交易、真实持仓、策略现金和历史记录，无法安全支持长期追加、再平衡与清仓。
  - 估值看板缺少大/中/小盘市场环境与严格按收盘价计算的历史回撤；绝对值、分位、来源、日期和口径需统一治理。
  - V1.3 输入包含付费/不可稳定获取的历史数据愿望及生产基础设施动作，若不收口会导致虚构数据、过度建设或越权操作。
- Core Value：
  - 计划与事实分离：只有用户明确确认成交的记录才进入真实交易账本。
  - 可恢复：冻结计划、逐只状态、持仓和策略现金以 SQLite 持久化。
  - 可解释：权重、价格、取整、配置偏差、低配优先和持仓变化均有透明公式。
  - 可核验：字段保留 source、dataDate、fetchedAt、officialUrl、fallbackSource、cacheStatus，官方入口和旧有效缓存不退化。
  - 可维护：沿用 Python 标准库本地服务和既有前端，增量引入 SQLite Migration，不接 Supabase 或券商接口。
- User Flow：
  1. 用户通过本地 HTTP 服务进入首页；系统检测缓存、SQLite 和未完成批次。
  2. 用户先查看沪深300/中证500/中证1000市场环境，再查看六大红利指数及其估值、回撤、来源和日期。
  3. 用户选择投资周期及首次建仓、追加投资、全面再平衡或清仓退出。
  4. 系统依据最新可用权重、行情、真实持仓、策略现金和交易单位生成透明预览；关键数据待核验时警告或阻断，不补造数。
  5. 用户确认生成不可静默变化的计划快照；需要更新时显式生成新 revision。
  6. 用户进入同应用下单页，使用 checklist/单只专注模式，把股票代码和数量复制到手机银河 APP 人工操作。
  7. 用户逐项确认已成交/已卖出、跳过或待复核；只有确认项写入 transaction。
  8. 批次完成后查看确认清单、CSV、执行记录、当前持仓和策略现金；清仓后周期 CLOSED，新投资创建新 cycle_id。
- Functional Scope：
  - 估值看板增加沪深300、中证500、中证1000市场层级；中证A500先列为可选 P2；六大红利指数及原顺序保持不变。
  - 统一展示：指数/代码、当前收盘、近10年或成立以来最高收盘与日期、回撤、PE/PB/股息率及分位、可靠时才展示风险溢价分位、联合解释、数据日期/来源/抓取时间和官方核验；PE/PB/股息率分位在证据门前只显示 `NA/暂无数据`，不视为 MVP 必须有数值。
  - 回撤统一 `currentClose / highestClose - 1`；不足10年标“成立以来”。`currentClose` 与 `highestClose` 必须来自同一指数收盘序列；双源核验要求同指数、同字段、同交易日、同价格口径，定义日期对齐和数值容差。核验失败不得展示回撤数值，只显示“暂无数据/待核验”及原因。
  - 行情保持腾讯主源→东方财富备用→最近成功本地缓存；两者定位为未版本化公开网页行情源，不承诺官方 API、SLA 或字段稳定性。普通价格只读，手动覆盖放入默认隐藏的高级异常处理区并留痕；请求超时、HTTP/解析/字段校验失败、连续失败次数和缓存陈旧状态必须可见。
  - 实现投资周期、首次建仓、追加投资（只买不卖、低配优先）、全面再平衡（只生成 BUY/SELL 计划）和清仓退出（逐笔人工确认）。
  - 实现冻结快照、revision、未完成批次恢复、checklist、单只模式、复制代码/名称/数量/单行记录、PENDING/CONFIRMED/SKIPPED/REVIEW 四态和完成门禁。
  - SQLite 保存 cycles、batches、order_items、transactions、cash ledger；持仓默认从 confirmed transactions 聚合，可重建并一致性校验。
  - 建立 `db/migrations/`、`db/schema.sql`、schema version；开发库与生产库隔离，正式库不进 Git；验证 foreign keys、WAL、busy timeout。
  - 提供 SQLite `.backup` 或 `VACUUM INTO` 手动/可调度入口及隔离恢复流程；生产定时任务与正式目录创建须另行授权。
  - 保留 V1.2 HTTP/缓存能力和 CSV 导出；`file://` 仅作降级演示，不承诺 V1.3 账本写入和恢复。
- Out of Scope：
  - 银河 APP 逆向、私有接口、密码管理、自动提交、自动卖出、AI 自动买卖；最多保留 disabled/no-op BrokerAdapter。理由：无官方授权且真实交易不可逆。
  - Supabase 双主库、Auth、Realtime、公网多人服务、原生手机 APP、项目内跨设备剪贴板。理由：单人本地场景不需要，增加维护面。
  - 购买或绕过 Wind/理杏仁/iFinD；不得把参考项目示例 `history`、ETF 代理、`MAX(high)` 冒充正式十年收盘/估值序列。
  - 无可靠授权历史序列时强行计算风险溢价分位、补齐全部十年分位或输出黑箱评分；缺失必须如实展示。
  - 未授权创建/迁移/覆盖正式 Docker 部署副本、DockerData、DockerBackups、生产数据库、容器、端口或删除历史备份。
  - 佣金、税费、分红、公司行动、部分成交、撤单、券商对账单导入及高并发/多实例/复杂权限；需要时另立 Change C。
- Technical Approach：
  - 保留 `server.py + index.html + cache/` 稳定链路，增量增加 SQLite、Migration runner、Repository/Service 和 JSON API，不重写已验证的 XLS/行情/缓存逻辑。
  - 后端继续 Python 标准库 HTTP 服务与 `sqlite3`；浏览器只能通过 API 访问数据库。建议新增 cycles、batches、order-items、transactions、holdings、cash、valuation/quotes 路由，并做事务、幂等和状态校验。
  - 同源独立路径建议 `/orders/<batch_id>`、`/holdings`、`/history`，刷新后由服务端恢复；前端按模块拆分，避免继续把全部业务堆进单脚本。
  - 金额使用整数分或 Decimal 语义，股数使用整数；计划保存输入、输出、公式版本。追加投资以持仓市值+策略现金+新增资金计算目标缺口，仅向低配项分配 BUY。
  - 生成批次时冻结权重版本/日期、行情、来源/时间、目标金额、建议数量、偏差和算法版本；刷新行情不得改建议股数；重算只生成新 revision，已确认项不可改写。
  - 持仓为 `SUM(CONFIRMED BUY) - SUM(CONFIRMED SELL)`；策略现金采用追加式事件账本，不能只存不可追溯余额。
  - 建议 `project_slug=dividend-portfolio`、数据库 `dividend-portfolio.db`；尚未获确认前仅作开发占位，不创建正式目录。正式路径遵守 `DockerData/<project_slug>/db/` 与 `DockerBackups/<project_slug>/sqlite/`，通过环境变量注入。
- Data / API：
  - 沿用 registry 中已验证的五个中证红利指数官方 factsheet/方法/成分权重入口及 SPCLLHCP 官方页/方法入口；未取得直链的文件明确记 `NA`，不得用 ETF 或个股代理替代指数收盘序列。行情沿用腾讯、东方财富、本地 `cache/quotes.json`，并按未版本化公开网页行情源处理。
  - 保持现有 `/api/health`、`/api/cache-status`、`/api/holdings`、`/api/prefetch`、`/api/weight`、`/api/quotes`、`/api/save-parsed` 语义；新增业务 API 不得破坏旧接口。
  - 新对象为 cycle、batch、order_item、transaction、cash_event；标识由服务端生成，写请求校验且记录 created_at/updated_at。
  - 三个宽基及九指数历史 close、估值分位、风险溢价来源/授权/覆盖尚未完成核验；开发前需完成下方逐指数 source registry 与数据矩阵，不能用参考仓库数据充数。无证据字段统一记 `NA`，不因 UI 需要补造数。
  - 930955 的 2026 年 9 月调样是否已进入当前 closeweight 尚未核验，是数据 P0；失败时保留旧快照并标 stale/待核验，不混合日期。只有通过官方文件验收门才可替换缓存。
- Source Registry / 数据矩阵（V1.3 开发前必须填实；当前已验证记录与 `NA` 明确分开）：
  - 通用字段：`indexCode`、`indexName`、`field`、`value/series`、`sourceType`、`sourceUrl`、`license/usageBasis`、`coverageStart`、`coverageEnd`、`asOf`、`fetchedAt`、`price/valuationMethod`、`fallback`、`status`、`failureGrade`、`evidenceNote`。
  - Curl Evidence Log（本轮实际只读抓取；抓取时间均为 `2026-09-15T18:55:42+0800`；先经配置代理失败，再取消 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 重试）：

    | ID | URL | fetchedAt | HTTP | bytes | sha256 | curl 结果/响应样例 |
    |---|---|---|---:|---:|---|---|
    | E01 | https://www.csindex.com.cn/ | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E02 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E03 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=000905 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E04 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E05 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E06 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269_Index_Methodology_cn.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E07 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=H30269 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E08 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930740factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E09 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930740_Index_Methodology_cn.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E10 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=930740 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E11 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E12 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=930955 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E13 | https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/ | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E14 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/931468factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E15 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=931468 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E16 | https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/931446factsheet.pdf | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E17 | https://www.csindex.com.cn/#/indices/family/detail?indexCode=931446 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E18 | https://qt.gtimg.cn/q=sh600519 | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；端点响应样例 NA；取消代理后 DNS `Could not resolve host` |
    | E19 | https://github.com/WangYang-Rex/eastmoney-data-sdk/blob/main/docs/API_FIELDS.md | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |
    | E20 | https://github.com/wanghoufan/a-share-index-valuation-report | 2026-09-15T18:55:42+0800 | 000 | 0 | NA | FAIL；取消代理后 DNS `Could not resolve host` |

  - Evidence status：20 行、20 个唯一 URL；本轮 `PASS=0`、`FAIL=20`，所有 hash 均为 `NA`。失败原因不改变已有 Web/官方文档研究结论，但本机 curl 未能取得新的字节证据；NA 字段（历史 close、估值分位、930955 生效后文件等）保持 NA，不能以失败抓取冒充已验证。
  - 证据等级：`A=官方原始文件/官方方法`；`B=官方页面快照`；`C=可访问但未版本化的公开网页源`；`NA=本轮没有可审计证据`。授权字段只记录“公开查阅/项目本地缓存依据”；未取得再分发许可时不得对外分发原始数据。
  - 逐指数可交付 registry（URL、授权/使用依据、覆盖、口径、失效等级均写明；历史序列/分位没有证据则保留 `NA`）：

    | 指数/代码 | 已验证身份、方法、成分/权重来源 URL | 授权/使用依据 | 已验证覆盖与口径 | 当前 close / 历史 close | 估值绝对值 / 分位 | 失效等级与降级 |
    |---|---|---|---|---|---|---|
    | 沪深300 / 000300、399300 | [中证指数官方入口](https://www.csindex.com.cn/)；方法/成分/权重文件：`NA`（本轮未取得可审计直链） | 官方入口公开查阅；再分发许可 `NA` | 身份入口已验证；close/估值覆盖与 price/valuationMethod `NA` | `NA / NA` | `NA / NA` | P0；显示 NA，不得用代理 |
    | 中证500 / 000905、399905 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905factsheet.pdf)；[中证指数官方入口/成分权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=000905)；官方方法直链 `NA`、下载文件 `NA` | factsheet/官方入口公开查阅；再分发许可 `NA` | 以文件实际内容为准：factsheet 快照截至 2026-08-31；curl 证据见 E02/E03（fetchedAt=2026-09-15T18:55:42+0800，HTTP 000，hash NA）；指数 close 历史覆盖 `NA`；官方 PE/PB/股息率为快照口径，非十年分位 | `NA / NA` | 官方快照可记录；分位 `NA / NA` | P0；旧缓存可读，标 stale |
    | 中证1000 / 000852、399852 | [官方编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf)；factsheet直链 `NA`；成分/权重下载直链 `NA` | 官方方法公开查阅；再分发许可 `NA` | 方法/身份已验证；历史 close、估值和权重覆盖 `NA` | `NA / NA` | `NA / NA` | P0；显示 NA |
    | 红利低波 / H30269 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269factsheet.pdf)；[官方编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269_Index_Methodology_cn.pdf)；[官方成分/权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=H30269)，具体下载文件 `NA` | 官方文件公开查阅；再分发许可 `NA` | 以文件实际内容为准：factsheet 快照截至 2026-08-31；curl 证据见 E05/E06/E07（fetchedAt=2026-09-15T18:55:42+0800，HTTP 000，hash NA）；方法为股息率加权、样本50、年度调样；历史 close/估值分位 `NA` | `NA / NA` | factsheet PE/PB/股息率快照可记录；分位 `NA / NA` | P0；旧快照＋stale |
    | 300红利低波 / 930740 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930740factsheet.pdf)；[官方编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930740_Index_Methodology_cn.pdf)；[官方成分/权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=930740)，具体下载文件 `NA` | 官方文件公开查阅；再分发许可 `NA` | factsheet 快照截至 2026-08-31；方法为股息率加权、样本50、半年调样；历史 close/估值分位 `NA` | `NA / NA` | factsheet PE/PB/股息率快照可记录；分位 `NA / NA` | P0；旧快照＋stale |
    | 红利低波100 / 930955 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930955factsheet.pdf)；[官方成分/权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=930955)；官方方法及生效后下载文件 `NA` | 官方文件公开查阅；再分发许可 `NA` | factsheet 快照截至 2026-08-31；样本100、季度调样；2026-09 生效日以官方文件 `effective_date` 为准 | `NA / NA` | factsheet 快照可记录；分位 `NA / NA` | **P0**；验收门未过不得替换/生成计划 |
    | 标普中国A股大盘红利低波50 / SPCLLHCP | [S&P DJI 官方指数页](https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/)；页面列出的 [S&P Low Volatility High Dividend 方法入口](https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/)；成分/权重原始下载 `NA` | 官方页面公开查阅；方法/数据再分发许可 `NA`；515450 只作为产品关联事实，不是指数 close 代理 | 官方页面确认 50 只低波高股息大盘股；历史 close/估值覆盖 `NA` | `NA / NA` | `NA / NA` | P0；不以 ETF/个股代理，显示 NA |
    | 红利质量 / 931468 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/931468factsheet.pdf)；[官方成分/权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=931468)；官方方法及下载文件 `NA` | 官方 factsheet 公开查阅；再分发许可 `NA` | factsheet 快照截至 2026-03-31；样本50、半年调样；历史 close/估值分位 `NA` | `NA / NA` | factsheet 股息率快照可记录；PE/PB及分位 `NA / NA` | P0；显示 NA |
    | 东证红利低波 / 931446 | [官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/931446factsheet.pdf)；[官方成分/权重入口](https://www.csindex.com.cn/#/indices/family/detail?indexCode=931446)；官方方法及下载文件 `NA` | 官方 factsheet 公开查阅；再分发许可 `NA` | factsheet 快照截至 2026-08-31；样本100、半年调样；历史 close/估值分位 `NA` | `NA / NA` | factsheet PE/PB/股息率快照可记录；分位 `NA / NA` | P0；显示 NA |

  - 跨指数行情记录：腾讯实测 [qt.gtimg.cn/q=sh600519](https://qt.gtimg.cn/q=sh600519)，覆盖单次股票实时文本报价，位置型非 JSON；授权/稳定契约 `NA`，等级 C。东方财富 `push2/push2his` 的字段参考 [第三方字段说明](https://github.com/WangYang-Rex/eastmoney-data-sdk/blob/main/docs/API_FIELDS.md)，本轮项目环境 E2E `NA`，等级 C。两者仅 best-effort，不提供历史指数 close 或估值分位证据。
  - 参考资料记录：[参考仓库 README](https://github.com/wanghoufan/a-share-index-valuation-report#readme) 明确 `history` 为示例、部分分位为估算/短区间、回撤使用 `MAX(high)`、部分价格用 ETF/全 A 代理；授权/覆盖不足，等级 NA，只能作为限制声明，不得作为生产数据。
  - 证据门：每个非 `NA` 字段必须有可打开 URL/原始文件、授权或公开使用依据、覆盖日期和口径说明；历史分位还必须保存原始序列、计算公式和分位边界。任何一项缺失，该字段保持 `NA`，相关 UI 显示“暂无数据”。
  - 证据门 B 例外（Change B，人类 2026-09-15 拍板）：允许引入**公开披露的估算值**（如百分位 baifenwei.com、股叉叉 guchacha.com、理杏仁、雪球、同花顺等公开页），但必须满足 ① 每格标 `估算` 且悬停可见来源名＋日期＋URL；② 与课程层、官方层**分区展示、绝不合并**（同一列可并存但各自标注口径）；③ 估算分位须注明观察期口径（如“近 10 年”或“上市以来”），与课程的 10 年分位**不得机械等同**；④ 找不到来源的字段仍保持 `NA`，禁止编数、禁止用 ETF/个股/盘中 high 代理。宽基（000300/000905/000852）的 PE/PB 分位与股息率分位即按此例外落盘；宽基风险溢价分位仍无授权同口径来源，故显示 `NA`。
  - highestClose 双源定值算法：`sourceA`、`sourceB` 必须分别声明同一 `indexCode/indexName`、价格指数（非全收益/净收益）、币种和收盘字段；先做身份校验，再按交易日对两序列执行 `inner join`。未同时出现的日期不进入计算；若并集缺失率超过 0.5%，或任一缺失日落在任一来源的候选最高 20 个收盘日，判定失败。所有 joined 日期须满足 `abs(closeA-closeB) / max(abs(closeA),abs(closeB)) <= 0.10%`；全量 joined 区间用于生产最高值，另抽查端点、最高点前后各 5 日及随机 20 个交易日。任一身份不符、字段误用、缺日超阈值或容差失败，回撤为 `NA`，UI 显示“暂无数据/双源核验失败”并保留错误原因。
  - 双源负例验收：把 ETF 收盘、个股收盘、盘中 `high`、全收益指数或代码不一致的序列作为 `sourceB`，必须被身份校验拒绝；人为删除一个交易日、制造超过 0.10% 的差异、或改变币种后，必须进入失败降级，不得静默取较高值。
  - 行情可测试契约：腾讯和东方财富单次请求 `timeout=3s`；每个主/备源最多重试 2 次，退避 `0.5s → 1.5s`，不对失败请求无限重试。10 分钟滚动窗口内同一源连续 3 次失败即标 `DEGRADED` 并切换下一源；最近成功缓存最大陈旧时间为 72 小时，且跨越 3 个交易日仍未恢复则标 `STALE_BLOCKED`，不得伪装实时。恢复条件为同一源连续 2 次请求同时通过 HTTP、解析、字段范围和 `dataDate` 校验，才从 `DEGRADED/STALE` 回到 `LIVE/FRESH`。每条行情必须保存 `source`、`status`、`dataDate`、`fetchedAt`、`ageSeconds`、`attempts`、`errorCode`、`cacheAgeSeconds`、`stale`；状态至少包括 `LIVE`、`DEGRADED`、`CACHE`、`STALE_BLOCKED`、`MANUAL_OVERRIDE`。
  - 930955 官方文件验收门：以中证官方 930955 成分/权重文件自身的 `effective_date` 为准，不预设日期下限。公告只能作为候选线索；必须在公告正文/附件或中证官方文件中核对明确的指数代码/名称，确认公告确实覆盖 930955 后，才可采用其生效信息。再确认样本数 100、权重和在约定容差内、文件日期/URL/hash、与旧快照的调入调出差异，并单独记录 closeweight 生效口径；门未通过不得替换旧缓存或生成新计划。
- Key Assumptions：
  - 已确认单用户、低写入并发、单机本地 Web；SQLite 与 Python 标准库适配当前规模。
  - 已确认真实下单由用户在银河 APP 完成；项目只辅助复制、计划和人工确认。
  - 已确认正式访问为本地 HTTP；`file://` 受跨域和持久化限制。
  - 待验证当前开发目录是否是唯一源码；旧 HANDOFF 的 Downloads 路径是否仅为旧副本记录。
  - 待确认 `dividend-portfolio`、正式端口/公开 URL、生产目录授权。
  - 待验证跨设备剪贴板稳定性、银河是否只需纯股票代码、账户覆盖的交易板块及普通A股100股整手规则。
  - 已确定 `confirmed` 只代表用户人工核实“已成交/已卖出成交”，不代表已下单或已报单；部分成交、撤单、改量首版拒绝写入 `confirmed`，需求改变时另立 Change C。
  - 待确认 V1.3 初期不计费用、税费、分红和公司行动；组合资产/现金仅作参考。
  - 未验证九指数是否都能获得长期、稳定、合法、同口径的 close 与估值分位数据；在 source registry 证据门通过前均按 `NA` 处理。参考仓库已明确 `history` 为示例，旧回撤说明使用 `MAX(high)`，均不得直接复用。
  - 已确认 SQLite 标准库在当前 Mac Mini 可用，但 WAL、锁等待、备份和恢复仍需临时开发库实测；不得以环境可导入替代项目验收。
- Competitor / Research Summary：
  - 参考仓库 `wanghoufan/a-share-index-valuation-report` 可借鉴两层指数信息架构、JSON 与展示分离、时效提示、来源/口径说明、响应式卡片和零依赖轻量图表。
  - 其 README 明确 `history` 是示例走势，部分数据为 ETF/全A代理、非十年或估算分位，旧回撤使用 `MAX(high)`；仅借鉴信息架构，不将其数据作为生产事实。
  - V1.2 已有官方核验入口、权重缓存、主备行情和离线兜底；V1.3 应围绕这些资产新增账本/执行闭环，而不是复制十一指数报告。
  - 外部数据供应商可用性、授权、接口稳定性及历史覆盖尚未完成系统研究，需 Research Reviewer 验证。
- Risks：
  - 数据口径混用（close/high、官方/第三方、交易日/自然日、不同分位区间）会产生错误解释；用字段级口径、source registry、缺失不造数缓解。
  - 将报单当成交会污染持仓；以明确“已成交”文案及用户确认门禁缓解。
  - 追加低配、整手取整、剩余现金可能不守恒；用固定公式版本、逐行/总额不变量、10万/20万和持仓夹具缓解。
  - 重复点击、回退、重算、多标签页可能重复写交易；用唯一约束、事务、幂等和版本号缓解。
  - 开发/生产库混用、Migration 失败或备份不可恢复；用独立开发库、不可回改 Migration、pre-deploy backup、integrity/foreign key、隔离恢复缓解。
  - 范围过大；P0 先闭环，P1/P2 分阶段，生产部署独立授权。
  - 交易/持仓为个人敏感数据；正式 DB/导出/备份不进 Git、不进入静态目录，演示数据可清除且虚构。
- DoD：
  - [ ] V1.2 六指数、官方链接、三类缓存、主备行情、初始化更新、CSV、10万/20万计算回归通过，0 个阻断 JS 错误。
  - [ ] 三宽基+六红利统一字段顺序和来源日期；source registry 中每个非 `NA` 字段有 URL/原始文件、授权依据、覆盖日期和口径；PE/PB/股息率分位未过证据门时只显示 `NA/暂无数据`，缺失数据不造数。
  - [ ] 回撤只在同指数收盘序列通过双源核验后展示；按 inner join 交易日、并集缺失率 0.5%、候选高点缺日、相对误差 0.10%、全量区间和抽样点规则验收；身份不符/ETF/个股/盘中 high/全收益序列负例必须失败并显示“暂无数据/双源核验失败”及原因。
  - [ ] 行情三路实际测试通过；腾讯/东方财富按未版本化公开网页源执行 3 秒 timeout、最多 2 次 `0.5s→1.5s` 退避、10 分钟内连续 3 次失败、缓存 72 小时/3 个交易日陈旧阈值和连续 2 次成功恢复条件；状态字段完整，普通价格只读；手动覆盖默认隐藏且有标记。
  - [ ] SQLite Migration、schema.sql、版本表、开发/生产隔离、Git 排除、foreign_keys、WAL/busy_timeout、完整性检查通过；在 Mac Mini 临时库完成双连接读写、短事务锁等待、进程重启、WAL checkpoint 和异常中断恢复实测。
  - [ ] 四生命周期均能生成透明计划；BUY/SELL 均须人工确认，不自动执行。
  - [ ] 冻结/revision、刷新不改建议、已确认不可改写、四态 checklist/单只模式/复制/恢复/完成门禁通过。
  - [ ] 只有用户人工核实“已成交/已卖出成交”的 `confirmed` 写 transactions；“已下单/已报单”不得进入 confirmed；部分成交/撤单首版拒绝或走 Change C；持仓可重建；清仓归零、周期关闭、历史保留；现金事件可追溯且旧余额结转。
  - [ ] 偏差满足“行偏差=实际投入-理论目标；偏差和=实际总额-理论总额”；已有持仓+新增100,000元夹具验证低配优先、超配0股、默认不卖。
  - [ ] 再平衡、清仓、非当前成分处理、SQLite 重启恢复、隔离备份恢复、容器持久化边界验证通过；`.backup`/`VACUUM INTO` 备份恢复后通过 `integrity_check`、`foreign_key_check`，并验证 WAL 相关文件边界。
  - [ ] README、CHANGELOG、操作/维护/口径说明、Migration、验收报告和 ZIP 齐全；无密钥、真实 DB、真实持仓或生产备份；无未经授权生产变更。
- P0 / P1 / P2：
  - P0（非做不可）：
    1. V1.2 能力保护与回归基线。
    2. 逐指数 source registry/数据矩阵、字段级来源/日期/口径/授权/缓存状态治理。
    3. 三宽基+六红利同指数最高收盘双源核验、对齐/容差和安全降级。
    4. 只读行情 UI、主备缓存三路和手动覆盖隔离。
    5. SQLite Migration、核心表、交易/现金账本、开发生产隔离。
    6. 四生命周期计划生成，SELL 只计划不执行。
    7. 计划冻结、revision、不可变确认和数学不变量。
    8. 手机 checklist、单只模式、复制、四态处理和完成门禁。
    9. 进度恢复、confirmed 写入、重复确认防护。
    10. 持仓重建、现金结转、非当前成分、周期关闭/新周期。
    11. 自动化夹具、10万/20万/追加/再平衡/清仓/SQLite/备份恢复测试。
    12. 操作/维护/口径文档及验收报告；授权前不部署生产。
  - P1（blocking / 非 blocking 注明）：
    - 已决策：project_slug、普通 A 股交易单位、成交价/费用范围和估值历史数据接受标准均已由人类批准；`confirmed` 成交语义已按计划确定，不再作为未决歧义。
    - blocking：Research Reviewer/数据验收链核验宽基与九指数历史 close/估值来源、授权、覆盖、同指数双源及 930955 调样后 closeweight 官方文件验收门。
    - 非 blocking：中证A500、实际成交价可选补录、批次备注、更多导出视图、disabled BrokerAdapter。
  - P2：
    - 真实历史 sparkline、估值变化高亮、横向对比图（仅真实序列具备后启用）。
    - 生产备份保留策略、异地副本、macOS 定时调度（需运维授权）。
    - 费用税费、分红、公司行动、部分成交/撤单、券商成交单导入（另立 Change C）。
    - 公网、多用户、跨设备同步、权限体系或迁移 PostgreSQL/Supabase（达到边界后重评估）。
- Human Decisions Needed：
  1. 【APPROVED｜2026-09-15】确认 `project_slug=dividend-portfolio`；正式目录仍须遵守后续授权边界。
  2. 【APPROVED｜2026-09-15】无合法同口径历史序列时显示 `NA/暂无数据`，不强行补齐十年分位、回撤或估值序列。
  3. 【APPROVED｜2026-09-15】按普通 A 股 100 股整手执行；特殊交易单位暂无，人未列明的特殊情况走高级异常处理/异常记录。
  4. 【APPROVED｜2026-09-15】首版不计佣金、税费、分红、公司行动、部分成交和撤单；相关能力另立 Change C。
  5. 【APPROVED｜2026-09-15】实际成交价可选，保留 `reference_price` 标记。
  6. 【APPROVED｜2026-09-15】中证 A500 首版不纳入，保持 P2。
  7. 【APPROVED｜2026-09-15】正式 Docker/SQLite 目录、备份和调度暂不授权；当前仅开发、测试、打包，不做正式生产变更。
- Readiness Score（Plan Readiness Score / 计划成熟度，满分 100）：
  - 产品目标与用户需求（20）：20/20。闭环、计划/事实分离、成交语义、NA 体验、交易单位、费用范围和成交价规则均已批准。
  - 核心方案完整性（20）：20/20。registry 字段、逐条证据日志、双源算法、行情状态和 SQLite DoD 已具体化；失败抓取也有可审计记录。
  - 外部事实与竞品验证（20）：14/20。已有官方 URL/快照、S&P 页面和腾讯研究证据；本轮 curl 受网络/DNS 阻断未取得字节 hash，九指数历史序列/授权、东财 E2E、930955 生效后文件仍未完成。
  - 技术可行性（15）：14/15。阈值和 SQLite 验收矩阵可执行，但尚未实际开发/测试。
  - 风险与异常场景（10）：10/10。失败、陈旧、代理误用、成交歧义和数据缺失均有明确边界。
  - 开发范围与 DoD（10）：10/10。registry 证据表、失败记录、双源/行情/SQLite 验收条件均已写入计划；实际验收仍待开发/QA。
  - 未决问题（5）：4/5。人类决策已完成；仍有外部数据验收和实际开发/QA 验收门，正式生产授权已明确暂不开放。
  - 合计：92/100
  - Gate（进 Human Review 条件）：Readiness >= 90 AND P0 = 0 AND blocking P1 = 0 AND 关键事实已验证 AND 核心假设已合理验证。当前不满足，不得进入 Human Review，不得派 Builder。
- Research Review Round（第几轮/Reviewer 结论摘要）：R2：Research Reviewer FAIL，74/100，9 条 Required Fixes 中 5/9 真闭环；Planner 随后完成了 9 条口径修订动作，但该动作不等同于 R2 Reviewer 结论。R3：Research Reviewer FAIL，85/100，R2 的 9 条中 7/9 真闭环；已修正 000905/H30269 factsheet 实际 as-of 日期并区分结论口径。R4：Research Reviewer FAIL，87/100，R2 的 9 条中 8/9 真闭环；已补 E01-E20 逐条抓取证据。人类于 2026-09-15 按建议完成 7 项拍板：接受无合法同口径序列显示 NA、接受腾讯/东财 best-effort、确认 project_slug 与普通 A 股 100 股整手、首版排除费用/公司行动/部分成交/撤单、成交价可选＋reference_price、A500 放 P2、暂不授权正式 Docker/SQLite 目录备份调度。当前人类决策不再是 blocking；剩余为九指数历史 close/估值授权覆盖、930955 生效后 closeweight、双源实际序列及后续开发/QA 验收门，仍等待 R5。
- PLAN_GATE：IN_PROGRESS（等待 R5）
