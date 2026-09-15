
# CODE REVIEW

- Task: D6（文档对齐＋验收报告＋最终回归收尾；P0#1#11#12）
- Commit: 工作区现状（D6 无产品代码改动；README V1.3 节＋CHANGELOG V1.3 条＋更新日历与数据口径第四节＋智能体更新提示词 V1.3 增量＋docs/qa/ACCEPTANCE_D6.md；独立重跑 scripts/ledger_smoke_test.py 209/209 EXIT=0）
- Reviewer: ORCA code-reviewer（opencode/muse-spark-1.3-contributor-free，本窗口直派，只审 D6 文档增量不改任何文件）
- Result: 过（P0=0；文档与代码实际一致，无泄漏、无虚假验证声明，V1.2 原有节未改坏；P2×1 转 backlog，不阻塞 D6 关闭）

> Dispatch / Evidence ID 系字段 2.0 已废弃，不填。

## P0 / P1 Findings

- P0（共 0 条）：D6 文档增量与代码实际一致，无需打回。分项核验：
  - API 路径：README/CHANGELOG 称“新增 /api/ledger/*、V1.2 旧接口语义不变”与 `db/api.py:38-50 PREFIX=/api/ledger`、注释 `5-6`（旧 `/api/holdings?code=` 指数权重语义 untouched、账本持仓用 `/api/ledger/holdings`）一致；ACCEPTANCE 二节 6.3-6.9 旧接口断言与 smoke 覆盖一致。
  - 状态枚举：README 五态 `LIVE/DEGRADED/CACHE/STALE_BLOCKED/MANUAL_OVERRIDE` 与 `server.py:51 QUOTE_STATUSES`、smoke D4.P6/D4.H4 断言一致；`STALE_CONSTITUENT` 仅出现在持仓/计划成分状态（`service.py:534`），文档未将其混入行情五态。
  - 阈值数字：README/口径/提示词 `timeout=3s、重试 2 次、退避 0.5s→1.5s、10 分钟连续 3 次失败 DEGRADED、缓存 72h/3 交易日 STALE_BLOCKED、连续 2 次恢复 LIVE` 与 `server.py:39/41-44`（QUOTE_TIMEOUT=3、BACKOFF=(0.5,1.5)、DEGRADED_FAILS=3、WINDOW=600、RECOVER_AFTER=2）及 smoke 72*3600 断言一致；回撤 `currentClose/highestClose-1、同序列、inner join、缺失率≤0.5%、误差≤0.10%、最高 20 日不缺日` 与 `db/valution.py:23-24`（0.005/0.001）及 topN=20 断言一致。
  - confirmed 语义：README“只有已确认成交写入账本、CONFIRMED 不能经状态接口直接设置”与 `service.py:37/381-382/399-400`（ORDER_ITEM_STATES 四态、state 设 CONFIRMED 409、已 CONFIRMED 不可逆）一致；与计划 Human Decision④⑤（已成交/已卖出成交才 confirmed、部分成交/撤单拒绝）一致。
  - NA 规则：文档“无授权序列回撤/分位统一 NA、不代理、不静默取高值；930955 门未过保留旧快照标 stale、不替换不生成计划”与计划 source registry/证据门/930955 门一致，无放宽口径。
  - 无泄漏：D6 增量无密钥/token/真实持仓/生产路径；grep 仅命中 `.gitignore`/`docs/sop` 规范性提及 DockerData/DockerBackups；工作区无 `*.db` 残留；ACCEPTANCE 演示数据声明虚构可清除；smoke 仅用虚构代码（600111/600999 等）。
  - 无虚假验证：ACCEPTANCE 四节如实列 4 类未决（QA 通道环境 FAIL×5 非产品 bug、真机/浏览器待用户复验 `127.0.0.1:8765`、外部数据 P0 门未过 E01-E20 全 FAIL、生产未授权）；CHANGELOG 说明段同步声明 QA 预检 FAIL＋真机待验＋未授权生产；回归仅声称自动化 209/209，未冒充真机/外部数据已过。
  - V1.2 未改坏：README 1-76 行 V1.2 原有节（启动方式/三层缓存/行情源/六指数/正式维护）原文保留，V1.3 为独立增量节；CHANGELOG V1.2/V1.2.1 条保留；口径一-三节、提示词 V1.2 block 原文保留。
  - 独立回归：本审查独立重跑 `python3 scripts/ledger_smoke_test.py` 得 PASS 209/FAIL 0 EXIT=0，与 builder 声称一致。

## P2 / P3 Backlog Findings

- P2-1（文档口径小差异，不阻塞）：更新日历与数据口径第四节 §4 把三路写成“腾讯（LIVE）→东财（DEGRADED）→缓存（CACHE/STALE_BLOCKED）”，易误读为东财恒为 DEGRADED；代码实际为按源独立健康度流转（`server.py:384` 仅单次快照示例状态，`note_source_result` 按成功/失败流转）。改法：改为“三路顺序：腾讯（主）→东财（备用）→本地缓存；各源状态按健康度在五态间流转”，与 README §5 表述对齐；改动走 neat-freak 或后续小修，不在本轮打回。
