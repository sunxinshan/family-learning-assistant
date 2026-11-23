# REVIEW: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **审查时间**: 2026-11-23 15:40
- **审查者**: AI（Reviewer 角色，内置 6 维回退路径）+ 独立上下文复审（近似 spot-check，非跨模型，见 §4.2）
- **审查基线**: `0383acd..HEAD@35d3187`（T01–T06 + T-FIX-01，8 个提交）
- **总体结论**: **阻塞**（2 项 Critical，其中 C-1 直接违反 AC-3）

---

## 审查范围声明

| 项 | 内容 |
|---|---|
| 纳入 | `backend/app/modules/agent/runtime.py`（+168）、`admin/{service,schemas,router,checkpoint_repository}.py`、4 个新测试文件、`uv.lock`（dnspython 2.9.2） |
| 排除 | `b26135d`（服务器交接文档）、`c0addd8`（`scripts/watch_llm_trace.py` + `.gitignore`）——同处 diff 区间但**不属本 change**；`backend/log.sh`、`infrastructure/observability/` 未跟踪 |
| 前端 | 无（`git diff 0383acd..HEAD -- frontend/` 为空）→ 第三轮 UI 审查跳过 |
| 工具 | 未装 brooks-lint → 走路径 B 内置诊断；UI 反模式清单不需要 |

---

## 第一轮 · Spec 合规审查

| 检查项 | 结果 | 证据 |
|---|---|---|
| AC-1 能重放并对照 | ✅ | `admin/router.py:113-129`、`admin/service.py:141-163`、`agent/runtime.py:995-1010`；`test_checkpoint_replay_api.py:137` |
| AC-2 原 thread 零污染 | ✅ | `runtime.py:901-917`（新 thread `replay-<uuid>`）；`test_checkpoint_replay_unit.py:156`、`..._api.py:230` |
| **AC-3 不产生业务副作用** | ❌ | **见 C-1**：`vocabulary_import` 路由重放会写 `content_extractions` 并改 `material.status`；现有用例只覆盖 chat 路由 |
| AC-4 目标不可重放时拒绝 | ✅ | `runtime.py:875-899`；三条拒绝路径 + 入口 409 均有断言（`test_checkpoint_replay_unit.py:233/246/261/287`） |
| AC-5 可重复 | ✅ | `test_checkpoint_replay_unit.py:192`（两次 thread_id 不同、首次重放 thread 不受影响） |
| **AC-6 权限与降级** | ❌ | 权限部分 ✅（`..._api.py:199`，403/401）；**降级部分只测了 sqlite 缺文件**。MySQL 后端下表名方言让预检恒 404，驱动写法则另有一半需服务器核实 —— 见 C-2 |
| AC-7 不拖垮在线服务 | ⚠️ | 逻辑满足（`runtime.py:916-941`，504 + 不取 `_execution_lock`），但超时后连接泄漏 —— 见 M-1 |
| 未引入 out of scope | ✅ | 无前端、无 `replay_runs` 表、无注入式调试、无普通用户入口 |
| 未范围蔓延 | ⚠️ | 无 REQUIREMENT 外**功能**；但 `routing_target`/`count_thread` 在被 T04 修正推翻后仍然合入且零调用方 —— 见 M-4 |
| 未越过 DESIGN 边界 | ❌ | DESIGN §2.3 锚点公式与实现不一致（已知偏差 2）；**§2.4「图内四节点只读」遗漏 `wait` 节点，且 `prepare_vocabulary_import` 实际写库** —— C-1 的根因就在这份断言上 |

**Spec 合规结论**: 不通过。AC-3 与 AC-6 未满足，需修复后重审。

---

## 第二轮 · 代码质量审查（6 维衰退风险）

### 2.0 TEST.md 5 轮金字塔完整性

| 轮次 | 状态 | 缺漏 |
|---|---|---|
| 1 功能 | ❌ | AC-3 名义有用例、**实质空转**：`test_replay_writes_no_business_rows` 只跑 chat 路由，而写库发生在 `prepare_vocabulary_import`。AC-6 降级只测 sqlite 缺文件，未测 MySQL（C-2 因此漏网）→ 需回 5-test 补两条 |
| 2 性能 | ⚠️ 部分 | 预算/实测齐全（`TEST.md:146-155`）；但「超时后进程状态」未测（孤儿线程+连接），补 `TEST.md` 一节 |
| 3 安全 | ✅ | 依赖/秘钥/SAST/OWASP 记录完整，A03 有注入用例 |
| 4 兼容 | ⚠️ 部分 | 无 schema 变更、API 纯新增，理由成立；但**「旧 checkpoint 可读」只在 sqlite 验证**，MySQL 表名不匹配恰好落在这里 |
| 5 可观测 | ✅ | 四字段日志有断言、明确记录 metric 缺口 |

### 2.1 6 维诊断 · 严重度统计

| 编号 | 衰退风险 | 🔴 | 🟡 | 🟢 |
|---|---|---|---|---|
| R1 | Cognitive Overload 认知过载 | 0 | 0 | 1 |
| R2 | Change Propagation 变更传播 | 1 | 0 | 0 |
| R3 | Knowledge Duplication 知识重复 | 0 | 1 | 0 |
| R4 | Accidental Complexity 偶然复杂 | 0 | 0 | 1 |
| R5 | Dependency Disorder 依赖混乱 | 0 | 0 | 1 |
| R6 | Domain Model Distortion 领域扭曲 | 1 | 1 | 0 |

> 死代码项（M-4）落在 R2/R4 边界，按 6-review.md R3 边界说明，**字面级冗余归 M-health**；但本项是本 change 新增且无调用方，属"被推翻方案的残留"，仍列入。

### 2.2 6 维诊断 · 详细发现

```markdown
### 🔴 C-1 · R2 变更传播 / R6 领域扭曲：重放 vocabulary_import 会真实写业务表，AC-3 不成立
**Symptom**：`agent/runtime.py:901`（anchor = prepare）→ `agent/service.py:500`（`content.extract`）→
`content/service.py:61-62`（`material.status = "parsed"` + `repository.add(extraction)`）→
`core/database.py:60-63`（`session()` 退出即 commit）。
**Source**：Fowler · Refactoring · Divergent Change / Evans · DDD · 副作用应留在应用层而非领域执行链
**Consequence**：管理员对一条"上传文件导入词库"会话重放一次，就会新增一条 `content_extractions`、
把 `materials.status` 改成 `parsed`，同类重放可无限堆行 —— 直接违反 AC-3（"不得新增/修改 …
task / vocabulary / practice 等业务表任何行"），而 AC-3 被 REQUIREMENT 定为"结构性保证，不依赖运行时开关"。
`DESIGN §2.4` 的"图内四节点只读"只盘点了 classify/prepare/tool_create/respond，**漏了 prepare 的
vocabulary_import 分支真会落库**，于是整个无副作用论证建立在一个不成立的清单上。
**Remedy**：三选一（需用户拍板）：① 重放前置拒绝 `route in {"vocabulary_import"}` → 409
`replay_unsupported_route`（最小、最安全，与"歧义即拒绝"同一哲学）；② 把 `ContentService.extract`
的副作用抽成"渲染草稿（纯函数）+ 落库（显式调用）"两步，重放只走前者（根治但要动 content 模块）；
③ 显式接受并写进 REQUIREMENT（不推荐，等于放弃 AC-3）。
**生成 fix 任务**：T-FIX-02

### 🔴 C-2 · R2 变更传播：MySQL 后端下重放的存在性预检必然失败（500 或恒 404）
**Symptom**：`admin/service.py:155` → `admin/checkpoint_repository.py:34-36`（`create_engine(url)` 直用
`settings.checkpoint_url`）与 `:196-205`（`select task_id, idx, channel, type, value from writes`）。
**Source**：Brooks · The Mythical Man-Month · 概念完整性（同一个 checkpoint 库被两套方言访问）
**Consequence**：两个**互相独立**的缺陷叠加：
① **表名/列名方言（确定命中）**：`langgraph-checkpoint-mysql` 建的是 `checkpoint_writes`，写序列化值用
`blob` 列（`mysql/base.py:48,232`）；sqlite saver 才是 `writes(value)`。而仓库里三处查询
（`get():199`、`routing_target():265`）全部写死 sqlite 方言 → MySQL 后端下抛 `SQLAlchemyError` →
`:210` 吞成 `None` → **每个真实存在的 checkpoint 都报 404 `checkpoint_not_found`**。
§4.2 兼容性"旧 checkpoint 可读"只在 sqlite 验过，这条必然漏网。
② **驱动（条件命中，待服务器确认）**：`checkpoint_url` 若写成 `mysql://…`（仓库内 `docker-compose.yml:36`、
`docs/部署说明.md:50` 都是这个写法），`create_engine` 会去加载 MySQLdb → `ModuleNotFoundError`，
它不是 `SQLAlchemyError`，`except` 吞不住 → 500。**注意**：生产不是 Docker 部署（systemd +
`deploy/project2-start.sh` + uvicorn 127.0.0.1:8002 + nginx），实际值在服务器的
`/opt/project2/shared/env/familylearning.env`，**本轮无法读取**，需一条命令核实（见 Remedy ④）。
**Remedy**：① `get()` / `routing_target()` 按 backend 选表名与值列（抽出 `_writes_table()` /
`_value_column()`，禁止再硬编码）；② `_url()` 对 mysql 统一改写 `mysql+pymysql://`，并把 `except` 扩到
`Exception` → 503 `checkpoint_store_unavailable`（DESIGN §3 已承诺此码，代码里 grep 不到）；
③ 「库不可用」与「不存在」必须用不同错误码，不能再合用一个 404；④ 上线前在服务器核实：
`grep -E 'FLA_CHECKPOINT' /opt/project2/shared/env/familylearning.env` 与
`show tables like '%writes%'`（应为 `checkpoint_writes`，若真是 `writes` 说明该库跑过 sqlite schema）。
**生成 fix 任务**：T-FIX-03

### 🟡 M-1 · R1 认知过载 / 资源约束：超时后孤儿线程会把已关闭的连接"复活"并继续写，异常被 Future 静默吞掉
**Symptom**：`agent/runtime.py:916-941`（`shutdown(wait=False)`）与 `:861`（`with CheckpointerManager`）、
`infrastructure/checkpoint.py:39-42`（`__exit__` 关连接）、`runtime.py:83-89`（`_revive_checkpoint_connection` 调 `ping(reconnect=True)`）。
**Source**：Ousterhout · Philosophy of Software Design · 异常路径的设计也要闭合（failure path 比 happy path 更能定义复杂度）
**Consequence**：504 返回后请求线程立即退出 `with`，把 saver 的 pymysql 连接 `close()`；孤儿线程下一次
checkpoint 写抛 `InterfaceError` → `_with_checkpoint_retry` 调 `ping(reconnect=True)`，pymysql 在
`_sock is None` 时会真的重连，于是**连接被复活、无人再关**（每次超时泄漏 1 条，打到 `max_connections`
上限就伤到在线服务——正是 AC-7 要防的）。sqlite 分支更直接：`ProgrammingError: Cannot operate on a
closed database` 不在 `_CHECKPOINT_RETRY_ERRORS` 里，图半途终止。两种情况异常都挂在被丢弃的 Future 上，
日志里只有那行 timeout warning，看不出"重放其实还在写"。
**Remedy**：超时分支不要立刻关连接——① 用 `threading.Event`/标志位让 worker 在下一个 checkpoint 前主动退出，
等 `executor.shutdown(wait=True, timeout≈2s)` 再关；或 ② 超时后**不**关 saver，把它连同 `replay_thread`
交给一个显式清理队列（进程级，v2 的 TTL 任务顺带做）；③ 无论如何给孤儿线程挂
`future.add_done_callback` 把异常打进日志（`logger.exception`），别再让它静默。
**生成 fix 任务**：T-FIX-04

### 🟡 M-2 · R3 知识重复：同一条"checkpoint 不存在"规则被表达在三处，且 DESIGN 承诺的 503 无实现
**Symptom**：`admin/service.py:127`、`admin/service.py:155`、`agent/runtime.py:875`（同一 code、同一文案、同一 404）。
**Source**：Hunt & Thomas · The Pragmatic Programmer · DRY（"同一个知识只能有一个权威表述"）
**Consequence**：三处改一处忘两处的典型起点；更实际的是——`service` 的预检与 `runtime` 的检查各自
对"库不可用"和"不存在"给出**同一个** 404，把"库挂了"误报成"数据丢了"（C-2 的第二形态）。
**Remedy**：保留 `runtime` 一处权威判定（它必定要开连接），`service` 的预检降级为"仅当库可用才预检，
不可用直接 503"；三处文案抽一个工厂函数。
**生成 fix 任务**：并入 T-FIX-03

### 🟡 M-3 · R6 领域扭曲：重放到"确认前"的锚点会静默停在 interrupt，200 响应里没有任何"没跑完"的标识
**Symptom**：`agent/runtime.py:943-951`（`out = get_state(...)`，未检查 `out.next` / `__interrupt__`）；
路由见 `:236-249`（`tool_calling` 关闭时 task_create 走 classify→prepare→wait）。
**Source**：Evans · DDD · 领域语言必须忠实（"replay"意味着一次完整执行）
**Consequence**：默认配置（`FLA_AGENT_TOOL_CALLING_ENABLED=false`）下，重放 `next=('wait',)` 的快照会
再次 `interrupt` 并正常返回 200：`replay.response` 为 null、`diff.responseChanged=true`，
管理员看到的是"重放没生成回答 / 回答变了"，实际是"跑到确认环节就停了"。这类误读会直接浪费一次排障。
**Remedy**：结果里加 `replay.interrupted: bool`（取自 `out.next` 非空或 `out.get("__interrupt__")`），
并在 200 响应中明示"停在 wait，未执行确认"；或按 C-1 remedy ① 的做法一并拒绝。
**生成 fix 任务**：T-FIX-05

### 🟡 M-4 · R2 变更传播 / R4 偶然复杂：`routing_target` + `count_thread` 零调用方（279 行新增代码无事可做）
**Symptom**：`admin/checkpoint_repository.py:239-308`（71 行）+ `tests/test_checkpoint_anchor_repository.py`（208 行）；
`grep -rn "routing_target|count_thread" app/` 除定义与 docstring 外**无任何调用点**。
**Source**：Fowler · Refactoring · Speculative Generality（"为将来可能的需求保留的代码，通常永远等不到那天"）
**Consequence**：TASK「修正 2」已明确它"不进入重放链路，保留作管理页诊断"，而管理页属 v2 且未排期；
这段代码连同 208 行测试要一直跟着 `writes` 表结构走。C-2 的第二形态（MySQL 表名）正好也在这段里——
没有调用方的代码没人会发现它跑不通。
**Remedy**：二选一并写进 STATUS：① 随本 change 删除（v2 做管理页时按需重写）；② 保留但标
`# v2: 尚无调用方`，并在 T-FIX-03 里一并修 MySQL 分支。倾向 ①。
**生成 fix 任务**：T-FIX-06

### 🟢 m-1 · R4 偶然复杂：`checkpoint_rows_added` 全量物化历史只为计数
**Symptom**：`agent/runtime.py:953-955`（`len(list(graph.get_state_history(...)))`）。
**Source**：Ousterhout · Philosophy of Software Design · 性能与抽象泄漏
**Consequence**：长 thread 上把每条快照都反序列化一遍（BLOB 可能很大），只为拿一个数字；
且该值语义是"重放 thread 的行数总和"而非"本次新增"，命名与实现略有偏差。
**Remedy**：改 `sum(1 for _ in ...)`；或直接 `count_thread(new_tid)`（需解决 agent→admin 依赖）。
**生成 fix 任务**：可并入 T-FIX-04 顺手改

### 🟢 m-2 · R1 认知过载：`replay_from_checkpoint` 161 行，且唯一一处不做连接重试的快照读取
**Symptom**：`agent/runtime.py:847-1008`；其中 `:953` 的 `get_state_history` 未包 `_with_checkpoint_retry`，
其余 5 处 checkpointer 调用都包了。
**Source**：McConnell · Code Complete · 例程长度与一致性
**Consequence**：一处提前返回的 InterfaceError 会把已经跑成功的重放兜成 500；函数过长也让它难以单测分支。
**Remedy**：抽 `_resolve_replay_anchor(saver, graph, src)` / `_run_replay(...)` 两段；`get_state_history` 补重试包装。
**生成 fix 任务**：可并入 T-FIX-04

### 🟢 m-3 · R6 领域扭曲（审计）：失败的重放不留管理端操作日志
**Symptom**：`admin/service.py:158`（`self.log(...)` 只在 `runtime` 成功返回后调用）。
**Source**：Evans · DDD · 审计与领域事件
**Consequence**：一次被拒绝或超时的重放（也可能是"有人在试探数据"）在 admin 操作日志里不留痕。
**Remedy**：`try/finally` 里记一条带结果码的日志。
**生成 fix 任务**：不单独立任务，T-FIX-03 一并处理。
```

### 2.3 架构依赖图（触发条件未命中 · 简化图）

触发判定：无新增顶级模块、无低层 import 合并、无新中间件、跨模块 < 5 —— 不满足 2.2 触发条件，故只画新增数据流（用内置简化图替代 `/brooks-audit`）。

```mermaid
graph LR
  R[admin/router.py<br/>require_admin] --> S[admin/service.py<br/>replay_checkpoint]
  S --> REPO[admin/checkpoint_repository.py<br/>get / _engine_for]
  S -.运行期注入 app.state.agent_runtime.-> AR[agent/runtime.py<br/>replay_from_checkpoint]
  AR --> CM[infrastructure/checkpoint.py<br/>CheckpointerManager 独立连接]
  AR --> G[build_agent_graph<br/>classify/prepare/tool_create/respond/wait]
  G -.写库副作用.-> BIZ[agent/service.py<br/>prepare_vocabulary_import]
  REPO -.直连同库.-> DB[(checkpoints 库)]
  CM -.独立连接.-> DB
  BIZ -.业务库.-> BDB[(业务库)]
```

**循环依赖**：无运行期 import 环（`service.py:28-31` 用 `TYPE_CHECKING` 把 `AgentRuntime` 挡在类型检查期）。
**反向依赖**：**有（数据流层）**——`admin`（编排）把 `agent` 运行时当参数驱动执行；运行期无 import 边，
但语义上是"管理端反过来调执行层"，与 `ARCHITECTURE §3.3` 的边界有张力。属 DESIGN §2.2 明确选择（避免改
`AdminService` 构造函数），本次不判缺陷，登记为 🟢 R5 观察项。
**跨边界依赖**：无（前端未参与）。

---

## 第三轮 · UI 视觉审查

**未触发**：本 change 无 `UI-DESIGN.md`，`git diff 0383acd..HEAD -- frontend/` 为空，无 `.css/.tsx/.vue/.html` 改动。
AdminPage 的重放按钮与差异视图明确在 v2（REQUIREMENT「范围切分」）。因此 3.1–3.4 全部 N/A。

---

## 第四轮 · 补充审查（按触发条件）

### 4.1 技术债评估

**未触发**：本 change 不是里程碑/季度大版本/重构项目；且未装 brooks-lint，内置不提供回退（6-review.md 4.1）。

### 4.2 跨模型 spot-check

**触发条件命中两项**：涉及并发/连接（ADR-020）、单一函数 > 80 行（`replay_from_checkpoint` 161 行）。
本环境无第二个模型可用，改为**独立上下文的复审代理**（同族模型、零上下文重读源码），只能算近似。

| 主审发现 | 独立复审发现 | 是否一致 | 处理 |
|---|---|---|---|
| 超时后孤儿线程关连接问题（预判为 🟡） | 同项，并给出 pymysql `ping(reconnect=True)` 会真重连的机制链条 | 一致 | 采纳，定为 M-1 |
| — | **C-1**：`vocabulary_import` 重放写 `content_extractions` + 改 `material.status` | 仅复审提出 | **主审已独立核实**（`agent/service.py:500` → `content/service.py:61-62` → `database.py:60` commit）→ 采纳为 🔴 |
| — | **C-2**：生产 `mysql://` URL 缺驱动 → 500；修驱动后表名不匹配 → 恒 404 | 仅复审提出 | **主审已独立核实**（`create_engine('mysql://…')` 实测 `ModuleNotFoundError`；sqlite saver 用 `writes`、MySQL saver 用 `checkpoint_writes`）→ 采纳为 🔴 |
| — | 锚点在"节点改名/删除"的旧数据上会 500（LangGraph `InvalidUpdateError`） | 仅复审提出 | 评估后**降为 🟢 不立任务**：属跨版本调试的已知代价，且 100% 拒绝而非错误执行；记入 LESSONS |
| — | 并发共享对象无缺陷（`AgentBusinessService` 每次自建 session、Registry 只读） | 补充确认 | 采纳，关闭该项疑虑 |

分歧价值：两条 Critical **均为复审单独提出**、主审初读未命中，说明主审对"只读"与"CamelModel 契约"两处
有确认偏误。沉淀为 `.specs/LESSONS.md` L-006（「图节点只读」须按路由核对）与 L-007（只在 sqlite 验过等于没验）。

---

## 总结

- **Critical 项：2**，均已生成 fix 任务（T-FIX-02 / T-FIX-03）
- **Major 项：4**（M-1~M-4），M-1/M-2/M-3 生成任务（T-FIX-04/并入 03/T-FIX-05），M-4 生成（T-FIX-06）
- **Minor 项：3**（m-1~m-3），并入 T-FIX-03/04，不阻断
- 已知接受的文档偏差从 3 条增至 **4 条**（新增：DESIGN §2.4 节点只读清单遗漏 `wait` 与
  `prepare_vocabulary_import` 的写库副作用），随 7-integration 一并回写
- 通过项：AC-1 / AC-2 / AC-4 / AC-5 / AC-7 实现与用例扎实；140 用例本地复跑全绿（35.35s）验证 TEST.md 结论属实

**下一步**：回 `4-dev` 执行 T-FIX-02 ~ T-FIX-06（T-FIX-02 需先由用户在三种 remedy 中拍板），
修完全量回归后重跑 `6-review` 的 C-1/C-2/M-1 三项复核，通过后再进 `7-integration`（T07 生产取证）。

---

## 修复复核（2026-11-23 · 用户拍板后）

用户决策（原话）：**「重放前用 409 拒绝 vocabulary_import 路由，留并标 `# v2: 尚无调用方`，同时必须一并修复 MySQL 方言」**。
按此执行 T-FIX-02 ~ T-FIX-06，逐项复核：

| 编号 | 复核要点 | 结论 | 证据 |
|---|---|---|---|
| **C-1** | 重放 `vocabulary_import` 还会写业务表吗？ | ✅ 已关闭 | 锚点解析后、`update_state` 前按 state 的 route 抛 409 `replay_unsupported_route`；父快照 route 兜底覆盖入口形态。用例断言 409 + 前后 `content_extractions` / `materials.status` 指纹完全一致 |
| **C-2** | MySQL 下预检还会 500/恒 404 吗？ | ✅ 已关闭 | `_url()` 强制 `mysql+pymysql`（`render_as_string(hide_password=False)` 保留密码）；`get()` / `routing_target()` 共用 `_writes_table()` = `checkpoint_writes`，值列 `` `blob` as value ``；`except Exception` → 503 `checkpoint_store_unavailable`。9 条方言/降级用例覆盖 |
| **M-1** | 超时后连接还会被「复活」且泄漏吗？ | ✅ 已关闭 | 取消标志让孤儿线程不再 `ping(reconnect=True)`（单测断言 ping 只有前置探活那一次、invoke 不重试）；连接由最后完成者关闭（超时后 `_closed is False` → 线程结束后自动 `True`）；孤儿结局进日志（`done_callback` 记 finished/exception） |
| **M-2** | 「不存在」与「库不可用」还混用 404 吗？ | ✅ 已关闭 | 三处 404 文案收敛到 `checkpoint_not_found_error()`；库不可用统一 503；`checkpoint_store_unavailable` 从"DESIGN 承诺但查不到"变为真实实现 |
| **M-3** | 停在 wait 的 200 还能看不出「没跑完」吗？ | ✅ 已关闭 | `replay.interrupted`（camelCase 已在契约测试断言）；chat 路线断言 `false`，task_create 停在 wait 断言 `true` |
| **M-4** | 零调用方死代码留还是删？ | ✅ 按用户决策保留 | 方法上标 `# v2: 尚无调用方`，且方言与 `get()` 统一（不再只修一半）；mysql 用例断言查的是 `checkpoint_writes` |
| m-1 | `checkpoint_rows_added` 是否仍全量无重试 | ✅ 已修 | 改为 `sum(1 for _ in _with_checkpoint_retry(saver, lambda: list(get_state_history(...))))` |
| m-3 | 失败的重放是否留痕 | ✅ 已修 | 成功/失败各一条 admin 操作日志（失败带 `result="failure"` + 结果码），失败日志显式 commit 以抵消 `get_session` 回滚；API 用例换新请求复查落库 |

**回归**：全量 **156 passed**（新增 16 条），`ruff check` / `ruff format` 干净。
**仍待人工**：T07 生产取证（部署后执行），以及 **C-2 的 500 分支需要在服务器核实 env 字面值**：

```bash
grep -E 'FLA_CHECKPOINT' /opt/project2/shared/env/familylearning.env
```

若为 `mysql://`，修复后已在代码内改写，无需改配置；若为 `mysql+pymysql://`，则此前只会命中表名那一半（恒 404），
也已被修复。两种形态都收敛到「重放可用」。
