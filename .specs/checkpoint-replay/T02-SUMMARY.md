# SUMMARY: T02 - AgentRuntime.replay_from_checkpoint 核心实现

- **Change ID**: checkpoint-replay
- **Task ID**: T02
- **完成时间**: 2026-11-21 17:16
- **AI 角色**: Dev

---

## 做了什么（一段话）

在 `AgentRuntime` 上新增 `replay_from_checkpoint(thread_id, checkpoint_id)`：用 `CheckpointerManager` 自开一条连接、重建图，读目标快照后拒绝三种不可重放状态（不存在 / interrupt 挂起 / 已到终点），自行解析锚点（父快照的 `next`），再把 `src.values` 灌进 `replay-<uuid>` 新 thread 并以 `as_node=anchor` 续跑，最后组装 `source` / `replay` / `diff` 三段返回。全程不碰 `self.checkpointer`、不获取 `_execution_lock`、不调用任何落库或确认函数。

**与 TASK 的一处偏离（实测驱动）**：原计划由 admin 层算好 `anchor` 传进来，实现时发现 DESIGN §2.3 的取法（父 checkpoint 的 `writes.branch:to` 目标）是 **off-by-one**，改为方法内部读父快照的 `next` 解析锚点，签名随之去掉 `anchor` 参数。详见「决策与偏离」第 1 条。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/modules/agent/runtime.py` | 修改 | 新增常量 `_REPLAY_TIMEOUT_SECONDS`、3 个 import（`concurrent.futures` / `uuid` / `CheckpointerManager`）与 `replay_from_checkpoint` 方法；纯新增，无删除 |

## verify 输出（必填）

```text
$ .venv/bin/ruff check app/modules/agent/runtime.py
All checks passed!

$ .venv/bin/ruff format --check app/modules/agent/runtime.py
1 file already formatted

$ .venv/bin/python -c "from app.modules.agent.runtime import AgentRuntime; print(hasattr(AgentRuntime,'replay_from_checkpoint'))"
True

$ .venv/bin/pytest -q --basetemp=/tmp/fla-verify-t02b tests/test_agent_checkpoint_reconnect.py tests/test_agent_workflows.py
.................                                                        [100%]
17 passed in 6.47s
```

端到端冒烟（真 SqliteSaver + TestClient + fake LLM，脚本在 `/tmp` 不入库；锚点修正后重跑）：

```text
source run prompt_version: v1:14cbaab47286
history: 4
  snap 2 next=()             interrupts=[]
  snap 1 next=('respond',)   interrupts=[0]     ← 重放起点
  snap 0 next=('classify',)  interrupts=[0]
  snap -1 next=('__start__',)

replay from step 1 next ('respond',)
{"source": {"step":1, "next":["respond"], "route":"chat", "response":null,
            "prompt_version":"v1:14cbaab47286"},
 "replay": {"thread_id":"replay-11f63306-…", "route":"chat", "response":"兜底",
            "token_usage":null, "duration_ms":6, "prompt_version":"v1:14cbaab47286",
            "model":"gpt-4.1-mini", "checkpoint_rows_added":2},
 "diff":   {"route_changed":false, "response_changed":true, "pending_action_changed":false}}

[AC-2] 原 thread history: 4 -> 4        ← 零污染
[AC-2] 原 thread 最新 next: ()
[重放] 结束后 next = ()                  ← respond 已真的执行
[AC-4] missing  -> checkpoint_not_found 404
[AC-4] terminal -> checkpoint_terminal 409
```

## 6 维自查（生产代码改动必填 · 来自 4-dev 步骤 4）

> 未装 brooks-lint，走内置 R1~R6 快查。

- ✅ **R1 认知过载**：🟡 方法本体约 110 行，超 50 行阈值。但它是线性流程（读快照 → 三个拒绝 → 灌 state → 跑 → 组装），拆成子函数会导致 `saver` / `graph` / `src` 三个上下文对象来回传递，可读性反而下降。**已知接受**，理由记于此；若后续加入 dry-run 或落库再拆。
- ✅ **R2 变更传播**：只改 `runtime.py`，未动图结构、节点、`AgentState`、`_execute_*`。
- ✅ **R3 知识重复**：token 增量计算只此一处；`prompt_version` 复用与 `_execute_new_run` 相同的拼法。
- ✅ **R4 偶然复杂**：没有加"以后可能用到"的参数或开关；三个拒绝路径都对应 AC-4。
- ✅ **R5 依赖混乱**：`agent` 未 import `admin`（`checkpoint_rows_added` 改用 `get_state_history`，未调 `CheckpointRepository`）。
- ✅ **R6 领域扭曲**：命名为 `source` / `replay` / `anchor` / `pending_action`，均为业务词，无 `data` / `info` / `item`。

## 越界检查（必填 · 来自 4-dev 步骤 5 / R6.5）

```text
✅ TASK 声明的 write_files：
  - backend/app/modules/agent/runtime.py

✅ 实际 diff 涉及：
  - backend/app/modules/agent/runtime.py（+146/-0）

→ 越界：0
```

## 破坏性变更（涉及破坏性改动必填 · 来自 4-dev 步骤 1.8）

**未命中**：diff 为 146 insertions / 0 deletions，无公共导出签名变更、无路由变更、无删文件。

## 决策与偏离（如有）

### 1. 锚点改为方法内部解析 — 实测推翻了 DESIGN §2.3 的取法（重要）

DESIGN §2.3 写的是「目标 checkpoint 的产出节点 = 它 parent 的 `writes.branch:to` 目标」。实测（临时 SQLite，a→b 两节点图，langgraph 1.2.19）：

```
mid          next=('b',)  values={'text':'a'}      ← 由节点 a 产出
mid.parent   branch:to 目标 = 'b'                  ← DESIGN 的取法，得到的是「下一跳」
mid.parent   next = ('a',)                         ← 真正的产出节点
grandparent  branch:to 目标 = 'a'                  ← 上溯一层才等于产出节点
```

三种锚点对重放的实际效果：

| as_node | update_state 后 next | 实际执行节点 | 最终 values |
|---|---|---|---|
| `'a'`（父的 next，**采用**） | `('b',)` | `['b']` | `{'text':'b'}` |
| `'b'`（DESIGN 原公式） | `()` | `[]` | `{'text':'a'}`（**什么都没跑**） |
| 不传（无锚点） | `('a',)` | `['a','b']` | 已完成节点被重跑 |

**危害**：按原公式实现，重放会**正常返回 200**、`diff` 全为 `false`，看起来像"重放确认原结果稳定"，实际一个节点都没执行。这是最容易误导人的失败模式。

**修正**：方法内部读 `src.parent_config` 的快照，取 `parent.next`：
- `len(parent.next) != 1` → `replay_anchor_ambiguous` 409（并行分支时安全失败）
- `src.parent_config` 为空（入口 checkpoint）→ `checkpoint_terminal` 409

好处：不再依赖 `writes` 表 `branch:to:` 的字符串语义；`agent` 也不需要 import `admin` 的 `CheckpointRepository`；接口只剩两个参数。

**待办**：DESIGN §2.3 与 §9.1 仍是旧写法，**未擅自修改**（R3.2）。建议由用户在 `A-evolve` 或本轮直接批准修订；T01 的 `producing_node` 保留但**不参与重放**，仅用于管理页诊断。

### 2. 超时不用 `with ThreadPoolExecutor`

`__exit__` 会 `wait=True`，超时形同虚设。改为手动 `shutdown(wait=False, cancel_futures=True)`，注释已写明。线程无法 kill，日志保留 `replay_thread` 供清理（DESIGN 风险表已登记）。

### 3. `out` 与 `new_tid` 在 `with CheckpointerManager` 块外使用

`out` 是普通 dict，连接关闭后再读无副作用；`get_state_history` / `get_state` 都在块内完成。

### 4. 实测补充

langgraph 1.2.19 + SqliteSaver 下 `snap.metadata` 只有 `source` / `step` / `parents`，**没有 `writes` 键**，因此锚点无法从 `get_state_history` 的 metadata 取 —— 这也是改用父快照 `next` 的旁证。

### 5. 后续修正（T-FIX-01，由 T03 发现）

本任务最初用 `if not src.values` 判断「checkpoint 不存在」。T03 写测试时发现真实 run 的入口 checkpoint（`step=-1`）`values` 也是 `{}`，于是被误报成 404「不存在」。

实测差异：

| | `created_at` | `metadata` | `tasks` | `values` | `next` |
|---|---|---|---|---|---|
| 不存在的 id | `None` | `None` | `()` | `{}` | `()` |
| 真实入口 | 有值 | `{'source':'input','step':-1}` | 1 项 | `{}` | `('__start__',)` |

已改为 `if src.created_at is None`。修正后入口 → 409 `checkpoint_terminal`，不存在的 id / thread → 404。详见 `T03-SUMMARY.md` 与 `TASK.md` 的 `T-FIX-01`。

## 是否触发新工作

无。

## 完成判定

verify 全绿（ruff + import + 17 passed），冒烟四场景符合 AC-1 / AC-4 预期 → **T02 done**。
