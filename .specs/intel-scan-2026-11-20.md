# 入场扫描报告 · 2026-11-20

**扫描基线**：`main @ cf5f18f`（工作区另有 11 个已修改文件 + 7 个未跟踪项）
**执行**：`flow-kit/prompts/I-intel-scan.md`
**产物**：`.specs/CONTEXT.md`（已生成）、`STATE.md`（已生成）、本报告
**范围**：只读扫描，未改动任何业务代码

---

## 1. 既有文档探测（步骤 0）

- 探测命中：
  - `AGENTS.md`（仓库根，3367 B，45 行）— 标准 AI 上下文文档
  - `README.md`（217 行）、`docs/家庭学习助手系统架构与开发设计文档 V1.0.md`（1945 行）、`docs/技术决策记录.md`、`docs/项目交接文档-20261104.md` 等 25 份 docs
  - 未发现 `CONTEXT.md` / `CLAUDE.md` / `.cursor/rules` / `.windsurf` / `.copilot-instructions` / `.clinerules`
- 用户选择：**分支 A 选项 1（综合 + 扫描）** — 由本次指令直接指定（"执行 intel-scan 生成 CONTEXT.md + 重点读现有架构文档"），未再反问
- 决策：生成 `.specs/CONTEXT.md`，`AGENTS.md` 中「capability_guide 维护规范」「Tool Calling 约定」已原样纳入 `默认偏好` / `禁动清单`
- 引用源：架构 V1.0（§2.3 / §3 / §4 / §5 / §24 / §26）、技术决策记录 TD-01~TD-16、交接文档 §3-§5 / §13、Tool Calling Phase0 §10-§11、Phase1 §2 / §9

---

## 2. 项目元信息实测

| 探测项 | 结论 | 证据 |
|---|---|---|
| 语言/运行时 | Python 3.12（CI 用 3.13）+ Node（本地构建） | `backend/pyproject.toml:6`、`.github/workflows/ci.yml:15` |
| 后端框架 | FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic | `backend/pyproject.toml` |
| Agent | LangGraph 1.2，单图 5 节点 | `agent/runtime.py:54,199-205` |
| 前端 | React 19.3 / TS 5.9 / Vite 8 / Router 7 / Playwright | `frontend/package.json` |
| 规模 | 后端 `app/` 8,300 行、前端 `src/` 12,382 行、测试 3,561 行 | `wc -l` |
| 数据表 | 20 张业务表 | `grep __tablename__` |
| 迁移 | 单链 0001 → d84e7517a216 → 0002…0006，单 head，无分叉 | `alembic/versions/*` |
| 测试 | pytest 112 用例；Playwright 8 spec / 23 用例 | `pytest --collect-only`、`grep -c "test("` |
| Lint | ruff（line-length 100，规则 E/F/I/B/UP）| `backend/pyproject.toml:38-46` |
| CI | 3 job：SQLite 后端 / MySQL 8.4 后端 / 前端 typecheck+build+audit+e2e | `.github/workflows/ci.yml` |
| 容器化 | Dockerfile×2 + compose，但从未在 daemon 下构建成功 | 交接文档 §13.2 |
| 部署 | systemd + Nginx + `serve_spa.py`，本地构建上传 | `deploy/project2.service` |

---

## 3. 模块与依赖（实测）

11 个业务模块：`user` / `vocabulary` / `material` / `content` / `task` / `question` / `practice` / `learning` / `conversation` / `agent` / `admin`。

依赖方向（实测 import）：

```text
agent       → content, material, practice, task, vocabulary, learning
content     → material
practice    → question, task, vocabulary
task        → vocabulary
learning    → practice
admin       → user, learning
```

`question` 无对外 router（内部能力）；`learning` 无 repository / 无自有表（只读聚合）。

---

## 4. 文档 vs 代码差异（需确认）

> 判定标准：架构 V1.0 是**目标架构**。以下条目不是"文档写错了"，而是"现状尚未达到目标"或"目标已被后续决策改变"，AI 后续开发必须知道真实情况。

| # | 主题 | 文档说法 | 代码实测 | 性质 | 建议 |
|---|---|---|---|---|---|
| **D1** | Dictation 模块 | §3.1 列为独立模块，拥有听写业务数据；§4.3 有 `DictationPracticeHandler` | **不存在 `dictation` 模块**，无听写表。听写配置存 `tasks.config_json`，判分在 `practice/service.py` | 目标未落地（可能已被"不提前抽象"策略吸收）| 确认是否正式废弃 Dictation 独立模块，若废弃则修订架构 §3.1 / §4 |
| **D2** | Handler Registry | §4.2/§4.3 要求 `VocabularyTaskHandler` / `DictationTaskHandler` + Registry | 全库无 Handler 类，`task_type` 分支散在 service | 目标未落地 | 与 D1 一并决策；建议保留为"出现第三种学习类型时再抽象" |
| **D3** | Agent Workflow | §5.4 规划 4 个 Subgraph（Material/Vocabulary/Task/Learning） | 单图 `classify → tool_create → prepare → wait → respond`；4 类业务全在 `prepare` 节点内用 Python 正则解析 | **已被后续决策改变**（Tool Calling 改造）| 架构 §5.4 需重写为"单图 + 场景工具集" |
| **D4** | 模块边界 | §3.3 第 1 条禁止跨模块访问 Repository | 实测 9 处跨模块 Repository import：`agent`→5、`practice`→3、`task`→1 | **现存违规**（Phase0 已标记 ❌）| 不回改存量；新增代码强制走对方 Service，写入 `CONTEXT.md` 技术债 |
| **D5** | 目录结构 | §24 建议 `app/api/routes/`、`backend/migrations/`、`tests/{unit,integration,graph,e2e}` | 业务路由在各 `module/router.py`；迁移在 `alembic/`；测试扁平 `tests/test_*.py` | 文档自称"建议目录，可微调"，属正常偏差 | 无需改代码，架构文档标注"实际采用模块内 router" |
| **D6** | 部署拓扑 | 交接文档：`https://yidongxun.com` 根路径，8002/8003 | HEAD `cf5f18f` 已改为 **`/zijixue` 子路径**（`VITE_BASE_PATH=/zijixue/`），且 `frontend/nginx.conf` 仍按根路径 `/api/` 写 | **文档过期 + 配置不一致** | **已确认（2026-11-20）**：对外域名改为 `zijixue.xyz`，`yidongxun.com` 停止服务。base 路径与域名是否匹配待一次发布确认，见 `.specs/ARCHITECTURE.md` §6 |
| **D7** | 测试基线 | 开发进度 68 passed；Phase1 记录 101/106 passed | 当前 112 用例 | 文档过期（正常演进）| 发布记录类文档不改；CONTEXT 用实测值 |
| **D8** | Tool Registry 规模 | Phase0：7 个工具（6 个占位）| 现仅 2 个真实工具（`learning.stats`、`task.create_preview`）| 已按 AGENTS.md 收敛 | Phase0 文档已过时，仅供历史参考 |
| **D9** | 生产库名 | 交接：`english_forest`；TD-04 示例：`familylearning`；compose：`familylearning` | 以生产交接文档为准（`english_forest`）| 多环境命名不统一 | 在部署文档中明确"生产库名 ≠ 示例库名" |
| **D10** | 灰度开关 | AGENTS.md / config：默认 `false` | 生产实际 `true`（交接 §5.5） | 环境差异，非矛盾 | 部署检查清单中标注"生产必须显式开启" |

### 另外两项文档状态问题

- 架构文档首部仍写「**状态：架构决策已确认，进入开发设计阶段**」，但项目已于 2026-11-02 上线生产、当前在持续迭代 —— 状态字段过期。
- 工作区有 **未提交改动**（`admin` 执行详情/Checkpoint 巡检、Agent 脱敏、AdminPage、新增 `infrastructure/observability/`），任何文档均未记录，属进行中的功能。

---

## 5. 待用户确认（阻塞后续架构文档更新）

| # | 问题 | 影响 |
|---|---|---|
| Q1 | **Dictation 是否正式不再作为独立模块**（D1/D2）？ | 决定架构 §3.1/§4 是修订还是保留为目标 |
| Q2 | 当前**生产访问入口**是 `sunxinshan.site/zijixue` 还是 `yidongxun.com`？两者并存吗？ | ✅ **已确认 2026-11-20**：对外域名 `zijixue.xyz`，`yidongxun.com` 已停止服务；路径（根 vs `/zijixue/`）待发布时确认 |
| Q3 | Agent 架构是否以「单图 + 场景工具集」为**新基准**（D3），架构 §5.4 是否可直接重写？ | ✅ **已按指示处理 2026-11-20**：单图 + 工具集写入 `ARCHITECTURE.md` ADR-001 作为现基准，V1.0 §5.4 保留为设计意图 |

**已解决的决策（2026-11-20 用户确认）**

- Q5 → 新建 `.specs/ARCHITECTURE.md` 作为 as-built 现状版，V1.0 保留为设计意图（已完成）
- Q1 / Q4 仍在 `ARCHITECTURE.md` §1.4 中按「设计已收敛 / 记为技术债」标注，可随时推翻
| Q4 | 跨模块 Repository 访问（D4）是**接受为技术债**，还是要立重构 CHANGE？ | 决定是否进 backlog |
| Q5 | 是否需要生成 `.specs/ARCHITECTURE.md`（as-built 现状版），还是直接修订架构 V1.0 文档？ | 决定本次文档整理终态 |

---

## 6. 本次未做

- 未修改任何业务代码、迁移、配置。
- 未运行完整测试套件（仅 `--collect-only` 统计用例数）。
- 未访问生产服务器，生产事实均来自仓库内文档与 `.env.production` / `deploy/`。
