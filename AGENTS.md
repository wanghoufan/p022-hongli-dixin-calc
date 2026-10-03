# AGENTS.md｜ORCA（全员遵守，一页）

<!-- ORCA-RULES-BLOCK:BEGIN -->
<!-- 本区块由治理母版 scripts/sync-old-projects.sh 于 2026-09-29 注入；只增不删，可重复运行原地更新。 -->
<!-- 本项目 AGENTS.md 的其余内容（项目专属规矩）保持原样，冲突时以本区块为准。 -->
## ORCA 规则增量（母版 2026-09-29-产品验收）

> 本区块只写**对外通用**的机制增量；派工细节见 `docs/roles/`，账本口径见下方条目。

- **产品验收（2026-09-28 定）**：开发完成的判断来自**用户可见要求的覆盖证据**，不只看单测／构建／代码审查／工具调用成功。
  - 验收标准写在计划里：Phase1 给每条用户可见要求编一条可观察可测的**验收条目（AC）**，并标出**关键 AC**（对应 P0／blocking P1／核心用户路径／必要视觉交互呈现）；**关键 AC 集合不得为空**。
  - 证据落 `docs/qa/` 的**产品验收追踪矩阵**（照 `docs/qa/BUGS.template.md` 同名节）。
  - **不可放行三情形**（命中任一不得判 `PASS`）：①关键产品 DoD／AC 未测；②关键任务涉及的**每个**可见操作控件未实际点击并观察到页面／锚点／状态变化（只验 `href` 存在不算）；③验收证据缺失。
  - 视觉验收最小覆盖：关键用户任务逐条走通、按项目要求检查桌面与窄屏、用边界样本（奇偶条目数／长标题长正文／空状态）检验对齐·换行·裁切·溢出·可读性、留真实浏览器截图。
  - **用户签收**：发布类型为**首次发布**的，用户签收通过才算完成（签收前状态记未完成）；迭代更新与局部修复不强制签收。签收属 **Human Gate 范畴（用户参与）**，**不是新增 QA Gate**。
- **体系更新三件套（2026-09-29 定）**：①本项目规则文件改动后与母版对齐（用 `bash scripts/sync-old-projects.sh` 或按《迁移整理提示词》取包，**备份不覆盖**）；②账本内容**不重写**（实绩历史），只做 schema 校验 `node scripts/model/check-ledger.mjs docs/model`（须 `LEDGER-OK`）；③**HANDOFF 记一行**。**老项目无两包概念，故母版的「同步两包＋更新对外概览」不适用。**
- **派工跨目录禁令（2026-09-29 定）**：派 opencode 通道角色（supervisor／neat-freak／experience-recorder）时，任务里读写本仓以外目录（如 `/tmp`、`1.Active/` 等）会被 `external_directory` 权限自动拒、步骤静默失败，可能让角色误报已做也易反复盲试烧额度（禁盲试）；派单前处置二选一——①临时文件改到仓内已 gitignore 的 `temp/`，②先取得用户授权；codebuddy／codex 通道无此限制。
- **红线（2026-09-29 增补）**：产品验收未落盘或关键 AC 未测、不得报完工/收工；首次发布未取得用户签收、不得报完工/收工。
- **本项目迁移状态**：`docs/model/GOVERNANCE-STATE.json`（`rules_version`／`synced_at`／`project_phase_field`／`task_ledger_rows`／`agents_needs_manual_merge`／`product_acceptance_ac_added`）。
- **存量项目待办（不自动做，需项目 TM 判断）**：本项目实绩 Plan 需补「视觉与交互验收标准（AC 编号）＋关键 AC 集合＋发布类型」，否则新规则下收尾会被判**计划缺项**；完成后把 `product_acceptance_ac_added` 置 `true`。
<!-- ORCA-RULES-BLOCK:END -->


## 两阶段治理（固定 9+1，不新增角色）

- 状态：`PLAN / WAITING_HUMAN_APPROVAL / DEVELOP / PLAN_REOPEN_REQUIRED`（仅Change C受控重开期间；`PROJECT_PHASE` 当前值以 HANDOFF 为准）。
- Phase1（PLAN，用户口令`第一阶段，计划`）：只许 task-manager／supervisor／planner（Sol）／product-reviewer（显示名 Research Reviewer，ID 不变，FREE）；禁 builder／code-reviewer／qa 派工，禁业务代码改动，禁 Release。PLAN 链：Planner→Research Reviewer→Planner→…→Readiness Gate→Human Gate；用户不搬运反馈（TM 自动回传）；`PLAN_READINESS_SCORE>=90` 才进 WAITING（Readiness 定义以 `docs/pm/PRODUCT_PLAN.template.md` 为准，卡内不另写）。
- Human Gate：`WAITING_HUMAN_APPROVAL`（`PLAN_GATE=READY_FOR_HUMAN_REVIEW`）时 TM 停循环只找人一次，不可自动跨越，不可自行启动 builder；只有用户明确说`第二阶段，开发`才进 Phase2。
- Phase2（DEVELOP）：锁定 `DEV_BASELINE=PRODUCT_PLAN_Vx.x`，默认主链 Builder→Reviewer→QA→Supervisor→TM（模型以 override 表为准）；禁随意改 Plan（Plan 变更只走 Change C Controlled Reopen＋Human Approval＋新版本＋新基线）；product-reviewer（Research Reviewer）默认不派，recorder/neat 只在收尾派。
- Change Request（用户口令`变更请求：……`，TM 分类）：`CHANGE_REQUEST: NONE / A / B / C`——A=开发内小改留 DEVELOP 不召 Planner；B=局部功能变化更新局部 Requirement/DoD 留 DEVELOP 不召 Sol Planner；C=产品/架构变更进 `PLAN_REOPEN_REQUIRED`，局部暂停＋Sol Planner＋Research Reviewer＋Human Approval＋新 Plan 版本＋新 DEV_BASELINE 回 DEVELOP，不全量重跑。
- 独立重申：task-manager（唯一对人说话）与 supervisor（只对编排者说话）保持独立，不合并；无 Spark Gate；无额度状态机字段。
- 升级保留：同一 Task 累计被 supervisor 打回 2 次自动升 senior-expert（Sol），或编排者判定 P0-hard 手动升；senior 接手后被打回 2 次即停线找人（详见本文件升级节）。

## 角色（9 常驻 + 1 升级专用，不再新增）

task-manager=编排者（唯一对人说话）｜supervisor=监督者（只对编排者说话，编排者失联时除外）｜planner｜builder｜code-reviewer｜qa｜product-reviewer（显示名 Research Reviewer，内部 ID 不变）｜experience-recorder｜neat-freak｜senior-expert=高级开发（只接升级任务）。职责看 `docs/roles/`，一句话一张。

## 谁写哪（写错地方打回）

| 谁 | 写哪 | 模板 |
|---|---|---|
| planner | `docs/pm/` | Phase1照PRODUCT_PLAN.template.md；Phase2照PLAN.template.md |
| builder | 业务仓库本身 | — |
| code-reviewer | `docs/review/` | CODE_REVIEW.template.md |
| qa | `docs/qa/` | BUGS.template.md |
| product-reviewer（Research Reviewer，ID 不变） | `docs/review/` | RESEARCH_REVIEW.template.md（Phase1；PRODUCT_BACKLOG.template.md 保留兼容） |
| task-manager | `docs/handoff/` | HANDOFF.template.md |
| supervisor | 无独立文档，打回写被检文件评论区 | — |
| experience-recorder | 根 `经验一句话.md`，追加一句 | — |
| neat-freak | 改对应 docs 原文+交接记一笔 | — |
| senior-expert | 业务仓库本身（只接升级任务） | — |

业务文件（src/assets/配置/AGENTS.md/旧交接）原地不动；搬了会 broken 的留原地记映射。

## 派工顺序（Phase-aware；旧单线默认链已废止）

Phase1（PLAN）：planner（Sol）→product-reviewer（Research Reviewer）→planner→…→Readiness Gate→Human Gate（禁 builder／code-reviewer／qa／业务改动／Release）。Phase2（DEVELOP）：builder 写→code-reviewer 复核→qa 测→supervisor 复检→编排者收齐找人（默认主链，模型以 override 表为准；product-reviewer 默认不派）。真机QA每session先过能力预检PASS才进正式，否则停（详情见qa卡）。经验/neat-freak 只在收尾派一次。本窗口内派 subagent，全自动（默认派工口；执行通道按 override『执行通道/Runtime』列，表定通道（codex/opencode）的走通道直调，禁套娃）。三类例外（人肉调试/外部施工/迁移基线）可起终端，见编排者提示词 :10。基础设施活必带 docs/sop/ 对应规范（DB 带 supabase.md 或 sqlite.md，部署带 docker.md），supervisor 抽查。
跳步：单文件小修可跳 planner/product，不可跳 code-reviewer+qa+supervisor；跳了记一句原因。分歧听谁的：技术分歧听 code-reviewer，范围分歧听 Task Manager。
续 session：同一功能/Bug 链（开发→QA→返工→再 QA）尽量续上一个 session（codex 用 resume），不要每轮新开；返工派必须续。用完不急着关，关了重开更贵。resume 由派工基础设施保持，编排者不手动开终端；升级换 senior-expert 时开新链，不续旧 session。
- External Builder Runtime 通用插座：builder 仍是 builder（9+1 不新增），Runtime 仅为执行通道（本窗口 subagent / codex / opencode / External Runtime），由 override「执行通道/Runtime」列或口头指定、派工基础设施自动调用；Runtime 自带 internal reviewer/QA/self-check 仅为自检证据，不能替代 code-reviewer/qa/product-reviewer/supervisor；permission_request 走机器可读→ORCA/TM 审批单点→用户定→回 runtime，builder 不直聊用户；禁把通道角色包进本窗口subagent套娃调用（表定codex/opencode的角色必须走通道直调），违者打回。

## 模型

每次派前读根 `USER_MODEL_OVERRIDE.md`，有就用它（10行以表为准）。精确 ID，照抄执行（TM行例外：开窗口时定）。表内无备用列：换人用户直接改母版真源表；DISPATCH 的 used 恒填主，supervisor 抽查实派==表。换谁、用到几时，用户定。分工表软链制：各项目根表均为软链，指母版真源，改母版即全项目同步（禁拷实文件；跨机器断链时拷实文件并记 HANDOFF）。

## 升级（普通→高级，只对当次任务）

- 触发：① 同一 Task 累计被 supervisor 打回 2 次自动升（QA 挂不算，只算 supervisor 打回） ② 编排者判定 P0-hard 手动升。满足一条即升。
- 计数口径：rework=被 supervisor 打回次数；QA 挂/自修好不计数，不断链也累计。
- 只升当次，不永久转正。换模型/换 Runtime 即开新链（旧链结论进 HANDOFF，缓存不跨链）。升级原因 + 返工次数记进任务账本。senior 接手后不再计数升级，被 supervisor 打回 2 次即停线找人（列阻塞＋要拍的板，不再升，无更高角色）。
- senior 模型读 `USER_MODEL_OVERRIDE.md` 的 senior-expert 行。

## 任务账本（换模型的依据，一个项目一个文件）

- 文件：`docs/model/TASK-MODEL-LOG.jsonl`，一行一任务，跨项目同名同 schema，分析时拼起来直接统计。模板自带的 `{"_example":true}` 行不参与统计，首个真实任务前删除。example 行由迁移整理工/首个 TM 在首个真实任务前删除。
- schema（全单行，枚举锁死）：`{"task","project","date","role","model","result":"PASS/FAIL","rework":数字,"escalated":"YES/NO","escalation_reason":null或一句,"tokens":数字或null,"cost_cny":数字或null}`。`cost_cny` 与 `tokens` 拿不到填 `null`，不许编；`project`=仓库根目录名（HANDOFF Stage ID 括号备注，如 radar-live），`date` 取 `YYYY-MM-DD`。
- 分工：builder/senior 写一行初版→supervisor 校验 JSON 合法+返工数→编排者判结果落盘。
- `result`=任务级 PASS/FAIL（按表派单成功仍可 PASS；FAIL 须配 escalation_reason/备注说明是任务挂还是模型挂）。
- 逐派记录：每次派工收工编排者往 `docs/model/DISPATCH-LOG.jsonl` 记一行（schema：date/task/role/model/used恒填主/runtime（本窗口/codex/opencode/—）/result PASS或FAIL/note；示例行不参与统计，首个真实派前删除；tokens/cost不记；寿命随任务账本归档）；与派工显式两行互验；supervisor抽查实派==表三处对得上。
- 两包同步：母版治理改动提交后同步两本地包（`新项目模板包/`、`老项目迁移模板包/`）并在 HANDOFF 记一行；`diff` 非预期差零容忍（常驻同步，用户定）。
- 换模型决策先读账本：返工多、常升级的任务类型优先换强模型。

## 缓存五条（各家通用，够用就行；本窗口 subagent 链适用，External Runtime 走 builder 通道，换 Runtime/换模型/升级即开新链，见编排者 :10-11；外部施工见外部提示词）

- 静态打头：派工先读同一批文件，顺序全体系唯一：AGENTS→角色卡→override 表→HANDOFF→经验一句话→任务目标放最后。prefix 稳定命中，谁也不许自创顺序。
- 动态押后：任务目标、git 状态、时间戳、随机 ID 永远放最后，system prompt 前面只放不变的东西。
- 同链续 session：一链之内不换派工基础设施与会话链（角色/工具按任务换，prompt 模板不变）；要换基础设施即开新链重起。
- 长了就压：超约 100k token（编排者估，用户可改）即写 HANDOFF 快照后开新链，旧链结论进 HANDOFF，历史扔掉。
- 缓存 best-effort，几小时到几天过期正常，不定 KPI，只定动作。

## 红线

- P0 没完+人没喊停，不准收工，不准“先到这里”。
- 每轮末三行心跳：目标/剩 P0/下一步。
- 不 push（commit 需编排者明确指令，含分支名，外部者用 `ext/` 开头）；不碰 secrets；不改旧版封存；`docs/sop/` 为基础设施规范位（docker.md/supabase.md/sqlite.md，去版本号引用），新项目自建（包内历史交接不动）。
- 换模型的事用户决策，不许自作主张、不许写恢复类条件。
- 总监督（体系外独立，不占9+1，编排者无权派工/解雇）：只读 AGENTS＋`docs/prompts/Orca 编排治理监督者提示词.md`（先读顶部收编说明，wake-only）＋HANDOFF 并按监督者提示词执行，监督编排者是否持续推进、防停摆；平时只喊编排者，禁主动问用户，同一停摆两次叫不醒才找用户一次；与体系内 supervisor（监督者）无关，不合并；质量判定走 supervisor 链，推进/停摆判定听总监督。
