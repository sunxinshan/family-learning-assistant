# TEST: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **关联**: `@.specs/checkpoint-replay/REQUIREMENT.md`、`@flow-kit/reference/test-pyramid.md`
- **项目类型**: 全栈 Web，但**本 change 只动后端**（前端 UI 属 v2，7 个前端文件在 WIP 基线 `0383acd` 里，与本 change 无关）
- **测试基线**: `main @ 65bee2d` + 本次新增 `tests/test_checkpoint_replay_resilience.py` 与 `uv.lock`（dnspython 升级）
- **执行日期**: 2026-11-22

---

## 0. 本次测试范围声明（5 轮金字塔）

| 轮次 | 状态 | 范围 | 跳过理由 |
|---|---|---|---|
| 第 1 轮 · 功能 | ✅ 必跑 | AC-1 ~ AC-7 全覆盖，140 用例 | — |
| 第 2 轮 · 性能 | ⚠️ 部分 | 60s 预算实测 + 在线影响（锁/连接）+ 查询次数 | 管理端点、单管理员手工触发，无并发场景，不跑 k6/locust |
| 第 3 轮 · 安全 | ✅ 必跑 | 依赖 / 秘钥 / SAST / OWASP（A01/A03/A07 实测） | — |
| 第 4 轮 · 兼容 | ⚠️ 部分 | API 向前兼容 + 旧 checkpoint 数据可读 | 无 schema 变更（0 个 alembic 文件）、无本 change 前端改动，跨浏览器 N/A |
| 第 5 轮 · 可观测 | ✅ 必跑 | 日志四字段 / PII / 健康检查 / metric 缺口 | — |

判定依据：全栈 web 属「第 1/2/3/5 必跑」，但本 change 无前端产物、无 schema 变更，故第 2、4 轮按实际裁剪，理由如上（R5.4 要求显式）。

---

## 第 1 轮 · 功能测试

### 1.1 测试矩阵（AC → 用例）

| AC | 类型 | 用例文件 | 状态 |
|---|---|---|---|
| AC-1 能重放并对照 | integration | `test_checkpoint_replay_api.py::test_replay_returns_200_with_camel_case_contract` | ✅ |
| AC-2 原 thread 零污染 | unit | `test_checkpoint_replay_unit.py::test_replay_does_not_pollute_source_thread` | ✅ |
| AC-2（HTTP 视角） | integration | `test_checkpoint_replay_api.py::test_replay_keeps_thread_checkpoint_total_unchanged` | ✅ |
| AC-3 不产生业务副作用 | unit | `test_checkpoint_replay_unit.py::test_replay_writes_no_business_rows` | ✅ |
| AC-4 明确拒绝 | unit | `test_replay_rejects_unknown_checkpoint` / `_terminal_checkpoint` / `_interrupted_checkpoint` / `_entry_checkpoint_without_parent` | ✅ |
| AC-4（HTTP 视角） | integration | `..._rejects_unknown_checkpoint_with_404` / `..._rejects_terminal_checkpoint_with_409` | ✅ |
| AC-5 可重复 | unit | `test_replay_is_repeatable_and_keeps_previous_replay_thread` | ✅ |
| AC-6 权限与降级 | integration | `test_replay_requires_admin` / `test_replay_degrades_when_checkpoint_store_missing` | ✅ |
| AC-7 不拖垮在线服务 | unit | **本次新增** `test_checkpoint_replay_resilience.py::test_replay_returns_504_when_the_graph_exceeds_its_budget`、`test_replay_does_not_wait_for_the_execution_lock` | ✅ |
| 锚点正确性（DESIGN §2.3 修正） | unit | `test_replay_runs_only_remaining_nodes` | ✅ |
| 锚点解析（Repository） | unit | `test_checkpoint_anchor_repository.py`（6 条） | ✅ |

**覆盖结论**：7 条 AC 全部 ≥ 1 条自动用例，无手工 UAT 项。**AC-7 在本轮之前是零覆盖**，是 5-test 抓到的主要缺口。

### 1.2 UAT 脚本

无。本 change 全部能力经 HTTP/运行时接口可自动化验证；「真实生产 checkpoint 重放」属 T07（7-integration 阶段），不在此处记 UAT。

### 1.3 覆盖率

```text
$ .venv/bin/pytest -q --basetemp=/tmp/fla-t5-full2 \
    --cov=app.modules.agent.runtime --cov=app.modules.admin
140 passed in 44.75s

Name                                         Stmts   Miss  Cover   Missing
app/modules/admin/checkpoint_repository.py     131     28    79%   48,51,59,64-65,73-75,81,97,111-113,130,156-158,178,208-210,215,272-279,303-307
app/modules/admin/service.py                    54      1    98%   92
app/modules/agent/runtime.py                   444     57    87%   63-65,88,102,...,896
TOTAL                                          786     86    89%
2 files skipped due to complete coverage (router.py / schemas.py = 100%)
```

- 当前：整体 89%，`runtime.py` 87%，`service.py` 98%
- 门槛：项目默认 80%，core 90%
- 不达项：
  - `runtime.py` 87% —— 未覆盖行主要是既有主链路的异常分支（63-208 的 SSE/取消路径）与 **`896` = `replay_anchor_ambiguous`**；后者需要并行边才能构造，见 1.6。
  - `checkpoint_repository.py` 79% —— 该文件主体是 WIP 基线的**巡检**功能（`list_threads`/`stats` 的异常降级分支），重放只用到 `get()`/`routing_target()`/`count_thread()`，三条都有覆盖。属既有代码的覆盖欠账，非本 change 引入。
- AC 覆盖优先于行覆盖：7/7 AC 全绿。

### 1.4 边界 / 错误路径用例（本次新增 4 条）

| 边界类型 | 用例 | 断言 |
|---|---|---|
| 超时（极大耗时） | `test_replay_returns_504_when_the_graph_exceeds_its_budget` | 预算压到 0.1s、respond 拖 0.5s → `replay_timeout` / 504；原 thread 历史长度不变；warning 日志含 `replay_thread=` |
| 并发/锁竞争 | `test_replay_does_not_wait_for_the_execution_lock` | 主线程持 `_execution_lock`，重放在 15s 内完成（实现若抢锁则阻塞失败） |
| 注入形状输入 | `test_replay_rejects_injection_shaped_checkpoint_id` | `' OR 1=1 --` / `x' UNION SELECT 1 --` / `%00` / 512 字符 → 全部 404，非 500，无 `Traceback` |
| 空/超长 | 同上（`%00`、512 字符） | 参数化查询兜住，不越界不崩 |

已有边界：入口 checkpoint（`values == {}`）→ T-FIX-01 已覆盖并修正误判 404。

### 1.5 测试质量自检（6 维测试衰退风险）

未安装 brooks-lint，走路径 B 内置清单。

**严重度统计**：

| 编号 | 测试衰退风险 | 命中文件数 | 严重度分布 |
|---|---|---|---|
| T1 | Test Obscurity 测试晦涩 | 0 | 🔴 0 / 🟡 0 / 🟢 0 |
| T2 | Test Brittleness 测试脆弱 | 1 | 🔴 0 / 🟡 0 / 🟢 1 |
| T3 | Test Duplication 测试重复 | 1 | 🔴 0 / 🟡 0 / 🟢 1 |
| T4 | Mock Abuse Mock 滥用 | 0 | 🔴 0 / 🟡 0 / 🟢 0 |
| T5 | Coverage Illusion 覆盖率幻觉 | 0 | 🔴 0 / 🟡 0 / 🟢 0 |
| T6 | Architecture Mismatch 架构错配 | 0 | 🔴 0 / 🟡 0 / 🟢 0 |

**详细发现**：

```markdown
### 🟢 T2 · Test Brittleness：锁测试依赖内部属性名
**Symptom**：tests/test_checkpoint_replay_resilience.py:118 `runtime._execution_lock`
**Source**：《Working Effectively with Legacy Code》· 接缝（seam）与感知点
**Consequence**：改锁的实现（换 asyncio 锁 / 改名）会让测试报 AttributeError 而非行为失败。
**Remedy**：这是**有意为之**——被测的正是「不取这把锁」这一结构契约，属可接受的内部感知点；
若将来并发模型改成 async 锁，本用例需同步改写（已在注释标注）。

### 🟢 T3 · Test Duplication：造 run 的样板有两份
**Symptom**：tests/test_checkpoint_replay_resilience.py:57 `chat_runtime` 与 test_checkpoint_replay_unit.py:158 `chat_setup`
**Source**：《xUnit Test Patterns》· 测试代码重复（Test Code Duplication）
**Consequence**：run 创建流程若变，两处都要改。
**Remedy**：新 fixture 额外返回 `checkpoint_id`、且用时间戳昵称避免与旧 fixture 的注册唯一性耦合；
后续可把 `chat_setup` 上提为共享 conftest fixture，本轮不改动已通过的测试。
```

**处理**：命中 2 项、均 🟢，记入 1.6 备查，不构成 release 阻断（阈值 ≥3 项必修）。

正向确认：
- T1 ✅ 用例名均为 Given/When/Then 式行为描述（`returns_504_when_...`、`does_not_wait_for_...`）
- T4 ✅ 无 `unittest.mock`；`FakeLLM` 只实现协议，用真实 sqlite checkpointer
- T5 ✅ 无空断言：断言 `AppError.code` + `status_code` + 行数/日志字段等实质结果
- T6 ✅ 超时/锁属运行时层用单测；HTTP 契约用集成测，层级匹配

### 1.6 测试质量记事（backlog）

| 项目 | 维度 | 严重度 | 计划 |
|---|---|---|---|
| 锁测试依赖 `_execution_lock` 名称 | T2 | 🟢 | 换并发模型时同步 |
| 造 run fixture 两份 | T3 | 🟢 | 下次动 conftest 时合并 |
| `replay_anchor_ambiguous` 无用例 | 覆盖缺口 | 🟡 | 图支持并行边时补（LESSONS L-004） |

---

## 第 2 轮 · 性能测试

### 2.1 性能预算（来自 REQUIREMENT.md 非功能性需求）

```yaml
replay:
  timeout_seconds: 60          # 单次重放上限，超时即返回
  affects_online_traffic: none # AC-7：不得让真实用户排队
  writes_business_tables: none # AC-3
```

REQUIREMENT 未定义 QPS / 延迟 SLO —— 该端点是管理端人工触发，无并发压力场景，故不设 p95 预算（R5.5：没有预算就不编造预算）。

### 2.2 实测结果

| 指标 | 预算 | 实测 | 判定 |
|---|---|---|---|
| 单次重放耗时（local sqlite + fake LLM） | < 60s | **8 ms**（T06 真实响应 `durationMs: 8`） | ✅ 达标（余量 7500×） |
| 超时守护生效 | 超预算即返回 | 预算 0.1s / 实际 0.5s → 504 | ✅ 达标（新用例实测） |
| 阻塞在线执行 | 0 | 持锁状态下重放仍完成 | ✅ 达标（新用例实测） |
| 拖慢主连接 | 0 | 独立 `CheckpointerManager` 连接，不碰 `self.checkpointer` | ✅ 结构性保证 |
| 单次重放 DB 往返 | 常数 | 2×`get_state` + 1×`update_state` + 1×`invoke` + 1×`get_state_history` = 5 次 | ✅ 无 N+1 |
| 单次新增 checkpoint 行 | 可见即可 | 2 行（T06 `checkpointRowsAdded: 2`） | ⚠️ 见 2.4 |

### 2.3 工具输出

```text
$ .venv/bin/pytest -q -k replay --durations=8
20 passed, 120 deselected in 9.20s

0.82s call  test_replay_returns_504_when_the_graph_exceeds_its_budget   ← 含 0.7s 等待被丢线程收尾
0.50s setup test_replay_rejects_injection_shaped_checkpoint_id          ← setup = 建一条真实 run
0.46s setup test_replay_returns_200_with_camel_case_contract
```

墙钟时间几乎全在 `setup`（造真实 run），replay 调用本身 < 100ms。

索引核查（langgraph MySQL saver 建表语句）：

```sql
PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
CREATE INDEX checkpoints_thread_id_idx ON checkpoints (thread_id);
```

→ `get_state` 走主键，`get_state_history` 走 `thread_id` 索引，无全表扫。

### 2.4 退步项处理

无退步项（本次无前端产物、无主链路改动）。

⚠️ 两个已知成本，均不阻断：
1. **checkpoint 膨胀**：每次重放固定新增 2 行，无 TTL 清理（v2 范围，REQUIREMENT 已列「replay thread 的 TTL 清理任务」）。响应里回传 `checkpointRowsAdded` 供观察。
2. **生产重放含真实 LLM 调用**（1~3s 量级），60s 预算充足；超时后后台线程无法 kill（Python 限制），日志留 `replay_thread=` 供人工清理。

---

## 第 3 轮 · 安全测试

### 3.1 依赖漏洞

```bash
$ uv run --no-sync --with pip-audit pip-audit -l --desc off
Found 1 known vulnerability in 1 package       ← 修复前
Name      Version ID              Fix Versions
dnspython 2.9.1   CVE-2026-128089 2.9.2
```

- 严重度：**CVSS 3.1 = 7.5 High**（CWE-400 资源耗尽；需解析攻击者可控的 WKS zone 文本）
- 本项目暴露面：dnspython 仅作 `email-validator` 的传递依赖（邮箱域名校验），**不解析 zone 文件**，理论不可达。
- 处理：**已升级**（`uv lock --upgrade-package dnspython` → 2.9.2，`uv.sync` 已完成）

```bash
$ uv run --no-sync --with pip-audit pip-audit -l --desc off
No known vulnerabilities found                 ← 修复后
```

- High / Critical：0
- 复跑全量：**140 passed**（升级未破坏邮箱校验相关用例）

> 部署影响：`backend/uv.lock` 变更，生产 release 需重新安装依赖（`uv sync` 或按 lock 装包）。

### 3.2 秘钥扫描

未装 trufflehog/gitleaks（且沙箱不便下载二进制），改用等价模式扫描 + 入库文件核查：

```bash
$ git ls-files | grep -E "\.env($|\.)"
.env.example  backend/.env.example  frontend/.env.example  frontend/.env.production

$ grep -rnE "(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|-----BEGIN (RSA |EC )?PRIVATE KEY|password\s*=\s*['\"][^'\"]{8,}['\"])" \
    --include=*.py --include=*.ts --include=*.tsx --include=*.js --include=*.yml --include=*.conf \
    backend/app frontend/src deploy | grep -v test
(无输出)
```

- 命中：0
- 真实 `.env` 未入库（仅 `.env.example`）；`frontend/.env.production` 只含 `VITE_BASE_PATH=/` 与 API 前缀，无密钥
- 已 rotate：N/A

> 工具缺口如实记录：本环境用「模式匹配」替代专用扫描器，覆盖面窄于 trufflehog 的熵检测。建议下次在 CI 里跑 gitleaks。

### 3.3 SAST

- 工具：**Bandit 1.9.4**（扫描 `app/`，7610 行）
- High：**0**
- Medium：**2**，均为 `B608 hardcoded_sql_expressions`，同一文件：
  - `app/modules/admin/checkpoint_repository.py:140`、`:145`
  - 判定：**误报**。`where` 只取两个常量之一（`"where thread_id = :thread_id"` 或 `""`），用户输入走绑定参数 `:thread_id`；`f-string` 插的是常量而非输入。已人工复核 SQL 文本。
- Low：0

### 3.4 OWASP Top 10

| 项 | 状态 | 备注 |
|---|---|---|
| A01 越权 | ✅ 已测 | `require_admin`；普通用户 403、匿名 401（`test_replay_requires_admin`）。管理员可重放任意 thread 属**设计内**能力（调试工具），无租户隔离需求 |
| A02 加密失败 | ❌ 不适用 | 无新增存储/传输面，复用既有 HTTPS + 会话 |
| A03 注入 | ✅ 已测 | SQL 全参数化；新增 `test_replay_rejects_injection_shaped_checkpoint_id`（4 种 payload 全 404）；bandit B608 已复核为误报 |
| A04 不安全设计 | ✅ 已评 | 只读设计、隔离 thread、不取执行锁、无业务写入，ADR-017~021 已记录取舍 |
| A05 配置错误 | 🟡 既有债 | `FLA_CORS_ORIGINS` 仍指向旧域名（STATE.md 已登记，非本 change 引入） |
| A06 漏洞组件 | ✅ 已修 | 见 3.1，dnspython 已升 2.9.2，复扫 0 |
| A07 鉴权 | ✅ 已测 | 端点级 `Depends(require_admin)`；401/403 均有用例 |
| A08 数据完整性 | ✅ 结构性 | 重放不写 `conversation_messages` / `agent_runs` / 业务表（AC-3 断言） |
| A09 日志监控 | ✅ 见第 5 轮 | 日志含四字段，不含回答正文 |
| A10 SSRF | ❌ 不适用 | 无用户可控 URL 拉取；LLM 调用目标来自配置 |

---

## 第 4 轮 · 兼容性测试

### 4.1 跨浏览器

**N/A**。本 change 无任何前端提交（`git log main --not 0383acd -- frontend/` 为空）。AdminPage 的重放按钮属 v2。

### 4.2 数据迁移

**N/A，已核实无迁移**：

```bash
$ git diff --name-only 6d06431..HEAD -- backend/alembic/ | wc -l
0
```

4-dev 步骤 1.7 未产出迁移文件是**正确**的：本 change 零 schema 变更（重放只读原表 + 写隔离 thread 的既有 checkpoint 表）。

### 4.3 跨版本 / 数据兼容

- [x] **旧 checkpoint 数据可读**：T01 用真实 sqlite（langgraph 1.2.19 写入的既有 schema）读取 `checkpoints` / `writes`，`routing_target` / `count_thread` 断言通过 → 老数据无需迁移即可被新代码消费。
- [x] **API 向前兼容**：`admin/router.py` 本 change **纯新增**（`git diff 0383acd..HEAD` 无删除行），既有 4 个 checkpoint 端点签名不变，`test_admin_checkpoints.py` 全绿。
- [x] **响应契约**：`CamelModel` 输出 camelCase；`tokenUsage` 内层保持 snake_case 与既有 `/agent/runs/{id}` 一致（T06 决策 1）。
- [ ] 编码 / locale：无用户可见文案变更，N/A。

---

## 第 5 轮 · 可观测性验证

### 5.1 日志

- [x] 关键路径入口/出口/异常均有 log：`INFO`（成功，含耗时）+ `WARNING`（超时，含 replay_thread），拒绝路径由全局异常处理器统一记
- [x] 含可反查字段（REQUIREMENT 非功能项逐项核对）：

```text
agent checkpoint replay source_thread=<tid> source_checkpoint=<cid>
  replay_thread=replay-<uuid> prompt_version=v1:<hash12> duration_ms=<int>
```

  由新用例 `test_replay_log_is_traceable_and_carries_no_response_text` 断言五个字段齐全。
- [x] **不含 PII / 秘钥 / token**：日志只打 id、版本号、耗时，不打用户输入与模型回答；用例显式断言 `result["replay"]["response"] not in message`
- [x] 错误日志上下文充分：超时日志带 source/replay 两侧 id 与 timeout 值，可直接定位孤儿线程

### 5.2 指标

- [x] 进程级 RED 已覆盖：`app/core/metrics.py` 统计 requestsTotal / errorsTotal / inFlight / statusClasses / latencyMax，新端点自动计入
- [ ] **per-endpoint 指标缺失**：没有 `replay_total` / `replay_duration_ms` 直方图，只能从「5xx 总数 + 慢请求最大值」间接看出问题
  → 判定 **⚠️ 部分达标**。REQUIREMENT 未要求 metric（只要求日志四字段），故不阻断；记为 v2 技术债（与「重放记录落库」一并做）
- [ ] USE 指标：无新增资源，复用既有连接池

### 5.3 链路追踪

- [ ] 跨服务 trace：本项目无分布式调用（单体 + 单 LLM 上游），N/A
- [x] 慢操作可定位：单次重放日志自带 `duration_ms`，超时单独 WARNING

### 5.4 告警 + 健康检查

- [x] `/health/live`（纯存活）与 `/health/ready`（执行 `SELECT 1` 探 DB）分离 —— `app/api/routes/health.py`
- [ ] 重放失败无专项告警：回到「人工触发的调试工具」定位，5xx 会被全局错误计数覆盖
- [ ] 无 runbook 链接：项目整体尚无告警体系，属全局欠账，非本 change 引入
- [x] 无噪音告警：本 change 未新增任何告警通道

---

## 新增测试登记

| 用例文件 | 类型 | 覆盖 AC | 所属轮次 |
|---|---|---|---|
| `tests/test_checkpoint_replay_resilience.py`（**本次新增，4 条**） | unit | AC-7 / A03 / 可观测 | 1 · 3 · 5 |
| `tests/test_checkpoint_replay_unit.py`（T03，8 条） | unit | AC-2 / AC-3 / AC-4 / AC-5 | 1 |
| `tests/test_checkpoint_replay_api.py`（T06，6 条） | integration | AC-1 / AC-2 / AC-4 / AC-6 | 1 |
| `tests/test_checkpoint_anchor_repository.py`（T01，6 条） | unit | 锚点解析基础 | 1 |
| `tests/test_agent_checkpoint_reconnect.py`（11-20，4 条） | unit | 连接自愈回归 | 1 |

回归用例总数：**140**（4-dev 完成时 136 → 本次 +4）。

## 回归保护

本次变更可能影响的旧功能：

| 旧功能 | 影响面 | 现有测试 | 结果 |
|---|---|---|---|
| Agent 主链路（classify/prepare/respond/wait） | `runtime.py` 新增方法，未改图与节点 | `test_agent_workflows.py` 等 | ✅ |
| checkpoint 连接自愈（11-20 修复） | `_with_checkpoint_retry` 被重放复用 | `test_agent_checkpoint_reconnect.py` | ✅ |
| Admin checkpoint 巡检 4 端点 | router 纯追加 | `test_admin_checkpoints.py` | ✅ |
| 邮箱校验（依赖升级波及） | dnspython 2.9.1→2.9.2 | 注册/登录用例 | ✅ |
| 前端 Admin 巡检页 | 本 change 未动前端 | 未跑 e2e（无改动） | — |

```text
$ .venv/bin/pytest -q --basetemp=/tmp/fla-t5-after-upgrade
140 passed in 36.93s
```

---

## 结论与遗留

**通过**。7/7 AC 有自动用例；安全 0 High（1 个 High 依赖已升级并复扫）；无 schema 变更、无回归。

必须回写的文档偏差（3 条，待批准）：

| # | 偏差 | 建议 |
|---|---|---|
| 1 | REQUIREMENT「超时即返回，**不写任何状态**」措辞过强 | 超时前 `update_state` 已写入隔离 replay thread（不碰原链、不写业务表）。建议改为「超时即返回，不对原 thread 与业务表写入任何状态」 |
| 2 | DESIGN §2.3 锚点公式 off-by-one | 已在 T02 实测推翻，代码按修正实现；DESIGN 未回写 |
| 3 | DESIGN §9.1 与实现不一致 | 同批回写 |

遗留（不阻断，v2 处理）：

- `replay_anchor_ambiguous` 无测试（线性图构造不出）
- 无 replay 的 per-endpoint metric
- replay thread 无 TTL 清理

下一步：`@flow-kit/prompts/6-review.md`；T07（生产真实 checkpoint 重放取证）留待 7-integration 部署后执行。
