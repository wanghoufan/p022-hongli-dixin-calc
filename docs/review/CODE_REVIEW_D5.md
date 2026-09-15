
# CODE REVIEW

- Task: D5（持仓历史页＋非当前成分＋D4 P1-1/P1-2 修复；P0#10）
- Commit: 工作区现状（server.py / db/valution.py / db/service.py / index.html / scripts/ledger_smoke_test.py D5 段；builder 自测 209/209 EXIT=0，未做独立重跑）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派，只审增量不改代码）
- Result: 过（P0=0；P1×2 已闭环，P2×1 转 backlog，不阻塞 D5 关闭；改法精确到函数）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- P0（共 0 条）：P1-1/P1-2 修复与非当前成分/持仓只读均对齐计划，无编数、无越界写账本、无 V1.2/D1-D4 回归。详见：
  - P1-1 闭环（server.py note_source_result 167-208＋split_valid_quotes 143-159＋get_quotes 356-374）：RECOVER_AFTER=2 落实"连续 2 次全校验通过才恢复"（192-195 行 consecutiveSuccesses>=RECOVER_AFTER 才由 DEGRADED/STALE 回 LIVE，否则保持原状态；Q2 一次成功仍 DEGRADED、Q3 两次成功回 LIVE）；窗口过期重置落实（182-186 行 lastCheckedAt 超 DEGRADED_WINDOW=600s 即清零计数并记 expired，Q4 跨窗口第二次失败计 consecutiveFailures=1 且 status=LIVE）；坏行不计成功落实（_quote_problem 120-140 行校验价格范围 PRICE_MIN/MAX＋dataDate 可解析/非未来/超 10 天无效；split_valid_quotes 剔除坏行只记 problems；get_quotes 360/373 行 primary_ok=(not e1)and(not p1)，坏行即 ok=False 进 note_source_result 失败分支）。smoke Q1-Q7 全覆盖。
  - P1-2 闭环（db/valution.py verify_drawdown 217-249）：RANDOM_SAMPLE_SIZE=20＋SAMPLE_SEED=20260915 锁死；rng=random.Random(sample_seed) 确定性抽样 rng.sample(joined, min(20,len))，不足全取；仅进 sampled/sampledRandom 审计计数，不改变 pass/fail 门（join/0.5%/top20/0.10% 门均在抽样前返回）；sampleSeed 随结果返回可审计。smoke S1（同输入同结果 20 条）/S2（12 日全取）/S3（换种子仍可复现）＋D4.3 已同步断言 len(sampledRandom)==20，均通过。
  - 非当前成分（db/service.py _build_plan 482-547＋_buy_only_rows 605-637＋_rebalance_rows 639-664＋_exit_rows 666-677＋_collect_warnings 600-603）：constituent_set/stale_constituents（482-483）＋universe=成分∪持仓（485-488）＋缺行情拒绝不补数（489-492）；ADD 缺口仅在成分内计算（609-610 非成分 gap=0；613 按 gap 降序分配）；REBALANCE 非成分跳过新 BUY（648-649 continue）；EXIT 按全部持仓全仓 SELL（526＋669-676，不经过成分过滤）；行标记 constituent_status/stale_constituent/constituent_reason＋BUY 行 note（532-547）；summary/holdings 不过滤（778-800 直透 v_holdings）；warnings 声明不分配＋EXIT 照卖（602-603）。smoke ST1-ST8 全覆盖。
  - 持仓页只读（index.html 116-132＋473-536）：新增「七、持仓与历史」区块经 hpApi 仅 GET /api/ledger/cycles、GET /api/ledger/cycles/:id/summary、GET /api/ledger/cash?cycle_id=（479-493/517/522）；D5 脚本块内无 POST 字符串（P5）；持仓表 id=hpRows＋重建声明 v_holdings(confirmed transactions)＋现金余额/流水＋批次计数齐（P3）；STALE_CONSTITUENT badge 行标记（510-513）。summary 保留非成分（H2）。无账本写、无 V1.2/D1-D4 既有区块改动（独立 script 块＋注释"不改既有区块"）。
  - V1.2/D1-D4 零改动：SheetJS 仍第 3 行、function initSelect、id=valuationTable、MANUAL_OVERRIDE 均在（P6）；drawdown_board 九指数 NA 语义与 D4 门控未动；service D2/D3 计划/冻结/四态语义未动（D5 增量仅追加成分状态标记与警告文案）。

## P2 / P3 Backlog Findings

- P2-1（dataDate 未来容差 1 天沿用 D4 口径）：server.py _quote_problem 136-137 行 future>86400 才判未来，D5 未收紧。行为与 smoke Q5（当日 mt 通过）自洽，不影响"坏 dataDate 不计成功"门，故列 P2。改法：如需严格，在 _quote_problem 中把未来阈值收紧或按交易日口径判定，并同步更新 smoke Q5 夹具。

