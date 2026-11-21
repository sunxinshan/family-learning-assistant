# SUMMARY: T03 - 重放核心行为单测

- **Change ID**: checkpoint-replay
- **Task ID**: T03
- **完成时间**: 2026-11-21 17:42
- **AI 角色**: Dev

---

## 做了什么（一段话）

新建 `tests/test_checkpoint_replay_unit.py`，8 条用例全部真跑通（无 skip、无 xfail），用 fake LLM + 真实 sqlite checkpointer 覆盖：原 thread 零污染、零业务写入、可重复、只跑剩余节点、四条拒绝路径。interrupt 用例没有降级 —— 用 `route="task_create"` 的 fake LLM + 通过 API 真实建一个词库，稳定走到 `wait` 节点的 `interrupt()`，命中 409。

**过程中发现 T02 的实现缺陷**（入口 checkpoint 被误报为 404），已作为 `T-FIX-01` 单独修复并登记，见「越界检查」。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_checkpoint_replay_unit.py` | 新增 | 8 个用例 |
| `backend/app/modules/agent/runtime.py` | 修改 | T-FIX-01：存在性判断 `not src.values` → `src.created_at is None` |

## verify 输出（必填）

```text
$ .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t03 tests/test_checkpoint_replay_unit.py
........                                                                 [100%]
8 passed in 3.34s

$ .venv/bin/pytest -q --basetemp=/tmp/fla-t03-after tests/test_checkpoint_replay_unit.py tests/test_agent_checkpoint_reconnect.py
............                                                             [100%]
12 passed in 3.04s

$ .venv/bin/pytest -q --basetemp=/tmp/fla-full          # 全量
130 passed in 33.25s

$ .venv/bin/ruff check tests/test_checkpoint_replay_unit.py
All checks passed!
```

实测到的 checkpoint 结构（chat 流程，`START → classify → respond → END`）：

```text
[0] step=2  next=()            values 非空     ← 终点
[1] step=1  next=('respond',)  values 非空     ← 重放起点
[2] step=0  next=('classify',) values 非空
[3] step=-1 next=('__start__',) values={}       ← 入口（输入在 pending writes 里）
```

task_create 流程（`classify → prepare → wait`）在 step=2 处 `next=('wait',)` 且
`tasks[0].interrupts` 为 `('wait', [{action: create_task, draft_version: 1, ...}])`，正是 409 的拒绝点。

## 用例与 AC 对应

| 用例 | AC |
|---|---|
| `test_replay_does_not_pollute_source_thread` | AC-2：history 条数、values、next 三项不变 |
| `test_replay_writes_no_business_rows` | AC-3：`conversation_messages` / `agent_runs` / `agent_run_events` / `tasks` 四表计数相等 |
| `test_replay_is_repeatable_and_keeps_previous_replay_thread` | AC-5：两次 thread 不同，第一次的重放结果仍在 |
| `test_replay_runs_only_remaining_nodes` | 核心：`classify_calls` 1→1 不增，`source.next == ["respond"]`，`response_changed=True` |
| `test_replay_rejects_unknown_checkpoint` | AC-4：404 |
| `test_replay_rejects_terminal_checkpoint` | AC-4：409 terminal |
| `test_replay_rejects_interrupted_checkpoint` | AC-4：409 interrupted |
| `test_replay_rejects_entry_checkpoint_without_parent` | AC-4：409 terminal（入口） |

## 6 维自查（测试代码，简版）

- ✅ **R1**：每个用例 < 40 行，夹具抽成模块级 helper。
- ✅ **R2**：只新增测试文件 + T-FIX-01 的 1 行实现修正。
- ✅ **R3**：`create_chat_run()` / `create_task_create_run()` 两个 helper 复用，未复制粘贴建 run 的流程。
- ✅ **R4**：没有为"以后可能测"的路径写占位用例。
- ✅ **R5**：测试只通过公开接口（HTTP + runtime 方法）观察，未直接操作内部字段。
- ✅ **R6**：用例名用 `pollute` / `repeatable` / `remaining` 等行为词。

## 越界检查（必填 · 来自 4-dev 步骤 5 / R6.5）

```text
✅ TASK 声明的 write_files：
  - backend/tests/test_checkpoint_replay_unit.py

⚠️ 实际 diff 涉及：
  - backend/tests/test_checkpoint_replay_unit.py（新增）
  - backend/app/modules/agent/runtime.py（+3/-1，存在性判断）

→ 越界：1（runtime.py）
→ 处置：**不是顺手改**。是 T03 的测试暴露了 T02 的实现缺陷（存在入口被报 404），
  按 4-dev 5.2「拆成新任务」处理，已登记为 T-FIX-01 并附实测证据；
  未扩大本任务的 write_files，修复单独成 commit，可单独回滚。
```

## 破坏性变更

**未命中**：新增测试文件；runtime 的改动是替换一个条件判断，无签名变化。

## 决策与偏离

1. **interrupt 用例不降级**：先用 fake LLM 打印 `get_state_history` 确认 `next=('wait',)` 与 `interrupts` 结构，再通过 API 建词库让 prepare 走通，真实命中 409。
2. **入口 checkpoint 的覆盖方式有变化**：原本打算用真实 input checkpoint 断言 409，实测它是 404（因为 `not src.values` 先命中）。没有改断言迁就，而是**修了实现**（T-FIX-01），修完后真实入口确实返回 409；测试里另保留一条人工构造 `parent_config is None` 且 values 非空的快照，专门守 `parent_config` 这条分支。
3. **行数统计用 `get_state_history`**，注释已说明；未直连 sqlite 做二次交叉（repository 单测 T01 已覆盖 SQL 层计数）。

## 是否触发新工作

**是**：T-FIX-01（已完成）。无其它。

## 完成判定

8 条用例 + 全量 130 passed → **T03 done**。
