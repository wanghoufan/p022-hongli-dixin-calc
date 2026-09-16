
# BUGS

结论：PASS（D11-DOCKER-001、D11-DOCKER-002 均已关闭；无 OPEN 残留）

| Bug ID | Priority | Stage P0 Blocking? | Repro | Status | Current Task | 备注（截图/日志一句） |
|---|---|---:|---|---|---|---|
| D11-DOCKER-001 | P1 | NO | 读取 `docker/env.template:3-11` | CLOSED | 修正 Docker 环境模板 | §4.1 要求模板只含变量名、说明和占位符；复验确认仅含变量名、说明和占位符。 |
| D11-DOCKER-002 | P1 | NO | 读取 `compose.yaml:8-18` | CLOSED | 修正 Compose 持久化路径默认值 | §4.3 要求 bind mount 宿主机目录预先存在且不得静默创建未知路径；复验确认数据目录与备份目录均为显式 bind mount，`APP_DATA_DIR`/`APP_BACKUP_DIR` 均为必填变量且无 `/tmp` 默认值。 |

## 验收证据

- 四件套齐全：`Dockerfile`、`compose.yaml`、`.dockerignore`、`docker/env.template` 均存在。
- D11-DOCKER-001 本次复验：`docker/env.template` 纯占位，仅含变量名、说明和 `<...>` 占位符，无具体值；符合 §4.1，状态 CLOSED。
- D11-DOCKER-002 本次复验：`compose.yaml` 同时声明数据目录与备份目录两个显式 bind mount；`APP_DATA_DIR`、`APP_BACKUP_DIR` 使用必填变量校验，未设置 `/tmp` 默认路径；符合 §4.3，状态 CLOSED。
- 无真实密钥值：四件套 grep 未发现 API key、token、password、service role、私钥等真实密钥模式；模板仅有说明文字。
- 端口/路径：宿主端口、公开 URL、数据/备份路径均有变量接口；数据与备份目录均通过必填变量绑定，未设置 `/tmp` 默认路径。
- `dev.db`：工作区存在 `dev.db`、`dev.db-wal`、`dev.db-shm`，均未被 Git 跟踪；`.gitignore` 与 `.dockerignore` 均有对应排除规则。
- Python 语法：`server.py` 及 `db/*.py` 全部通过 `ast.parse` 检查。
- Docker 构建：`docker build -t dividend-portfolio:v1.3.0 .` 通：镜像 `dividend-portfolio:v1.3.0` 构建成功。
- 容器访问：容器端口 `8771` 返回 HTTP 200；本地端口 `8779` 默认访问返回 HTTP 200。
- Git 排除：`.gitignore` 含 `.env*.local`，本地环境文件已排除。

## 真机QA会话能力预检结果

- 本次为文件级 QA，不进入真机 QA 会话；不适用。

## Fix Attempt Fingerprint

- Task ID: D11_docker
- Root Cause Hypothesis: Docker 模板与 Compose 默认值沿用了可运行示例，未完全落实 §4 的模板占位和宿主目录预创建约束。
- Approach: 只读检查规范、四件套、Git/ Docker 排除规则、Python 语法；未修改业务文件。
- Files Changed: 仅本文件。
- Verification: 见“验收证据”。
- Failure Reason: 无；D11 Docker 验收项全部通过。
- Difference From Previous Attempt: 本次复验已覆盖镜像构建、容器/本地端口访问、环境模板占位、Compose 双 bind mount 与必填变量门禁。
