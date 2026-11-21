# CONTEXT — 家庭学习助手（Family Learning Assistant）

> 本文件跨 change 长期累积，是 AI 在 2-design / 3-task / 4-dev 阶段的项目级默认上下文。
> **生成方式**：`I-intel-scan` @ 2026-11-20，代码实测为主 + 既有文档综合。
> **冲突处理原则**：`docs/家庭学习助手系统架构与开发设计文档 V1.0.md` 是**设计意图（目标态）**，不等于**当前实现**。
> 系统现在**实际怎么搭**以 `.specs/ARCHITECTURE.md`（as-built）为准；两者差异清单见其 §1.4，扫描证据见 `.specs/intel-scan-2026-11-20.md`。

---

## 源文档

| 文档 | 性质 | 本文件引用点 |
|---|---|---|
| `docs/家庭学习助手系统架构与开发设计文档 V1.0.md`（1945 行）| **架构基准（目标态）** | 核心原则 §2.3、模块清单 §3.1、禁止事项 §3.3、Agent 架构 §5、编码约束 §26 |
| `docs/技术决策记录.md`（181 行）| **已锁技术决策 TD-01~TD-16** | 「已锁决策」段主要来源 |
| `docs/项目交接文档-20261104.md`（640 行）| 生产运行态 + 已知风险 | 「运行拓扑」「禁动清单」「技术债」 |
| `docs/Tool_Calling与Tool_Registry改造-Phase0现状审查.md` | 代码与文档差异的官方审计 | 「文档偏差」段 |
| `docs/Tool_Calling与Tool_Registry改造-Phase1实施记录.md` | Agent 改造当前进度 | 「Agent 现状」 |
| `AGENTS.md`（45 行）| **能力清单维护规范 + Tool Calling 约定（强制）** | 「默认偏好」「禁动清单」 |
| `README.md`（217 行）| 产品定位与模块规划 | 「项目概要」 |

---

## 项目概要

面向家长的 AI 学习助手：家长用自然语言跟 Agent 对话，上传 Excel/CSV 教材，由 Agent 组织「解析 → 建词库 → 建听写任务 → 练习 → 看记录」的链路。
不是固定课程平台，**Agent 是统一入口，业务页面与 Agent 调用同一套 Service**（架构文档 §1.3）。
MVP 只做两种学习类型：**Vocabulary（词汇）** 和 **Dictation（听写）**，不提前抽象通用学习类型接口（§4.1）。

---

## 技术栈（团队级默认 / 已锁定）

| 层 | 技术 | 证据 |
|---|---|---|
| 后端语言 | Python ≥3.12,<3.15 | `backend/pyproject.toml:6` |
| 后端框架 | FastAPI + Uvicorn + Pydantic v2 | `backend/pyproject.toml:10,23` |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic | `backend/pyproject.toml:22`、`backend/alembic.ini:2` |
| Agent 编排 | LangGraph 1.2 + `langgraph-checkpoint-mysql` / `-sqlite` | `backend/pyproject.toml:13-15` |
| LLM | DeepSeek OpenAI-compatible（`deepseek-v4-flash`）| `docs/技术决策记录.md#TD-16` |
| 业务库 | 生产 MySQL 8（库名 `english_forest`）；本地 SQLite | `docs/项目交接文档-20261104.md:66` |
| Checkpoint 库 | 生产 MySQL（`langgraph-checkpoint-mysql`）；本地 SQLite | `backend/app/core/config.py:30-32` |
| 前端 | React 19.3 + TypeScript 5.9 + Vite 8 + React Router 7 | `frontend/package.json` |
| 前端状态 | React Context（自研 AppStore），**无** redux/zustand | `frontend/src/stores/AppStoreContext.ts:39` |
| 实时通道 | SSE（`sse-starlette`），事件持久化 + `after_sequence` 重放 | `backend/app/modules/agent/runtime.py:576` |
| 测试 | 后端 pytest（112 用例）；前端 Playwright E2E（8 个 spec / 23 条用例，desktop + mobile 两 project）| `backend/tests/`、`frontend/playwright.config.ts:19,23` |
| 部署 | systemd（`project2.service`）+ Nginx + 本地构建产物上传 | `deploy/project2.service`、`docs/项目交接文档-20261104.md:149` |
| CI | GitHub Actions 三 job：① SQLite 后端 ruff+pytest+alembic ② MySQL 8.4 后端 pytest ③ 前端 typecheck+build+npm audit+Playwright | `.github/workflows/ci.yml:7,25,72` |

**栈卡片编号**：`tech-stacks.md` 未逐条比对；本项目为「Python FastAPI 后端 + React SPA 前端 + LangGraph Agent」定制组合，不走标准模板。

---

## 运行拓扑（当前生产）

```text
Internet → Nginx :443（zijixue.xyz）
   ├─ /                  → 静态 SPA（127.0.0.1:8003, serve_spa.py）
   ├─ /api/*             → FastAPI + LangGraph（127.0.0.1:8002；SSE 需 proxy_buffering off）
   └─ MySQL 127.0.0.1:3306 / english_forest
```

- **对外域名：`https://zijixue.xyz`**（2026-11-20 已上线，根路径）。`yidongxun.com` **已停止服务**，旧文档里出现的该域名一律视为历史。
- 生产前端基路径由 `frontend/.env.production` 的 `VITE_BASE_PATH=/` 决定；接口前缀由 `BASE_URL` 推导为 `/api/v1`。
- 旧的 `sunxinshan.site/zijixue` 子路径入口保留为 **301 → `https://zijixue.xyz`**；配置分别在 `/etc/nginx/conf.d/sunxinshan.conf` 与 `zijixue.xyz.conf`，源文件存 `/opt/project2/nginx/`。
- 证书：Let's Encrypt 独立一张 `zijixue.xyz`（含 `www`），webroot 方式，`/var/www/acme`。
- 单 worker 运行，Agent 在进程内后台线程执行（全局锁）——**多实例前必须先做共享队列 + Worker**（交接文档 §13.2）。
- 服务器无 Node/npm/uv，**前端必须本地构建后上传**（交接文档 §4.3）。

### 部署与运行陷阱（踩过的坑，别再踩）

- **后端发布只需覆盖 `backend/app/`**。release 里的 `app` 有两份：源码目录与 venv 内 `site-packages/app/`（早期安装的残缺副本，缺 `executor.py`）。uvicorn 会把 cwd 插到 `sys.path` 最前，实际从源码目录导入，`site-packages/app` 不参与运行，不必重装包。
- **改前端产物不用重启**：`serve_spa.py` 启动时 `resolve()` 了 `frontend/dist`，按请求读盘；原地换目录内容即可生效。换目录名则会 404。
- **LangGraph 的 MySQL checkpointer 是单条长连接**（`PyMySQLSaver.from_conn_string`），MySQL `wait_timeout=28800` 会掐断空闲连接且客户端不自愈。2026-11-20 已在 `runtime.py` 加 `ping(reconnect=True)` 探活 + 连接级异常重试一次；**新增任何长连接持有方都要照此处理**。
- 业务库走 SQLAlchemy，已有 `pool_pre_ping=True` + `pool_recycle=1800`，不需要额外处理。
- 服务器上 `/usr/local/bin/project2-apply-certbot` 写死 `yidongxun.com`，已过期，**不要使用**。

---

## 模块现状（实测 · 代码为准）

| 模块 | 实际职责 | 拥有的表 | 文件形态 |
|---|---|---|---|
| `user` | 注册登录、JWT + 可撤销 Refresh Session、用户隔离、管理员用户管理 | `users`、`user_sessions` | router/service/repository/models/schemas |
| `vocabulary` | 学科、词库、标签、词条、词汇掌握状态、公共词库发布/撤回/复制 | `subjects`、`vocabularies`、`vocabulary_tags`、`word_entries`、`vocabulary_learning_states` | 全分层 |
| `material` | 上传原始文件与元数据 | `materials` | 全分层 |
| `content` | XLSX/CSV 服务端解析、表头映射（规则优先 + LLM 兜底）、字段补全、预览草稿 | `content_extractions` | 全分层 |
| `task` | 任务、任务快照、固定/长期模式、听写配置、进度 | `tasks`、`task_snapshots`、`task_snapshot_entries` | 全分层 |
| `question` | 题目生成与存储（内部能力，**无对外 router**）| `questions` | service/repository/models（无 router）|
| `practice` | 练习生命周期、答题、线上自动判分、线下自查、错题复习、轮次与强制重做 | `practice_attempts`、`practice_answers` | 全分层 |
| `learning` | 学习统计（只读聚合，无自有表）| — | router/schemas/service（无 repository）|
| `conversation` | 会话与消息（`text` / `tool_call` / `tool_result`）| `conversations`、`conversation_messages` | 全分层 |
| `agent` | LangGraph 主图、意图分类、Tool Registry/Executor、SSE、执行详情与脱敏、能力引导兜底 | `agent_runs`、`agent_run_events` | runtime/tools/executor/llm/prompt_registry/… |
| `admin` | 管理员用户管理、公共词库管理、操作日志、Checkpoint 巡检（未提交）| `operation_logs` | 全分层 + `checkpoint_repository.py` |

合计 **20 张业务表**（`grep __tablename__` 实测）。

### 依赖方向（实测调用关系）

```text
agent      → content / material / practice / task / vocabulary / learning（6 个模块的 Repository + Service）
content    → material
practice   → question / task / vocabulary
task       → vocabulary
learning   → practice
admin      → user / learning
conversation → 仅自身
```

### Agent 现状（重点 · 与架构文档不同）

- 单张 LangGraph：`classify → (tool_create) → prepare → wait → respond`，见 `runtime.py:54,199-205`。
- 意图路由枚举 8 个：`task_create / task_update / task_delete / vocabulary_create / vocabulary_import / learning / chat / unclear`（`llm.py:472-474`）。
- **Tool Registry 只注册了 2 个真实工具**：`learning.stats`（只读）、`task.create_preview`（`tools.py:59-89`）。占位实现已删除。
- 灰度开关 `FLA_AGENT_TOOL_CALLING_ENABLED` 默认 `false`（`config.py:43`）；**生产实际已置 `true`**（交接文档 §5.5）。关闭即回退到 Python 正则链路。
- 除 `task_create` 外，其余场景仍走 `prepare` 节点内的 Python 解析（Phase1 §9 已知限制）。
- 确认协议：`action_id + draft_version + config_hash`，LangGraph `interrupt` 挂起（TD-05）。

---

## 域语言（术语表）

| 术语 | 定义 |
|---|---|
| 词库（Vocabulary）| 一个可练习的单词/词语集合，分个人词库与公共词库；含学科（英语/语文）属性 |
| 词条（WordEntry）| 词库内单条记录：词、音标/拼音、词性、释义、例句 |
| 固定任务 | 创建时锁定词条快照与内容的任务，内容不可改，只可改名称/重做规则/听写配置 |
| 长期任务 | 按分组重复练习的任务，使用稳定快照参与练习，`words_per_group` 生效 |
| 任务快照（TaskSnapshot）| 创建任务时对词条的拷贝，后续词库变化不影响已有任务 |
| Attempt | 一次练习实例，可中断/恢复；错题复习是独立 Attempt（`kind=wrong`）|
| 轮次（round）| 强制重做模式下的一遍全词循环；错词进入下一轮，连续两轮拼对才过关 |
| 线上听写 | 服务端自动判分 |
| 线下听写 | 用户自查错误项（`submit_self_check`）|
| 草稿预览（pending_action）| Agent 生成的待确认操作，只读、无副作用；确认后才由 Service 写入 |
| 能力引导兜底（capability guide）| 意图无法路由时读 `capability_guide.md` + LLM 生成引导文本，**不执行任何业务操作** |
| Run | 一次 Agent 执行，`agent_runs` 一行；事件按 `(run_id, sequence)` 持久化供重放 |
| 执行详情 | 面向用户/管理员的 Agent 运行轨迹视图，返回前递归脱敏 |

---

## 已锁决策

按时间倒序（详细条目见 `docs/技术决策记录.md`）：

- `[2026-11-05]` Agent 采用原生 Tool Calling + Registry/Executor 分权，`task_create` 首批接入；工具名内部用点号、Provider 侧转下划线 — TD/Phase1
- `[2026-11-04]` 意图失败改为能力引导 + LLM，不再返回固定字符串 — `docs/意图识别兜底引导实施记录.md`
- `[2026-11-02]` 生产统一 DeepSeek `deepseek-v4-flash`，Key 只存 `.env` — TD-16
- `[2026-11-02]` Excel 导入「规则优先、模型兜底」，模型输出必须服务端二次校验 — TD-13
- `[2026-11-02]` 导入字段补全只填空字段，绝不覆盖用户内容 — TD-14
- `[2026-11-02]` Agent 事件持久化 + `after_sequence` 重放；Graph 在后台线程执行，SSE 断开不取消 — TD-03 / TD-09
- `[2026-11-02]` 短期 JWT + 数据库可撤销 Refresh Session，轮换即撤销旧会话 — TD-02
- `[2026-11-02]` 前端只依赖 `api` 组合根；Mock 仅 `VITE_API_MODE=mock` 时启用 — TD-01
- `[2026-11-02]` 两阶段删除任务（第一次确认只生成第二确认动作）— TD-06
- `[2026-11-02]` MySQL Checkpoint 库必须 `utf8mb4_0900_*` 排序规则；推荐独立库 — TD-04
- `[架构 V1.0]` Agent 是编排者不是业务所有者；Service 是业务规则与数据操作的唯一入口；模块拥有自己的数据；Checkpoint 不是业务存储 — 架构 §2.3 / §28

---

## 默认偏好（AI 缺省按此决策）

- **命名**：后端文件/函数 `snake_case`；前端页面与组件 `PascalCase.tsx`，`api/`、`utils/`、`stores/` 用 `camelCase.ts`；测试 `test_*.py`（后端扁平放 `tests/`）、`*.spec.ts`（前端 `e2e/`）。
- **分层**：`router → service → repository → model`。权限与用户隔离在 **Service 层**再校验一次，不能只依赖前端或 router（交接文档 §4.1）。
- **错误处理**：后端统一 `AppError(code, message, status_code, details)`，响应体 `{error:{code,message,details,request_id}}`（`core/exceptions.py:9,26`）；前端统一走 `httpClient` 的 401 → 单例 Refresh Promise 只重试一次（TD-10）。
- **身份**：`user_id`/`role` 只来自后端认证上下文（`RuntimeContext`，`core/security.py:17`），**Schema 里不得出现身份字段**，且 `extra="forbid"`。
- **状态管理**：React Context（`AppStore`）+ `api` 组合根，不引入新状态库。
- **测试**：测试从验收准则派生；后端 pytest 用 `TestClient` + 临时 SQLite（`tests/conftest.py:14-43`）；Agent 测试用 Fake LLM，真实 LLM 只做冒烟。
- **时间**：全部存 UTC，SQLite 读出后补时区（`core/models.py:17`UTCDateTime）；主键 UUID 字符串 36 位（`core/models.py:45`IdMixin）。
- **提交**：`<type>: <subject>`（现状为英文 Conventional 风格，如 `feat: deploy under /zijixue subpath`）。
- **能力清单**：`capability_guide.md` **只在明确要求时增量更新**，禁止全量重扫；只写用户语言，不写类名/函数名/Tool 名（`AGENTS.md`）。

---

## 既有抽象索引（防重复实现）

### 后端

| 类型 | 路径 | 入口 |
|---|---|---|
| 统一异常 | `backend/app/core/exceptions.py` | `AppError` / `error_body` / `app_error_handler` |
| DB 会话 | `backend/app/core/database.py:34,73` | `Database.session()` / `get_session()` |
| 模型基类 | `backend/app/core/models.py` | `IdMixin` / `TimestampMixin` / `UTCDateTime` / `new_id()` |
| 认证与身份 | `backend/app/core/security.py:17-42` | `RuntimeContext` / `get_current_user` / `require_admin` |
| 文件存储 | `backend/app/infrastructure/storage.py:8` | `LocalFileStorage.save/delete`（扩展名白名单 + 哈希文件名 + 大小上限）|
| Checkpoint | `backend/app/infrastructure/checkpoint.py:12` | `CheckpointerManager`（sqlite/mysql 由 `FLA_CHECKPOINT_BACKEND` 切换）|
| LLM 适配 | `backend/app/modules/agent/llm.py` | `create_llm_adapter` / `chat` / `chat_with_tools` / `classify_intent` |
| Tool 体系 | `agent/tools.py:45`、`agent/executor.py:15`、`agent/tool_schemas.py` | `ToolRegistry` / `ToolExecutor` / `ToolContext` |
| Prompt 版本 | `agent/prompt_registry.py` + `agent/prompts/*.txt` | 版本 + 哈希记录进 run |
| 脱敏 | `agent/redaction.py` | 递归屏蔽 token/password/cookie/secret/credential |
| 指标 | `backend/app/core/metrics.py` + `/health/metrics` | 请求数/错误数/延迟 |
| 请求上下文 | `backend/app/core/middleware.py` + `core/context.py` | `request_id` / `RequestContextMiddleware` |

### 前端

| 类型 | 路径 | 入口 |
|---|---|---|
| API 组合根 | `frontend/src/api/index.ts:33-39` | `api`（页面只依赖它，禁止直接 fetch / localStorage）|
| HTTP 客户端 | `frontend/src/api/httpClient.ts:6,74` | `API_BASE_URL`（跟随 `BASE_URL`）、单例 `refreshPromise` |
| 业务 API | `frontend/src/api/httpApi.ts`（702 行）| 各域方法 + SSE 接入 |
| 全局状态 | `frontend/src/stores/AppStore.tsx` + `AppStoreContext.ts:39` | `useAppStore()` |
| Excel | `frontend/src/utils/excel.ts` | 模板生成 / 解析（`read-excel-file`、`write-excel-file`）|
| 格式化 | `frontend/src/utils/format.ts` | 数字/日期/进度文本 |
| 选择器 | `frontend/src/utils/selection.ts` | 可见快照选择（防隐藏旧选择误删，TD-15）|
| 语音 | `frontend/src/utils/speech.ts` | 听写朗读（Web Speech）|
| 键盘避让 | `frontend/src/features/practice/useKeyboardViewport.ts:22` | 移动端软键盘 |
| 通用 UI | `frontend/src/components/ui.tsx` | 按钮/弹层/toast 等基础件 |

---

## 禁动清单（AI 不许"顺手"碰）

- `backend/app/modules/agent/prompts/capability_guide.md`：只按 `AGENTS.md` 规则增量改，禁止全量重写、禁止写入未接通能力。
- `backend/alembic/versions/*` 已应用迁移：禁止改写历史 revision；新变更只能追加新迁移（R4.5）。
- 生产 `legacy_*` 表（49 张）、`/opt/project2/releases/`、`shared/`、`backups/`：**未经确认不得删除或改结构**（交接文档 §6.3/§13）。
- `backend/app/modules/agent/runtime.py` 的确认协议（`action_id / draft_version / config_hash`）与 interrupt 流程：改动属架构级，需走 CHANGE。
- `backend/app/core/config.py` 的 `FLA_` 前缀与 `.env` 约定：新增配置必须走 `Settings`，禁止散落 `os.environ`。
- `frontend/src/api/mockApi.ts` / `mockAgent.ts`：Mock 层必须与 `httpApi` 接口签名同步，不可被页面直接引用。
- `.github/workflows/ci.yml`：MySQL job 的 `utf8mb4_0900_ai_ci` 相关配置不要随意改（Checkpoint 依赖）。

---

## 技术债（给 2-design / 4-dev 参考，别再加同类债）

| 债项 | 证据 | 影响 | 建议 |
|---|---|---|---|
| **跨模块直接访问 Repository**：`agent/service.py` 直连 5 个模块 Repository；`practice` 直连 3 个；`task` 直连 1 个 | `agent/service.py:13-24`、`practice/service.py:22-26`、`task/service.py:20` | 违反架构 §3.3 第 1 条；模块边界靠约定而非结构保证 | 新增代码一律经对方 Service；存量随功能重构收敛 |
| **无 Task/Practice Handler 抽象** | `grep Handler` 全库仅错误处理命中 | 架构 §4 的 Handler Registry 未落地，听写/词汇分支散落在 service | 第三种学习类型出现时再抽，不提前做 |
| Agent 大字段 | `pending_action_json` 峰值 ~319k 字符 | 存储/传输/清理压力 | 治理策略待定（交接文档 §13.1）|
| 超大任务详情 ~1.5 MB | 7,956 词任务 | 详情页打开慢 | 后续分页/分段加载 |
| 单 worker + 全局锁 | `runtime.py` 进程内执行 | 无法水平扩展 | 多实例前必须共享队列 + Worker |
| 前端无单元测试 | 仅 `e2e/*.spec.ts`（8 个 spec）| 工具函数与 store 逻辑裸奔 | 引入 vitest 时优先补 `utils/` |
| 部署文档漂移 | 交接文档写 `yidongxun.com`（已停服）；现域名 `https://zijixue.xyz`，前端 base `/` | 按旧文档部署会错 | 2026-11-20 已完成根路径迁移，见 `docs/生产部署记录-20261120.md` |
| Docker 链路未验证 | `docker-compose.yml` 存在但从未在 daemon 下构建 | 容器化方案不可信 | 需要时再补验证 |

---

## intel-scan 元数据

- **last_intel_scan**: `2026-11-20`
- **scanner**: `flow-kit/prompts/I-intel-scan.md`
- **扫描基线**: `main @ cf5f18f`（工作区另有 11 个文件未提交改动，见扫描报告）
- **下次重扫建议**: 架构重构 / 框架升级 / 新增业务模块 / 超过 90 天
- **本次未覆盖**: 生产服务器实际配置（`/etc/nginx/conf.d/project2.conf`、`shared/env/familylearning.env`）不在仓库内，仅按文档与 `deploy/` 推断
