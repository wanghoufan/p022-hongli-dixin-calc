# CHANGELOG

## V1.3｜2026-09-15

在保留 V1.2 六指数、官方成分/权重缓存、主备行情与 10 万/20 万底仓测算能力的前提下，增量升级为单人本地红利底仓管理工具，完成「估值与市场环境 → 建仓/追加/再平衡/清仓 → 冻结下单计划 → 手机辅助下单 → 人工确认 → 真实持仓与策略现金 → 未完成批次恢复」闭环。系统只做计划、记录和核对，不自动下单、不自动卖出、不接券商接口、不接 Supabase。

- **D1｜SQLite 账本基础设施**（P0#5）：新增 `db/migrations/`、`db/schema.sql`、schema version、`sqlite3` 标准库连接（WAL、`foreign_keys=ON`、`busy_timeout`）；cycles/batches/order_items/transactions/cash_ledger 五张业务表与 `v_holdings`/`v_cash_balance` 重建视图；已确认交易不可 UPDATE、transactions/cash_ledger 追加式不可 UPDATE/DELETE 的不可变触发器；开发库与正式库隔离（`.db`/`var/`/`DockerData`/`DockerBackups` 进 `.gitignore`，静态服务拒绝暴露 `db/` 与 `.db`）；新增 `/api/ledger/*` JSON API，V1.2 旧接口语义不变。smoke 79/79。
- **D2｜四生命周期计划引擎**（P0#6#7）：`INITIAL` 首次建仓、`ADD` 追加投资（只买不卖、低配优先、超配 0 股）、`REBALANCE` 全面再平衡（只生成 BUY/SELL 计划）、`EXIT` 清仓退出（逐笔 SELL）；冻结快照与 revision（刷新行情不改已冻结建议股数、已确认项不可改写、缺行情拒绝生成不补造数）；固定公式版本、逐行/总额双数学不变量、closed 周期拒绝再写入。SELL 只计划不执行。smoke 121/121。
- **D3｜下单执行页**（P0#8#9）：手机辅助 checklist / 单只专注模式，复制代码/名称/数量/单行记录；四态 `PENDING/CONFIRMED/SKIPPED/REVIEW` 流转与完成门禁（全部确认成交/已跳过才通过）；`CONFIRMED` 只经 `record_transaction` 联动写入、不可逆转；刷新/重启后从服务端恢复进度；修复 D2 遗留 P1×2（CLOSED 周期仍可写三接口、revise 可改写 kind/cycle_id）。smoke 146/146。
- **D4｜估值回撤看板 + 行情三路 UI**（P0#2#3#4）：三宽基 + 六红利统一字段顺序与三层口径（课程/官方/第三方）各自标注、不混口径；回撤固定 `currentClose/highestClose-1` 且必须同指数双源核验（inner join、并集缺失率 ≤0.5%、相对误差 ≤0.10%、候选最高 20 日不缺日、负例身份校验），核验不通过或无授权序列只显示「暂无数据」；行情三路状态契约（`source/status/dataDate/fetchedAt/ageSeconds/attempts/errorCode/cacheAgeSeconds/stale`，五态枚举、3s timeout、2 次退避、72h/3 交易日陈旧）；普通价格只读，手动覆盖默认隐藏并标 `MANUAL_OVERRIDE`、不进账本定价；修复 D4 自身 P1×2（恢复需连续 2 次成功、双源抽样补 seeded 随机 20）。smoke 180/180。
- **D5｜持仓与历史页 + 非当前成分**（P0#10）：只读持仓页从 confirmed 成交重建（`v_holdings`）、策略现金余额/流水、批次计数；非当前成分持仓以 `STALE_CONSTITUENT` 标记（不分配新 BUY、保留显示、EXIT 照常全仓 SELL）；修复 D4 遗留 P1×2（源健康度滚动窗口与连续 2 次恢复、双源抽样确定性）。smoke 209/209。
- **D6｜文档对齐 + 验收报告 + 最终回归**（P0#11#12）：README 增 V1.3 节，CHANGELOG/更新日历与数据口径/智能体更新提示词对齐，新增 `docs/qa/ACCEPTANCE_D6.md` 验收报告；全量回归 `scripts/ledger_smoke_test.py` **209/209 EXIT=0**，全程仅用临时开发库，未触碰正式库/生产目录。
- **D7｜UI 返工五项**（Change B，用户验收反馈）：估值区拆宽基/红利两张表＋紧凑行高；宽基 PE/PB/股息率分位按证据门 B 例外落公开估算（百分位/股叉叉，逐格标来源＋估算）；行内确认＋回车/Esc（删 `window.confirm`）；复制就近 toast；删除测试批次（含 CONFIRMED 需输“确认删除”四字＋审计，CLOSED 拒绝）。smoke 242/242。
- **D8｜单行撤销已确认成交**（用户明确要求）：CONFIRMED 行“撤销”按钮＋输入“撤销确认”四字，删联动成交/现金事件、行回 PENDING、CLOSED 拒绝＋审计（migration 0003＋schema v3＋`ledger_reverts`）；标签 `.vtag` 加 nowrap 修劈半。smoke 262/262。
- **D9｜回撤近似数据上架**（用户拍板近似＋交叉验证）：`scripts/fetch_drawdown.py`（腾讯 fqkline bfq / 东方财富 push2his fqt=0 不复权收盘近 10 年 `MAX(close)`，失败用参考站 2026-08-07 快照兜底并标注）→ `cache/valuation/drawdown.json`（9/9 有数＋crossChecks）→ `/api/drawdown`＋页面脚注来源行。smoke 278/278。
- **D10｜宽基风险溢价 PE 口径反推**（参考站同款公式 `100−PE分位`：36.2/22.3/30.2，标估算；股息率口径仍 NA）。smoke 282/282。

> 说明：V1.3 全部增量为本地开发/测试交付；QA 通道因沙箱禁绑端口/Orca Runtime 不可达连续预检 FAIL（D1-D10，产品 bug 0 条），supervisor 逐阶段独立重跑补位（79→121→146→180→209→242→262→278→282 全绿）；真机/浏览器复验待用户；未授权正式生产部署。详见 `docs/qa/ACCEPTANCE_D6.md`（含 D7-D10 增补）。

## V1.2｜2026-09-15

- 从单 HTML 升级为本地长期工具：`server.py + index.html + cache/`。
- 修复 file:// 跨域导致官方权重自动读取失败、缓存空白的问题。
- 新增磁盘持久缓存：官方原始 XLS、解析后 JSON、最近成功行情。
- 行情升级为：腾讯主源 → 东方财富备用 → 本地行情缓存。
- 每只股票新增行情来源和时间戳；CSV 同步导出行情源/时间。
- 新增首次联网自动补齐中证指数解析缓存。
- 新增“一键初始化/更新全部官方缓存”。
- 页面保留每个指数对应官方核验入口。
- 调样规则明确到实施窗口，不再只写“季度/半年/年度”。
- 新增长期维护智能体提示词、更新日历、数据源清单。
- 包内预置 930740 官方快照和 SPCLLHCP 515450 中报代理快照；其余中证指数首次联网从官方自动初始化。

## V1.2.1｜2026-09-15（维护修复）

- 修复页面加载即 `ReferenceError: initSelect is not defined` 导致全页功能瘫痪（下拉框为空、后端检测/成分清单/行情全部不执行）：在 `selectIndex` 之前补回缺失的 `initSelect()` 函数（遍历 INDEX_DATA 填充下拉框选项）。
- Excel 解析组件 SheetJS 改为项目内本地引用（`xlsx.full.min.js`），并保留 jsdelivr CDN onerror 兜底，解决浏览器连不上 CDN 时无法解析官方 XLS 的问题。
- Playwright 真实浏览器端到端验证通过：后端检测✅、6/6 指数解析缓存✓、下拉框 6 选项、选指数后成分清单正常填充、0 条 JS 错误、0 个失败请求。
