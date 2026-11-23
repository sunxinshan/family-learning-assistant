# DESIGN: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **创建日期**: 2026-11-21
- **上游**: `CHANGE.md` / `REQUIREMENT.md`

---

## 0. 技术栈选定

**无新增依赖**。全部用现有能力：`langgraph>=1.2` 的 `get_state` / `update_state(as_node=...)` / `invoke(None, ...)`，项目已有的 `CheckpointerManager`、`build_agent_graph`、`_with_checkpoint_retry`、`AppError`。

## 0.5 既有架构对齐

### 0.5.1 本次触碰的既有模块

| 模块 | 改动性质 |
|---|---|
| `agent` | `AgentRuntime` 新增一个方法 `replay_from_checkpoint()`；图结构、节点、状态零改动 |
| `admin` | 新增一个只读语义的端点 + service 转发；复用未提交 WIP 的 `CheckpointRepository` 做校验 |
| `infrastructure` | 不改。`CheckpointerManager` 原样复用作"第二连接"的开关 |

### 0.5.2 既有抽象沿用对照表

| 已有抽象 | 位置 | 本次怎么用 | 不新建的理由 |
|---|---|---|---|
| `CheckpointerManager` | `infrastructure/checkpoint.py:12` | `with` 开一个**独立** saver 给重放用 | 已支持 sqlite/mysql 切换，且 `__exit__` 会关连接 |
| `build_agent_graph` | `agent/runtime.py:103` | 用独立 saver 重新 build 一份图 | 保证重放跑的是**当前**代码，正是目的 |
| `_with_checkpoint_retry` | `agent/runtime.py:65` | 包住 `get_state` / `update_state` / `invoke` | 重放同样会碰上空闲连接被掐 |
| `AppError` | `core/exceptions.py` | 拒绝路径用语义化 code | 与全局异常处理一致 |
| `CheckpointRepository` | `admin/checkpoint_repository.py`（WIP） | 校验目标 checkpoint 存在、取元信息 | 已能直连 checkpoint 库并脱敏 |

**不引入新模式**：没有新的队列、没有新表、没有后台 worker。

---

## 1. 决策清单

| # | 决策 | ADR |
|---|---|---|
| D1 | 重放跑在**新 thread**，绝不在原 thread 上续跑 | ADR-017 |
| D2 | 无副作用靠"不经过写入路径"保证，不靠运行时开关 | ADR-018 |
| D3 | 锚定产出节点用 `writes.branch:to:<node>`，歧义即拒绝 | ADR-019 |
| D4 | 重放自建 checkpointer 连接，不共用主连接、不抢执行锁 | ADR-020 |
| D5 | MVP 不落库，返回即弃 | ADR-021 |

---

## 2. 机制与实测证据

### 2.1 实测（关键，推翻了两条想当然的做法）

在临时 SQLite 上跑两节点图（`a → b`），langgraph 1.2：

| 做法 | 结果 | 结论 |
|---|---|---|
| `invoke(None, {thread_id: 新, checkpoint_id: 旧})` | `EmptyInputError: Received no input for __start__` | **跨 thread 借 checkpoint 不可行** |
| 同 thread 指定 `checkpoint_id` 续跑 | 原 thread 历史从 4 条变 6 条 | **会 fork 出分支污染原链**，`get_state(thread)` 取最新会变 |
| 新 thread + `update_state(values)` 无锚点 | `next=('a',)`，`a` 被执行两次（`seq=[a,a,b]`） | **会重跑已完成节点**，副作用节点会重复执行 |
| 新 thread + `update_state(values, as_node='a')` | `next=('b',)`，只执行 `b`，结果 `[a,b]` 与原链一致 | ✅ 采用 |

### 2.2 重放流程

```
POST /api/v1/admin/checkpoints/{thread_id}/{checkpoint_id}/replay
   │
   ├─ require_admin
   ├─ src = graph.get_state({thread_id, checkpoint_id})      # 带重连重试
   ├─ src.next 为空            → 409 checkpoint_terminal（已到 END，无可重放节点）
   ├─ src.metadata.source == "interrupt"/有待解决 interrupt → 409 checkpoint_interrupted
   ├─ as_node = producing_node(thread_id, src.parent checkpoint_id)   # ADR-019
   │      无 / 多个 branch:to → 409 replay_anchor_ambiguous
   ├─ new_tid = f"replay-{uuid4()}"
   ├─ update_state({thread_id: new_tid}, src.values, as_node=as_node)
   ├─ invoke(None, {thread_id: new_tid})
   ├─ out = get_state({thread_id: new_tid}).values
   └─ 组装对照结果返回，关闭独立连接
```

要点：`update_state` 之后 `next` 会被重算成 `as_node` 的后继，因此**只跑尚未执行的节点**，已完成的节点不会重跑。这一步是"重放"和"重复执行"的分界线。

### 2.3 产出节点的取法（ADR-019 落地）

```sql
select channel from writes
where thread_id = :thread_id
  and checkpoint_id = :parent_checkpoint_id
  and channel like 'branch:to:%'
```

`channel = 'branch:to:b'` 表示"上一个 checkpoint 把控制权交给了 `b`"。所以目标 checkpoint 的**产出节点** = 它 **parent** 的 `branch:to` 目标。实测已印证：`mid` 的 parent 的 writes 里有 `branch:to:a`，故产出节点为 `a`。

- 命中 1 条 → 用它。
- 0 条或多条 → **拒绝**（`replay_anchor_ambiguous`），不猜。多分支图（未来的并行边）会落到这里，属于安全失败。

### 2.4 为什么不需要 dry-run 开关（ADR-018，2026-11-23 按 REVIEW C-1 修正）

业务写入只发生在两处，都不在图内：

| 写入点 | 位置 | 重放是否经过 |
|---|---|---|
| 消息落库（user / assistant / tool_call / tool_result） | `_execute_new_run` / `_execute_confirm` 在图执行**之后**调用 | ❌ 不经 |
| 业务写入（建任务、删任务、建词库） | `AgentBusinessService.execute()`，仅由 `_execute_confirm` 调用 | ❌ 不经 |

**原文"图内四个节点只读"是错的**（6-review C-1）：漏了 `prepare` 的**分支副作用** ——
`prepare_vocabulary_import` 会调 `ContentService.extract()`（`agent/service.py:500`），
它 `repository.add(ContentExtraction)` 且 `material.status="parsed"`（`content/service.py:61-62`），
`Database.session()` 退出即 commit。按节点名概括"只读"，等于把整条无副作用论证建在假前提上。

逐节点的真实副作用（复核结论，替代原来的概括）：

| 节点 | 真实副作用 | 可否重放 |
|---|---|---|
| `classify` | 无（一次 LLM 调用） | ✅ |
| `tool_create` | 只读预览工具（AGENTS.md 已约定预览类工具只读） | ✅ |
| `prepare`（task_create / task_update / task_delete / vocabulary_create） | 只读查询 + 拼 `pending_action` | ✅ |
| `prepare`（**vocabulary_import**） | **写 `content_extractions`、改 `materials.status`** | ❌ 409 `replay_unsupported_route` |
| `respond` | 查统计数据（learning）或调兜底 LLM | ✅ |
| `wait` | 只调 `interrupt()`；`business.execute()` 在**恢复**时才走，重放没有恢复值 | ✅ 但停在 interrupt（响应 `interrupted=true`） |

因此"不写"仍是**结构性**的，但"结构"要说全：
① 不调 runtime 的落库/确认函数；② 不重放带副作用的 `prepare` 分支（路由级 409 拒绝）。
比撒一堆 `if dry_run` 可靠 —— 因为漏掉一个分支就会静默写库，而路由拒绝会立刻报错。

### 2.5 连接与并发（ADR-020）

硬约束：`PyMySQLSaver` 内部是**一条** `pymysql.Connection`（11-20 的 `InterfaceError` 就是它）。同一条连接上并发跑两个图，cursor 会互相打断。

因此重放**不共用**主连接，而是自己开一条（`CheckpointerManager(settings)` → `saver`），跑完即关；图用这个 saver 重建：

```python
graph = build_agent_graph(replay_saver, self.llm, self.business, self.guidance, self.tool_workflow)
```

**不用 `with`**：`__exit__` 会 `shutdown(wait=True)`，超时形同虚设；而超时后请求线程若直接 close，
仍在跑的重放线程下一次写就会 `ping(reconnect=True)` 把连接**复活**，且再没人关（每次超时泄漏一条）。
所以连接归属按"谁最后用完谁关"：
`manager.close()` 幂等；超时后先等孤儿线程 `_REPLAY_DRAIN_SECONDS`，结束了由请求线程关，
没结束就把 manager 交给孤儿线程（`add_done_callback` 里关，并记录它的结局）。

好处是不用抢 `self._execution_lock`（那个锁在 `_execute_new_run` / `_execute_confirm` 里持有，抢不到就会让真实用户排队甚至租约过期）。代价是每次重放多一次 MySQL 建连（约几十毫秒，管理员调试场景可接受），且连接数 +1（需在 `max_connections` 余量内）。

---

## 3. 接口契约

```
POST /api/v1/admin/checkpoints/{thread_id}/{checkpoint_id}/replay
权限：require_admin
超时：60s（服务端给 invoke 套计时，超时返回 504 replay_timeout，已产生的 replay thread 保留待清理）
```

响应（`200`）：

```json
{
  "source": {
    "thread_id": "…", "checkpoint_id": "…", "step": 2, "next": ["wait"],
    "route": "task_create", "response": "…", "pending_action": {"operation": "create_task"},
    "prompt_version": "main_agent:abc123def456"
  },
  "replay": {
    "thread_id": "replay-…", "route": "task_create", "response": "…",
    "pending_action": {"operation": "create_task"},
    "interrupted": true,
    "token_usage": {"prompt_tokens": 812, "completion_tokens": 96},
    "duration_ms": 2410, "prompt_version": "main_agent:abc123def456",
    "model": "deepseek-v4-flash", "checkpoint_rows_added": 3
  },
  "diff": {"route_changed": false, "response_changed": true, "pending_action_changed": false}
}
```

`replay.interrupted`：重放停在 `wait`（等人工确认）时为 `true` —— 200 不等于"跑完了"，
没有这个字段，管理员会把"停在确认环节"读成"重放没生成回答"（6-review M-4）。

错误码：`checkpoint_not_found` 404 / `checkpoint_terminal` 409 / `checkpoint_interrupted` 409 /
`replay_anchor_ambiguous` 409 / `replay_unsupported_route` 409（vocabulary_import 等有副作用的 prepare 分支）/
`checkpoint_store_unavailable` 503（库连不上、驱动缺失、表名方言不对 —— **不是** 404） / `replay_timeout` 504。

> `prompt_version` 必须两边都给。重放用**当前** prompt，"结果不同"常常只是版本变了 —— 不给版本号，这个功能第一天就会被误读成"重放不稳定"。

---

## 4. ADR 索引

| ADR | 决策 | 理由 | 代价 |
|---|---|---|---|
| **ADR-017** | 重放跑在新 thread `replay-<uuid>` | 实测：同 thread 续跑会新增分支并改变 `get_state` 最新值，用户下次打开对话看到的是调试结果 | checkpoint 行数增加，需 TTL |
| **ADR-018** | 不设 dry-run 开关，靠不经过写入路径 | 开关会漏（新增节点忘记判断）；结构上不经 `execute()` 就不可能写 | 若将来把写入移进图节点，此保证失效 → 需重审 |
| **ADR-019** | 锚点取 parent 的 `branch:to:<node>`，歧义即拒绝 | 实测无锚点会重跑已完成节点；猜测在分支图里会静默错 | 并行边的图暂不支持重放（安全失败） |
| **ADR-020** | 重放自建 checkpointer 连接 | 单条 pymysql 连接不支持并发游标；抢全局锁会让真实用户租约过期 | 每次多一次建连；连接数 +1 |
| **ADR-021** | MVP 不落库 | 少一张表、少一次迁移，先验证链路是否有用 | 重放历史不可追溯，出了问题只能看日志 |

---

## 5. 风险

| 风险 | 影响 | 处置 |
|---|---|---|
| checkpoint 表膨胀 | 每次重放 3~4 行；`channel_values` 含完整 prompt/history，单行可能很大 | 响应里回 `checkpoint_rows_added`；v2 加 TTL 清理（`thread_id like 'replay-%'` 且超 30 天） |
| prompt 漂移 | 结果必然不同，被误判为"不稳定" | 响应带 `prompt_version`、`model`，diff 只做结构对比 |
| 费用 | 从 `classify` 前重放 = 完整链路 LLM 调用 | 管理员专属 + 60s 超时 + 日志留痕 |
| langgraph 升级 | `branch:to:` 写法规格若变，锚点取法失效 | 单测直接断言 `next == ('b',)` 与"只执行 b"；升级时这条测试会先红 |
| 连接数 | 每次重放 +1 连接 | 跑完即关（`with`）；不做连接池 |
| 长时阻塞 uvicorn | 同步路由占线程池 | 60s 上限；必要时改后台线程 + 事件表（v2） |

---

## 6. 不在范围

- 前端界面、AdminPage 按钮、差异高亮视图
- 重放记录落库与历史列表
- 注入式调试（改 state 再跑）
- 事件重放补强、崩溃续跑（各自独立 change）

---

## 9. 架构沉淀建议（供 `A-evolve` 用）

### 9.1 新增可复用抽象
- `AgentRuntime.replay_from_checkpoint(source_thread, source_checkpoint) -> dict`
- `CheckpointRepository.producing_node(thread_id, checkpoint_id) -> str | None`

### 9.2 新增技术决策（建议升 ARCHITECTURE「ADR 列表」）
- ADR-017 ~ ADR-021（见上）。其中 **ADR-018 与 ADR-020 是通用约束**，不只属于重放：
  - "图节点只读、写入在 runtime 层"是现有设计的隐式前提，本次显式化；
  - "PyMySQLSaver 单连接不可并发共享"应写进 ARCHITECTURE 的连接约束段。

### 9.3 新增跨模块契约
- `POST /api/v1/admin/checkpoints/{thread_id}/{checkpoint_id}/replay`（admin → agent）

### 9.4 依赖变化
- 无

### 9.5 禁动清单建议追加
- 不要为"省一条连接"把重放塞进主 checkpointer 的共享连接
- 不要给图节点加业务写入（会破坏 ADR-018 的无副作用保证）
