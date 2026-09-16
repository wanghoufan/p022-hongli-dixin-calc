# HANDOFF｜交接（暂停/恢复用，先读我）

> 旧版字段（governance-state / Evidence / Human Gate / Promotion / Dispatch ID）已废弃，不填。

- Captured at（YYYY-MM-DD HH:MM）：2026-09-16 08:10（用户明确叫停，开发暂停快照）
- PROJECT_PHASE：（PAUSED：用户 2026-09-16 明确叫停，开发暂止；D10＋README重写＋删.bat＋库改名已收工；Docker 部署待立项）
- PLAN_VERSION：（PRODUCT_PLAN_V1.0）
- PLAN_READINESS_SCORE：（92：planner 自评；R5 跳过，用户批准，偏差见下）
- PLAN_GATE：（APPROVED：用户批准跳过 R5，R4-87 为最后 reviewer 结论，偏差记此处）
- DEV_BASELINE：（PRODUCT_PLAN_V1.0）
- CHANGE_REQUEST：（B：估值B-公开估算＋删除测试批次＋D8单行撤销确认，用户明确要求，局部更新留 DEVELOP 不召 Planner）：
- Stage ID（本阶段叫什么）：PAUSED-开发暂停（V1.3＋D7-D10＋README重写＋删.bat＋库改名已推完 3e5959a；Docker 部署未开始；用户浏览器复验仍挂起）
- 剩 P0（没完的才列，多一条都不行）：①用户浏览器复验一次（附条件项：http://127.0.0.1:8766/ 看首页＋旧 holdings＋下单/持仓页；QA 通道恢复后补跑留档）②Docker 部署（用户已定方向，Change C 待展开，见下一步）
- 当前 Task（正干到哪）（累计打回 n/2，supervisor每次打回时TM同步更新）：暂停快照：D10 关→README 按 V1.3 重写→删启动工具.bat→库改名 hongli-dixin-calc→合单 3e5959a 已推 origin main；工作区干净；rework 0/2，无升级
- 执行链/Session（可选，仅真 resume 通道填，普通 subagent 可空；TM 只记录/引用，ID 由基础设施返回，不手造、不要求用户复制；返工确认是否原链；senior 升级开新链后更新；本派走主/备一句）：PLAN：planner 链 01a0a49c（同链 resume 4 次，codex，主）；reviewer 链 01a0a49e（同链 resume 3 次＋R5 两次被拒，codex，主）。D1：builder＝opencode 本通道（初版＋--continue 返工，主）；reviewer＝本窗口 subagent×2（初审＋复验，主）；qa＝codex luna（主，环境 FAIL）；supervisor＝opencode 主（独立重跑 79/79）。D2：builder＝opencode 新链（主）；reviewer＝本窗口（主）；qa＝codex luna（主，环境 FAIL）；supervisor＝opencode 主（独立重跑 121/121）
- 未闭环评审意见（code-reviewer/qa 留的还没改的）：无
- docs 落盘清单：D1 账本骨架（79）→D2 生命周期（121）→D3 下单页（146）→D4 估值行情（180）→D5 持仓（209）→D6 文档验收→D7 UI 返工（242）→D8 撤销（262）→D9 回撤近似（278）→D10 rp 反推（282/282 全绿）；review×10（D1-D10 过 P0=0）、qa×10（D1-D10 环境 FAIL bug 0）、ACCEPTANCE_D6（含 D7-D10 增补）；CHANGELOG 补 D7-D10；DISPATCH-LOG 58 行、TASK-MODEL-LOG 32 行（双校验 exit=0）；暂停前加单 3e5959a：README 按 V1.3 重写（去 V1.2/Windows 痕迹）＋删启动工具.bat＋库改名同步，smoke 仍 282/282
- 下一步（Next Single Action）：Docker 部署 Change C（用户已定方向，未展开）：按 docs/sop/docker.md 出草案——Dockerfile＋compose.yaml＋.dockerignore＋env 模板、project_slug=dividend-portfolio（Plan 已批，库改名不影响）、宿主端口（8765/8766 本地服务运行中，必须避让或先停）、数据卷挂 DockerData、备份走 DockerBackups；前置阻塞：本机 Docker daemon 未启动，需先起 Docker Desktop。另：用户浏览器复验仍挂起，QA 通道恢复后补跑
- Git（2026-09-16 用户明确指令）：私有库 wanghoufan/hongli-dixin-calc（原 dividend-portfolio-Mac，旧地址自动跳转）；分支 main 已推到 3e5959a（README重写＋删.bat＋库名同步）；工作区干净；dev.db 未跟踪；win 只读副本需重拉，不 push 回本库
- 人要拍什么板（列出来问，不问不许开工）：Docker 部署 Change C 细节（Dockerfile 内容、宿主端口、数据/备份目录、是否停 8765/8766 本地服务）；B2已闭环（2026-09-16：index.html:32/:338/:498三处去.bat/Windows，reviewer落盘CODE_REVIEW_B2＋qa BUGS_D12_b2＋supervisor PASS，已推00c62dc）；其余无（浏览器复验时再找人一次）
- permission_request（可选：原文/决策/回执一句，首版可先记自然语言一句）：无
- 收尾记一笔（neat-freak：文档对齐了没、临时文件清了没、未决列完没；neat 派完后 TM 补记，若已落盘则追加修订行）：neat-freak 2026-09-15 已收尾：①口径§4一句已按 CODE_REVIEW_D6 P2-1 改为三路顺序＋五态流转、与 README§5 对齐；②REVIEW/BUGS D1-D6 齐＋ACCEPTANCE_D6 在，HANDOFF 账本行数已订正 35/17→39/20；③项目内无 *.db、无 __pycache__、无 docs/tmp 残留（/tmp 未动）。业务代码未动。TM 2026-09-16 暂停记：smoke 282/282 EXIT=0；工作区干净（已推 3e5959a）；.bat 已删但 index.html 两处文案未动（B2 未决）；Docker 未开始（daemon 未启动，无 Dockerfile，属 Change C）。本 HANDOFF 修改未提交——恢复后若直接 commit，需用户先明确分支名。TM 2026-09-16 续跑记：Docker四件套草案已落地（Dockerfile/compose.yaml/.dockerignore/docker/env.template，未提交；宿主端口8771自定，8765/8766保持运行未碰；review复核PASS P0=0，P1两项已顺手修齐compose变量透传；daemon仍OFF，docker build验证待补；dev.db/.env.local均未进Git）。B2与浏览器复验仍挂起。TM 2026-09-16 D11收工记：daemon已起→build通（dividend-portfolio:v1.3.0）→根因server.py:520写死127.0.0.1致宿主RST（用户已批单行改BIND，默认不变）→容器8771得200、本地8779默认200→QA终验PASS（001/002均CLOSED）→supervisor终审PASS。未提交：Dockerfile/compose.yaml/.dockerignore/docker/env.template新文件＋server.py一行＋.gitignore两行＋BUGS_D11_docker.md，等用户commit指令（含分支名）。

## 恢复读盘（全体系唯一顺序，别乱）

1. AGENTS；2. 角色卡；3. 根 `USER_MODEL_OVERRIDE.md`；4. 本 HANDOFF；5. 根 `经验一句话.md`；6. 任务目标放最后。
冲突才扩大读。

## 迁移执行链（本轮）

- 模板源：`…/老项目迁移模板包`；铺入 35 项（含软链 USER_MODEL_OVERRIDE.md→母版真源），跳过 0，备份 1（旧 HANDOFF.md）。
- 映射：业务文件全部留原地（index.html/server.py/cache 等），详见 docs/templates/归位表.md。
- 基线：py_compile PASS；测试端口 8088 首页 200；测试实例已退出；用户另有 Downloads 目录旧版服务进程（PID 6586），未碰。
