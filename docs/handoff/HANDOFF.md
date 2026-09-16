# HANDOFF｜交接（暂停/恢复用，先读我）

> 旧版字段（governance-state / Evidence / Human Gate / Promotion / Dispatch ID）已废弃，不填。

- Captured at（YYYY-MM-DD HH:MM）：2026-09-16 09:10（用户明确叫停，开发暂停快照·第二轮）
- PROJECT_PHASE：（PAUSED：用户 2026-09-16 明确叫停，开发暂止；D11 Docker部署＋B2去.bat＋neat收尾已推完 153d7e8；Docker容器8771常驻运行中；仅剩用户浏览器复验）
- PLAN_VERSION：（PRODUCT_PLAN_V1.0）
- PLAN_READINESS_SCORE：（92：planner 自评；R5 跳过，用户批准，偏差见下）
- PLAN_GATE：（APPROVED：用户批准跳过 R5，R4-87 为最后 reviewer 结论，偏差记此处）
- DEV_BASELINE：（PRODUCT_PLAN_V1.0）
- CHANGE_REQUEST：（B：估值B-公开估算＋删除测试批次＋D8单行撤销确认，用户明确要求，局部更新留 DEVELOP 不召 Planner）：
- Stage ID（本阶段叫什么）：PAUSED-开发暂停·第二轮（V1.3＋D7-D10＋D11 Docker＋B2＋neat收尾已推完 153d7e8；容器dividend-portfolio-app-1在8771常驻healthy；仅剩用户浏览器复验）
- 剩 P0（没完的才列，多一条都不行）：用户浏览器复验一次（http://127.0.0.1:8766/ 本地版＋http://127.0.0.1:8771/ Docker版：看首页＋持仓＋下单页）
- 当前 Task（正干到哪）（累计打回 n/2，supervisor每次打回时TM同步更新）：暂停快照·第二轮：D11关（Docker四件套＋server.py:520 BIND单行＋.gitignore补.env.local，build通8771实测200，QA终验PASS，supervisor两轮终审PASS，rework为supervisor打回1次已清零闭环）→B2关（index.html:32/:338/:498去.bat，reviewer落盘＋qa＋supervisor PASS）→neat两轮收尾→已推153d7e8，工作区干净；Docker容器8771常驻healthy（空账本，与dev.db隔离）；rework 0/2，无升级
- 执行链/Session（可选，仅真 resume 通道填，普通 subagent 可空；TM 只记录/引用，ID 由基础设施返回，不手造、不要求用户复制；返工确认是否原链；senior 升级开新链后更新；本派走主/备一句）：PLAN：planner 链 01a0a49c（同链 resume 4 次，codex，主）；reviewer 链 01a0a49e（同链 resume 3 次＋R5 两次被拒，codex，主）。D1：builder＝opencode 本通道（初版＋--continue 返工，主）；reviewer＝本窗口 subagent×2（初审＋复验，主）；qa＝codex luna（主，环境 FAIL）；supervisor＝opencode 主（独立重跑 79/79）。D2：builder＝opencode 新链（主）；reviewer＝本窗口（主）；qa＝codex luna（主，环境 FAIL）；supervisor＝opencode 主（独立重跑 121/121）
- 未闭环评审意见（code-reviewer/qa 留的还没改的）：无
- docs 落盘清单：D1（79）→D2（121）→D3（146）→D4（180）→D5（209）→D6文档验收→D7（242）→D8（262）→D9（278）→D10（282/282）；review×10 P0=0、qa×10环境FAIL bug 0、ACCEPTANCE_D6；CHANGELOG补D7-D10；DISPATCH-LOG、TASK-MODEL-LOG双校验；3e5959a：README V1.3重写＋删.bat＋库改名；D11：Docker四件套＋server.py:520 BIND单行＋.gitignore补.env.local（BUGS_D11_docker PASS）；D12/B2：index.html三处去.bat（CODE_REVIEW_B2＋BUGS_D12_b2 PASS）；neat两轮收尾；已推153d7e8
- 下一步（Next Single Action）：用户浏览器复验（8766本地版＋8771 Docker版：首页＋持仓＋下单页），验完收工。除此之外无待办。
- Git（2026-09-16 用户明确指令）：私有库 wanghoufan/hongli-dixin-calc；分支 main 已推到 153d7e8（e450665 D11＋00c62dc B2＋6a12aae HANDOFF＋153d7e8 neat）；工作区干净；容器dividend-portfolio-app-1在8771常驻healthy（DockerData空账本，与dev.db隔离）；dev.db未跟踪；8765/8766本地服务运行中未碰；win只读副本需重拉，不push回本库
- 人要拍什么板（列出来问，不问不许开工）：仅浏览器复验结果（验完即收工）；其余无
- 规矩铁律（恢复后照旧）：①不跑Windows，目标仅Mac Mini；②dev.db/真实数据/密钥不进Git；③无用户明确指令不commit不push（commit信息含分支名）；④新建/改文档先出草案经确认再写；⑤P0没完不收工；⑥agent派工前读USER_MODEL_OVERRIDE.md分工表（codex/opencode走通道直调，禁本窗口套娃代做）；⑦小问题编排者自定，定不了问审查者；⑧每轮末三行心跳（目标/剩P0/下一步）
- 项目收尾（2026-09-16 用户拍板告一段落）：v1.3.1回撤快照打进镜像（Dockerfile COPY cache/valuation＋.dockerignore放行，drawdown.json本就已跟踪），容器重建后8771回撤OK实测；Tailscale手机访问100.125.100.15:8771已通；quotes.json运行时刷新不提交。
- permission_request（可选：原文/决策/回执一句，首版可先记自然语言一句）：无
- 收尾记一笔（neat-freak：文档对齐了没、临时文件清了没、未决列完没；neat 派完后 TM 补记，若已落盘则追加修订行）：neat-freak 2026-09-15 已收尾：①口径§4一句已按 CODE_REVIEW_D6 P2-1 改为三路顺序＋五态流转、与 README§5 对齐；②REVIEW/BUGS D1-D6 齐＋ACCEPTANCE_D6 在，HANDOFF 账本行数已订正 35/17→39/20；③项目内无 *.db、无 __pycache__、无 docs/tmp 残留（/tmp 未动）。业务代码未动。TM 2026-09-16 暂停记：smoke 282/282 EXIT=0；工作区干净（已推 3e5959a）；.bat 已删但 index.html 两处文案未动（B2 未决）；Docker 未开始（daemon 未启动，无 Dockerfile，属 Change C）。本 HANDOFF 修改未提交——恢复后若直接 commit，需用户先明确分支名。TM 2026-09-16 续跑记：Docker四件套草案已落地（Dockerfile/compose.yaml/.dockerignore/docker/env.template，未提交；宿主端口8771自定，8765/8766保持运行未碰；review复核PASS P0=0，P1两项已顺手修齐compose变量透传；daemon仍OFF，docker build验证待补；dev.db/.env.local均未进Git）。B2与浏览器复验仍挂起。TM 2026-09-16 D11收工记：daemon已起→build通（dividend-portfolio:v1.3.0）→根因server.py:520写死127.0.0.1致宿主RST（用户已批单行改BIND，默认不变）→容器8771得200、本地8779默认200→QA终验PASS（001/002均CLOSED）→supervisor终审PASS。未提交：Dockerfile/compose.yaml/.dockerignore/docker/env.template新文件＋server.py一行＋.gitignore两行＋BUGS_D11_docker.md，等用户commit指令（含分支名）。neat-freak 2026-09-16 收尾修订：①README V1.3/Dockerfile/compose.yaml/docker/env.template/index.html口径一致：.bat文件已删（仅剩启动工具.command）、index.html无.bat/Windows残留（命中均为batch标识符）、V1.2字样仅为历史版本标记/回归语义非残留，业务文件未动；②CODE_REVIEW_B2（Commit改已推00c62dc＋残留行改零命中）、BUGS_D12_b2（diff改00c62dc已推）、BUGS_D11_docker（构建行补已推e450665）已对齐现状；③项目内无__pycache__/docs/tmp，/tmp/df-verify空目录已清（backups/data均空），dev.db未动未跟踪；工作区干净（HEAD 6a12aae）。不commit不push。neat-freak 2026-09-16 终轮收尾修订：①HEAD 现为 153d7e8，工作区干净；.bat 文件无（仅剩启动工具.command）；index.html 无 .bat/Windows 独立残留（命中均为 batch/batches 标识符）；index.html 内 V1.2 字样为既有版本标记/回归注释（业务文件不动，README 标题 V1.3 差异如实记录）；Docker 四件套齐且与 README§账本隔离口径一致；②BUGS_D12_b2、BUGS_D11_docker 内 HEAD 已订正 6a12aae→153d7e8，CODE_REVIEW_B2 与现状一致；③项目内无 __pycache__/*.pyc、无 docs/tmp 残留；/tmp/df-prod.env 存在未动（系统级提示），/tmp/df-verify 已不存在；dev.db/dev.db-wal/dev.db-shm 未动未跟踪。不commit不push。

## 恢复读盘（全体系唯一顺序，别乱）

1. AGENTS；2. 角色卡；3. 根 `USER_MODEL_OVERRIDE.md`；4. 本 HANDOFF；5. 根 `经验一句话.md`；6. 任务目标放最后。
冲突才扩大读。

## 迁移执行链（本轮）

- 模板源：`…/老项目迁移模板包`；铺入 35 项（含软链 USER_MODEL_OVERRIDE.md→母版真源），跳过 0，备份 1（旧 HANDOFF.md）。
- 映射：业务文件全部留原地（index.html/server.py/cache 等），详见 docs/templates/归位表.md。
- 基线：py_compile PASS；测试端口 8088 首页 200；测试实例已退出；用户另有 Downloads 目录旧版服务进程（PID 6586），未碰。
