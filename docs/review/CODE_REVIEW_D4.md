
# CODE REVIEW

- Task: D4（估值回撤看板＋行情三路 UI；P0#2#3#4）
- Commit: 工作区现状（server.py / db/valution.py / index.html / scripts/ledger_smoke_test.py D4 段；builder 自测 180/180 EXIT=0，未做独立重跑）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派，只审增量不改代码）
- Result: 过（P0=0；P1×2＋P2×2 转 backlog，不阻塞 D4 关闭；改法精确到函数）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- P0（共 0 条）：双源 join/0.5%/0.10%/top20/负例全对齐计划；九指数无序列时统一 NA 无编数；三层口径各自标注不混；五态＋72h/3交易日＋退避落实；手动覆盖默认隐藏＋标记＋冻结拒绝（不进账本）；普通价格只读；V1.2 区块零改动；/api/drawdown 只读不写账本。均通过，详见逐项证据：
  - 双源算法（db/valution.py verify_drawdown）：身份校验 kind=price/instrument=index/field=close＋code/name/currency 一致（_identity_problems＋165-173）；inner join（177-178）；并集缺失率＞0.5% 失败（182-185，MISSING_RATE_LIMIT=0.005）；top20 缺日失败（187-193，TOP_N=20）；全量 joined 相对误差＞0.10% 失败（195-205，REL_TOLERANCE=0.001）；失败一律 na_result（drawdown=None/display=暂无数据）。负例 D4.7-D4.14（ETF/个股/high/全收益/code/name/币种/空序列）全由身份/一致性分支拒绝。公式 currentClose/highestClose-1 同一序列（207-211）。
  - NA 诚实（drawdown_board）：无 sources 时九指数统一 NA＋NO_SERIES_REASON（249-296）；顺序 000300/000905/000852打头共 9 个；rules 锁死 0.005/0.001/20/公式。
  - 三层口径（index.html renderValuation/vLayer）：课程/官方/第三方三层 vLayer 各自标注＋VALUATION_META＋"不合并分位"；宽基 sheet=null 时课程层显示暂无数据、explain 走"市场环境（宽基）"分支，不拿 ETF/个股代理。
  - 行情三路（server.py）：QUOTE_TIMEOUT=3、QUOTE_ATTEMPTS=2、QUOTE_BACKOFF=(0.5,1.5) 经 fetch_with_backoff 落实；cache_quote_status 落实 72h（CACHE_MAX_AGE_SEC）/3交易日（CACHE_MAX_TRADING_DAYS）→STALE_BLOCKED＋stale 标记；quote_row 字段齐 source/status/dataDate/fetchedAt/ageSeconds/attempts/errorCode/cacheAgeSeconds/stale；QUOTE_STATUSES 五态齐；get_quotes 主→备→缓存三路＋400/200 语义不变。
  - 手动覆盖隔离（index.html）：manualOverrideArea style display:none 默认隐藏＋manualToggleBtn 切换；localStorage 键 divManualOverride 持久＋quoteInfo 标 MANUAL_OVERRIDE＋badge/覆盖价"不进账本定价"；dpFreezeFromCalc（391）把 isManual 的 code 列入 missing 并拒绝冻结，不进 quotes 定价。
  - 普通价格只读：主表表头"当前价格（只读）"＋renderRows 价格格为 ro-price span＋MANUAL_OVERRIDE badge；全文件无 class="price" 可编辑输入；可编辑 manual-price 仅在高级异常处理区。
  - V1.2 零改动：function initSelect/indexSelect/valuationRows 保留；SheetJS 仍在第 3 行；D4 增量为独立脚本块＋VALUATION/MARKET_DATA/手动区，不改 D1-D3 区块语义。
  - /api/drawdown 只读：server.py do_GET 分支仅调用 drawdown_api.drawdown_board() 直接返回，无 POST、无账本写、无缓存写。
- P1-1（恢复条件只落实一半，建议转 backlog，不打回）：server.py note_source_result（115-136）成功 1 次即回 LIVE（128 行 >=1），计划要求"同一源连续 2 次请求同时通过 HTTP/解析/字段范围/dataDate 校验才回 LIVE/FRESH"；且 get_quotes 以"无异常"记成功，未显式校验字段范围＋dataDate；DEGRADED_WINDOW 只存不用于过期（连续计数无 10 分钟滚动过期）。改法：note_source_result 增加 recoveredAfter=2 逻辑（consecutiveSuccesses>=2 才由 DEGRADED→LIVE；STALE 恢复同理）＋在 get_quotes 成功分支补 dataDate/price 范围校验＋按 windowSeconds 过期重置计数。当前不造成编数/误标实时（新鲜/陈旧仍由 cache_quote_status 按 72h/3日判定），故列 P1 不打回。
- P1-2（双源抽样说明与计划差一句，建议转 backlog，不打回）：计划"另抽查端点、最高点前后各 5 日及随机 20 个交易日"；valution.py verify_drawdown（213-219）只抽端点＋最高点前后各 5 日（sampled 2~12），无随机 20。改法：在 verify_drawdown 的 sample 集合中加入确定性随机 20（ seeded Random 按 joined 长度抽 20，joined 不足 20 则全取），仅用于 sampled/审计计数，不改变 pass/fail 门。smoke D4.3（2~12 点）需同步放宽上限或断言"≥2 点且含端点/最高点"。当前门控（join/缺失/top20/容差）已全对，不影响 NA 诚实，故列 P1 不打回。

## P2 / P3 Backlog Findings

- P2-1（交易日为周一至五简化口径）：server.py trading_days_between（80-88）按 weekday<5 计，不含法定节假日/调休。计划未强制真实交易日历，D4.H3/H4 用同一口径自洽，故列 P2。改法：后续如需精确，在 server.py 引入可配置节假日表或注释"简化口径"并在 UI 文案 Bliss 标注，smoke 保持周末夹具即可。
- P2-2（per-quote DEGRADED 与源健康度解耦）：get_quotes（294-300）按来源名（腾讯=LIVE/东财=DEGRADED）定行状态，_SOURCE_HEALTH 的 DEGRADED 只进 sources 展示，不直接驱动行状态。行为与"失败切下一源"一致且 smoke D4.H5 只断言枚举＋consecutiveFailures 可见，故列 P2。改法：如需严格对齐"连续 3 次失败即标 DEGRADED"，在 get_quotes 行状态判定中叠加 source_health()（健康为 DEGRADED 时行状态取 DEGRADED 并附 errorCode），同步更新 smoke 断言。
