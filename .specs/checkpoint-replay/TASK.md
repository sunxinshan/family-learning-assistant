# TASK: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **关联**: `@.specs/checkpoint-replay/REQUIREMENT.md`、`@.specs/checkpoint-replay/DESIGN.md`
- **生成日期**: 2026-11-21
- **技术栈**: 后端 Python 3.12 / FastAPI / LangGraph 1.2 / SQLAlchemy，无新增依赖（DESIGN §0）

---

## Wave 0 · 前置（阻塞，须用户拍板）

**本 change 建在未提交的 WIP 之上。** `git status` 实测：

| 文件 | 状态 | 本 change 是否要改 |
|---|---|---|
| `backend/app/modules/admin/checkpoint_repository.py` | 未跟踪（WIP 新文件） | ✅ T01 |
| `backend/app/modules/admin/service.py` | 已修改未提交 | ✅ T04 |
| `backend/app/modules/admin/schemas.py` | 已修改未提交 | ✅ T04 |
| `backend/app/modules/admin/router.py` | 已修改未提交 | ✅ T05 |
| `backend/app/modules/agent/redaction.py` | 已修改未提交 | ❌ 只读依赖 |
| `backend/tests/test_admin_checkpoints.py` | 未跟踪 | ❌ 只读参考 |
| 前端 4 文件 + `observability/` 等 | 未跟踪/已修改 | ❌ 不碰 |

`service.py` / `schemas.py` / `router.py` 三个文件里**同时存在** WIP 改动与本 change 改动，无法按文件切分提交，只能按 hunk 挑 —— 易出错。

**建议**：先把 checkpoint 巡检 WIP 单独提交为基线（`feat: add read-only checkpoint inspection for the admin console`），本 change 的 6 个任务再独立成 commit。这样 `git revert` 能单独回滚重放功能。**需用户确认后由 4-dev 执行，不在本文件自动做。**

---

## 波次划分

```
Wave 0 (前置):  W00  提交 checkpoint 巡检 WIP 为基线（需用户确认，非本 change 代码）
Wave 1 (parallel): T01[P], T02[P]
Wave 2 (parallel): T03[P], T04[P]        (T03←T02；T04←T01,T02)
Wave 3:            T05                    (←T04)
Wave 4:            T06                    (←T05)
Wave 5:            T07                    (←T06，部署后执行，属 7-integration)
```

> 同 wave = 可并行；跨 wave = 必须顺序执行。
> **Wave 1 的两个任务是本 change 的全部"重活"**，T03/T04/T05/T06 都只是在它们之上接线与断言。

---

## 任务清单

```xml
<task id="T01" parallel="true" status="done" completed_at="2026-11-21 17:26">
  <name>CheckpointRepository 增加锚点解析与 thread 计数</name>
  <read_files>
    backend/app/modules/admin/checkpoint_repository.py
    backend/app/modules/admin/models.py
    backend/app/core/exceptions.py
    backend/app/modules/agent/redaction.py
    backend/tests/test_admin_checkpoints.py
  </read_files>
  <write_files>
    backend/app/modules/admin/checkpoint_repository.py
    backend/tests/test_checkpoint_anchor_repository.py
  </write_files>
  <action>
    在既有 CheckpointRepository 上加两个方法，沿用它的 `_url()` + `_engine_for()` 连接方式，不新建连接池、不新建类：

    1) `routing_target(thread_id, checkpoint_id) -> str | None`
       查 `writes` 表：`select channel from writes where thread_id=:t and checkpoint_id=:c and channel like 'branch:to:%'`。
       命中恰好 1 条 → 返回 `channel.split('branch:to:', 1)[1]`；
       命中 0 条或多条 → 返回 None，并在多条时 logger.warning 记录候选列表（ADR-019：歧义即拒绝，不猜）。
       `_url()` 为 None 或查询异常 → 返回 None（与既有 query 方法的降级风格一致）。

    2) `count_thread(thread_id) -> int`
       `select count(*) from checkpoints where thread_id=:t`，用于回填响应里的 `checkpoint_rows_added`。
       异常时返回 0，不抛。

    注意：`routing_target` 的入参是**目标 checkpoint**，但 SQL 查的是它 **parent** 的 writes —— 由调用方传 parent_id（T04 负责传），本方法只按传入 id 查，保持单一职责，不在方法内做二次查询。

    新增测试文件用真 SqliteSaver 跑一个 a→b 小图产生 writes，断言：
    - `routing_target(thread, mid.parent_id) == "b"`（证明它是「下一跳」）
    - `routing_target(thread, grandparent_id) == "a"`（证明「产出节点」需上溯一层）
    - 并行/无 branch 的情况返回 None；`count_thread` 计数与实际行数一致
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t01 tests/test_checkpoint_anchor_repository.py
  </verify>
  <done>
    routing_target 在"唯一命中"时返回节点名、在 0 条/多条时返回 None；count_thread 返回真实行数；4 条以上断言全绿（AC-4 的锚点部分）
  </done>
  <depends_on></depends_on>
</task>

<task id="T02" parallel="true" status="done" completed_at="2026-11-21 17:22">
  <name>AgentRuntime.replay_from_checkpoint 核心实现</name>
  <read_files>
    backend/app/modules/agent/runtime.py
    backend/app/infrastructure/checkpoint.py
    backend/app/modules/agent/service.py
    backend/app/modules/agent/models.py
    backend/app/modules/agent/prompt_registry.py
    backend/app/core/exceptions.py
    backend/app/core/config.py
    backend/app/core/database.py
  </read_files>
  <write_files>
    backend/app/modules/agent/runtime.py
  </write_files>
  <action>
    ⚠️ 本任务的签名与锚点取法已被实测修正（2026-11-21），**以文末「修正 1」为准**：
    实际签名为 `replay_from_checkpoint(thread_id, checkpoint_id)`，锚点在方法内部解析。

    在 AgentRuntime 上新增一个方法，签名：
    `replay_from_checkpoint(self, thread_id: str, checkpoint_id: str) -> dict[str, Any]`

    实现要点（严格按 DESIGN §2.2 / §2.5）：
    - **独立连接**：`with CheckpointerManager(self.settings) as saver:` 自开一条，用
      `build_agent_graph(saver, self.llm, self.business, self.guidance, self.tool_workflow)` 重建图。
      **不共用 self.checkpointer，不获取 self._execution_lock**（ADR-020，理由写进注释）。
    - 目标快照：`_with_checkpoint_retry(saver, graph.get_state, {thread_id, checkpoint_id})`。
    - 拒绝路径（全部抛 AppError，带语义化 code）：
      `not src.values` → `checkpoint_not_found` 404；
      存在待解决 interrupt（`any(task.interrupts for task in src.tasks)`）→ `checkpoint_interrupted` 409；
      `not src.next` → `checkpoint_terminal` 409。
    - 隔离 thread：`new_tid = f"replay-{uuid.uuid4()}"`（ADR-017）。
    - 续跑：`update_state({thread_id: new_tid}, src.values, as_node=anchor)` 后 `invoke(None, ...)`。
      **必须带 as_node**，否则 next 会重算为入口节点、把已完成节点再跑一遍（DESIGN §2.1 实测）。
    - 超时 60s：用 `concurrent.futures.ThreadPoolExecutor(1)` + `future.result(timeout=60)`，
      超时抛 `replay_timeout` 504，并在日志里留下 replay_thread 供清理（ADR/风险表已登记线程无法 kill）。
    - token_usage 只算**本次**：invoke 前记 `base = dict(src.values.get("token_usage") or {})`，
      invoke 后 `usage = out.get("token_usage")`，逐键相减，负数置 0；无新增则返回 None。
      （理由：update_state 会继承原 usage，直接回传会让人以为重放又花了那么多 token。）
    - prompt_version：`self.prompt.version + ":" + self.prompt.content_hash[:12]`（与 run 落库处一致）。
    - source.prompt_version：由 `src.values["run_id"]` 查 `agent_runs`（`self.database.session()` + ORM 取单行），
      查不到返回 None。只读，不写任何表。
    - checkpoint_rows_added：跑完用 `count_thread(new_tid)` 取——但那是 admin 的 repository。
      **本文件不 import admin**（避免 agent→admin 反向依赖）：改为在本方法内用 saver 已有连接
      或 `graph.get_state_history` 计数（`len(list(graph.get_state_history({thread_id:new_tid})))`）。
      取 history 长度即可，不查库。
    - 返回 dict（字段名与 DESIGN §3 一致）：
      `{"source": {...}, "replay": {...}, "diff": {...}}`，diff 只做 route/response/pending_action 三项等值比较。
    - 日志（REQUIREMENT 非功能项）：`logger.info` 带
      source_thread / source_checkpoint / replay_thread / prompt_version / duration_ms。

    不改图结构、不改节点、不改 AgentState、不改 start_run/confirm 任何既有路径。
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/ruff check app/modules/agent/runtime.py &amp;&amp; .venv/bin/python -c "from app.modules.agent.runtime import AgentRuntime; assert hasattr(AgentRuntime, 'replay_from_checkpoint')" &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t02 tests/test_agent_checkpoint_reconnect.py tests/test_agent_workflows.py
  </verify>
  <done>
    方法存在且可导入；ruff 通过；既有 Agent 主链路 116 用例中的相关回归全绿（无破坏 AC 之外的行为）
  </done>
  <depends_on></depends_on>
</task>

<task id="T03" parallel="true" status="done" completed_at="2026-11-21 17:42">
  <name>重放核心行为单测：隔离性 / 零写入 / 只跑剩余节点</name>
  <read_files>
    backend/app/modules/agent/runtime.py
    backend/app/infrastructure/checkpoint.py
    backend/app/modules/agent/service.py
    backend/tests/conftest.py
    backend/tests/test_tool_calling_phase1.py
    backend/tests/test_agent_workflows.py
    backend/tests/test_agent_checkpoint_reconnect.py
  </read_files>
  <write_files>
    backend/tests/test_checkpoint_replay_unit.py
  </write_files>
  <action>
    新建单测文件，用 `FakeToolLLM` 风格的可控假 LLM（照 tests/test_tool_calling_phase1.py 的写法）+
    `create_app(settings, llm=fake)` 走真实 sqlite checkpointer。

    断言清单（每条对应 AC）：
    - **AC-2 零污染**：在真 run 跑完后记录原 thread 的 `checkpoint 行数`、`get_state().values`、
      `get_state().next`；执行 `runtime.replay_from_checkpoint(...)` 后再断言三者逐项不变。
      行数用 `graph.get_state_history` 长度或直连 sqlite `select count(*)`，二者择一但要在注释里说明。
    - **AC-3 零业务写入**：重放前后对 `conversation_messages` / `agent_runs` / `agent_run_events` /
      `tasks` 表做 `count(*)` 对比，必须完全相等。
    - **AC-5 可重复**：同一 (thread, checkpoint) 连跑两次都成功，两次的 replay_thread_id 不同，
      且第二次跑完第一次的 replay thread 不受影响。
    - **只跑剩余节点**：用一个记录 `calls` 的假 LLM / 假 tool_workflow，断言重放时 `classify` 未被二次调用
      （即从 prepare/respond 段起跑），这直接证明 as_node 锚定生效。
    - **拒绝路径**：`next` 为空的终点 checkpoint → `checkpoint_terminal`；
      interrupt 挂起点 → `checkpoint_interrupted`；不存在的 checkpoint_id → `checkpoint_not_found`。

    允许在测试里直接构造 AgentRuntime（传 settings + SqliteSaver）以避开 HTTP 层，但必须用真实 sqlite 文件，
    不用 MemorySaver —— 否则"行数不变"这条断言没有意义。
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t03 tests/test_checkpoint_replay_unit.py
  </verify>
  <done>
    AC-2 / AC-3 / AC-5 与"只跑剩余节点"、"三条拒绝路径"全部由断言覆盖且通过
  </done>
  <depends_on>T02</depends_on>
</task>

<task id="T04" parallel="true" status="done" completed_at="2026-11-21 17:34">
  <name>AdminService 编排 + 响应 schema</name>
  <read_files>
    backend/app/modules/admin/service.py
    backend/app/modules/admin/schemas.py
    backend/app/modules/admin/checkpoint_repository.py
    backend/app/modules/agent/runtime.py
    backend/app/core/exceptions.py
    backend/app/api/schemas.py
  </read_files>
  <write_files>
    backend/app/modules/admin/service.py
    backend/app/modules/admin/schemas.py
  </write_files>
  <action>
    ⚠️ 见文末「修正 2」：本任务**不再需要** `routing_target` 参与重放，锚点由 runtime 自解。

    schemas.py 增加四个模型（沿用 `CamelModel`，前端拿到的就是 camelCase）：
    `ReplaySourceOut` / `ReplayRunOut` / `ReplayDiffOut` / `CheckpointReplayOut`，
    字段与 DESIGN §3 响应体逐项对齐（source/replay/diff 三段，含 prompt_version 与 model）。

    service.py 增加 `replay_checkpoint(self, admin_id, thread_id, checkpoint_id, agent_runtime) -> CheckpointReplayOut`，
    负责编排与**拒绝前置**（顺序不可换）：
    1) `self.checkpoint_repository.get(thread_id, checkpoint_id)` 为 None → `checkpoint_not_found` 404
       （复用既有的 404 文案，别新造）。
    2) 委托 `agent_runtime.replay_from_checkpoint(thread_id, checkpoint_id)`。
       锚点由 runtime 从父快照解析；`checkpoint_terminal` / `checkpoint_interrupted` /
       `replay_anchor_ambiguous` 三种 409 均由 runtime 抛出，service 只透传，不重复判断。
    3) `self.log(admin_id, "重放 checkpoint", "checkpoint", checkpoint_id, thread_id)` —— 复用既有操作日志，
       管理员动作必须留痕；这是**唯一**允许的写入，且写的是 admin 自己的日志表（不违反 AC-3，AC-3 管的是业务表与 agent 表）。

    （原第 2、3 步「取 parent_id → 调 routing_target 算 anchor」已删除，见文末「修正 2」。）

    不做：不在 service 里碰 checkpointer、不建图、不算 diff（都是 runtime 的职责）。

    agent_runtime 由 router 通过 `request.app.state.agent_runtime` 传入，service 不持有它（保持现有构造函数不变，
    不新增依赖注入项——这会让 WIP 基线里已有的 fixture 全部要改）。
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/ruff check app/modules/admin/service.py app/modules/admin/schemas.py &amp;&amp; .venv/bin/python -c "from app.modules.admin.service import AdminService; from app.modules.admin.schemas import CheckpointReplayOut; assert hasattr(AdminService,'replay_checkpoint')" &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t04 tests/test_admin_checkpoints.py
  </verify>
  <done>
    schema 可实例化、service 方法可导入、既有 admin checkpoint 4 条用例不回归；四条拒绝路径的顺序在代码里可读
  </done>
  <depends_on>T01,T02</depends_on>
</task>

<task id="T05" parallel="false" status="done" completed_at="2026-11-21 17:36">
  <name>新增重放端点</name>
  <read_files>
    backend/app/modules/admin/router.py
    backend/app/modules/admin/service.py
    backend/app/core/security.py
  </read_files>
  <write_files>
    backend/app/modules/admin/router.py
  </write_files>
  <action>
    在既有 router 上追加：
    `POST /admin/checkpoints/{thread_id}/{checkpoint_id}/replay`，`response_model=CheckpointReplayOut`，
    `Depends(require_admin)`；从 `request.app.state.agent_runtime` 取运行时传给 service。
    路径刻意放在既有 `GET /checkpoints/{thread_id}/{checkpoint_id}` 之后，避免与列表路由的匹配顺序冲突。
    不改 `get_admin_service` 的依赖链，不新增全局单例。

    端点内不做业务判断，全部委托 service（保持与既有 4 个端点一致的薄壳风格）。
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/ruff check app/modules/admin/router.py &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t05 tests/test_admin_checkpoints.py
  </verify>
  <done>
    端点已注册且不破坏既有 admin 路由；未授权访问由 require_admin 拦截（由 T06 断言 401/403）
  </done>
  <depends_on>T04</depends_on>
</task>

<task id="T06" parallel="false" status="pending">
  <name>API 层端到端测试：契约 / 权限 / 降级</name>
  <read_files>
    backend/tests/test_admin_checkpoints.py
    backend/tests/conftest.py
    backend/app/modules/admin/router.py
    backend/app/modules/admin/service.py
    backend/app/modules/admin/schemas.py
    backend/app/modules/agent/runtime.py
  </read_files>
  <write_files>
    backend/tests/test_checkpoint_replay_api.py
  </write_files>
  <action>
    新建 API 测试，复用 test_admin_checkpoints.py 里的 login/auth 写法与 `seed_checkpoints` 的造数思路
    （但要注意：手工 put 的 empty_checkpoint 没有真实图数据，只能验拒绝路径；能跑通的正向用例需先用假 LLM
    跑一次真实 run 产生可重放的 checkpoint）。

    断言清单：
    - **AC-1**：正向重放返回 200，响应含 `source` / `replay` / `diff` 三段；`replay.promptVersion`
      与 `source.promptVersion` 同时存在；`replay.durationMs` 为正整数。
    - **AC-4**：不存在 id → 404 `checkpoint_not_found`；终点 checkpoint → 409 `checkpoint_terminal`；
      无唯一产出节点 → 409 `replay_anchor_ambiguous`。
    - **AC-6**：普通用户 → 403，匿名 → 401；`checkpoint_sqlite_path` 指向不存在文件（即 `_url()` 为 None）
      时 → 404 或 503，但**必须不是 500 且不含 traceback**。
    - **AC-2 的 HTTP 视角**：正向重放前后，对原 thread 再发一次 `GET /checkpoints?thread_id=` 断言 total 不变。
    - 响应字段是 camelCase（`promptVersion` / `checkpointRowsAdded`），避免前端契约错位。
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t06 tests/test_checkpoint_replay_api.py
  </verify>
  <done>
    AC-1 / AC-4 / AC-6 全部由 HTTP 断言覆盖；AC-2 在 HTTP 视角再验一次；无 500 泄漏
  </done>
  <depends_on>T05</depends_on>
</task>

<task id="T07" parallel="false" status="pending">
  <name>真实 checkpoint 手工验证与证据落盘（部署后）</name>
  <read_files>
    .specs/checkpoint-replay/REQUIREMENT.md
    .specs/checkpoint-replay/DESIGN.md
    backend/app/modules/agent/runtime.py
    docs/生产部署记录-20261120.md
  </read_files>
  <write_files>
    .specs/checkpoint-replay/REPLAY-EVIDENCE.md
  </write_files>
  <action>
    属 7-integration 阶段（部署新 release 之后执行），不在 4-dev 跑。做法照 11-20 那次生产探针的路径：
    在服务器 `backend/` 目录下以 `PYTHONPATH=$PWD` 执行脚本（否则会加载 venv 里那份残缺的
    `site-packages/app`，踩 11-20 记录的坑），挑一个真实 thread 的中间 checkpoint 跑一次重放。

    证据必须包含：source/replay 的 route、response 摘要、prompt_version、model、duration_ms、
    重放前后的原 thread checkpoint 行数（相等）、以及 `agent_runs` 行数（相等）。

    若生产上找不到可重放的中间 checkpoint，就地在本地用 sqlite 造一个完整 run 再重放，
    并在文件里明确标注"evidence from local sqlite, not production"，不许含糊。
  </action>
  <verify>
    test -s .specs/checkpoint-replay/REPLAY-EVIDENCE.md &amp;&amp; grep -q "原 thread 行数" .specs/checkpoint-replay/REPLAY-EVIDENCE.md
  </verify>
  <done>
    证据文件含一次真实重放的完整三段响应摘要 + 原链行数前后对比（AC-1 的实物证据）
  </done>
  <depends_on>T06</depends_on>
</task>
```

> **注意**：`write_files` 严格限定在 DESIGN `## 0.5.1`（agent / admin / infrastructure）范围内；
> 测试文件属本 change 新增，不属于既有模块清单，单独列出。`.specs/checkpoint-replay/` 只有 T07 写。
> **禁动清单**：`backend/app/modules/agent/runtime.py` 的图结构（`build_agent_graph` 的节点与边）、
> `AgentState` 定义、`_execute_new_run` / `_execute_confirm`、`infrastructure/checkpoint.py`、
> 任何 `alembic/versions/*`、前端全部文件 —— 均不得出现在任何 `write_files` 里（已核对，无一命中）。

---

## 状态字段说明

- `status="pending"` — 未开始
- `status="in_progress"` — 进行中（同时只允许一个非 [P] 任务为此状态）
- `status="done"` — 已完成（verify 通过）
- `status="blocked"` — 阻塞（必须在文件末尾「阻塞日志」记录）

---

## 阻塞日志

| 任务 | 阻塞原因 | 待人工决策项 | 时间 |
|---|---|---|---|
| W00 | 三个 admin 文件同时含 WIP 与本 change 改动，无法按文件切分提交 | 是否先提交 checkpoint 巡检 WIP 作为基线（建议提交） | 2026-11-21 |
| T07 | 需先部署新 release 才能在真实数据上验证 | 部署时机（是否随本 change 一起发布） | 2026-11-21 |

---

## 与设计的偏离（执行中实测修正 · 2026-11-21）

> 以下两条由 T02 执行时的实测推翻原设计，**DESIGN.md 未擅自修改**（R3.2），记录在此供后续批准与回写。

### 修正 1：锚点由 runtime 内部解析，DESIGN §2.3 的取法 off-by-one

DESIGN §2.3 说「目标 checkpoint 的产出节点 = 它 parent 的 `writes.branch:to` 目标」。实测（临时 SQLite，a→b 图，langgraph 1.2.19）：

```
mid          next=('b',)  values={'text':'a'}      ← 由 a 产出
mid.parent   branch:to 目标 = 'b'                  ← 设计的取法，拿到的是「下一跳」
mid.parent   next = ('a',)                         ← 真正的产出节点
grandparent  branch:to 目标 = 'a'
```

| as_node | update_state 后 next | 实际执行 | 结果 |
|---|---|---|---|
| `'a'`（父的 next） | `('b',)` | `['b']` | `{'text':'b'}` ✅ |
| `'b'`（设计原公式） | `()` | `[]` | `{'text':'a'}`，**什么都没跑**却返回 200 |
| 不传锚点 | `('a',)` | `['a','b']` | 已完成节点被重跑 |

因此 **T02 的签名改为 `replay_from_checkpoint(thread_id, checkpoint_id)`**，锚点在方法内部由 `src.parent_config` 的快照取 `parent.next`：
- `len(parent.next) != 1` → `replay_anchor_ambiguous` 409
- `parent_config` 为空（入口 checkpoint）→ `checkpoint_terminal` 409

### 修正 2：T04 不再需要 `routing_target` 参与重放

原计划 T04 用 `CheckpointRepository.routing_target()` 算锚点再传给 runtime。修正后 runtime 自解，T04 只做：
1. `repository.get()` 校验存在（404）
2. 委托 `agent_runtime.replay_from_checkpoint(thread_id, checkpoint_id)`
3. 记操作日志

`routing_target` / `count_thread`（T01）保留，作为管理页的诊断能力，**不进入重放链路**。这也顺带消除了原先「agent → admin 反向依赖」的顾虑，比原方案更干净。

---

## Fix 任务（来自 DEV 过程中的实测缺陷）

```xml
<task id="T-FIX-01" parallel="false" status="done" completed_at="2026-11-21 17:44">
  <name>修正「存在性」判断：入口 checkpoint 被误报 404</name>
  <read_files>
    backend/app/modules/agent/runtime.py
    backend/tests/test_checkpoint_replay_unit.py
  </read_files>
  <write_files>
    backend/app/modules/agent/runtime.py
  </write_files>
  <action>
    T03 写测试时发现：真实 run 的 input checkpoint（step=-1）`values == {}`，
    而原实现用 `if not src.values` 判「checkpoint 不存在」，导致对**存在的入口**
    返回 404 checkpoint_not_found —— 管理员会以为数据丢了。

    实测 get_state 的返回差异：
    - 不存在：created_at=None、metadata=None、tasks=()、values={}、next=()
    - 真实入口：created_at 有值、metadata={'source':'input','step':-1}、next=('__start__',)、values={}

    改用 `src.created_at is None` 判存在。修正后：
    - 入口 → 走 `parent_config is None` 分支 → 409 checkpoint_terminal
    - 不存在的 id / thread → 404 checkpoint_not_found
  </action>
  <verify>
    cd backend &amp;&amp; .venv/bin/pytest -q --basetemp=/tmp/fla-t03-after tests/test_checkpoint_replay_unit.py
  </verify>
  <done>真实入口返回 409 terminal、不存在返回 404；8 条单测与全量 130 用例全绿</done>
  <depends_on>T02,T03</depends_on>
</task>
```

---

## 自检

- [x] 每个任务都有完整 7 字段
- [x] `write_files` 全部在触碰模块 + 本 change 新增文件范围内
- [x] 无任务写禁动清单文件
- [x] 每个 `verify` 都是可执行命令（后端用 `--basetemp` 规避沙箱 tmp 目录 EEXIST）
- [x] 有 2 个 `[P]` 并行任务（T01/T02、T03/T04）
- [x] 波次无环依赖
- [x] 编号连续 T01–T07

---

## 后续阶段

- `@flow-kit/prompts/4-dev.md`（按波次执行 T01–T06；先确认 W00）
- `@flow-kit/prompts/5-test.md`（T03/T06 已含单测，5-test 侧重边界补充与 AC 覆盖核对）
- T07 在 7-integration 执行
