# SUMMARY: T06 - API 层端到端测试：契约 / 权限 / 降级

- **Change ID**: checkpoint-replay
- **Task ID**: T06
- **完成时间**: 2026-11-21 17:52
- **AI 角色**: Dev

---

## 做了什么（一段话）

新建 `tests/test_checkpoint_replay_api.py`，6 条用例走真实 HTTP：正向 200 的三段契约与 camelCase、404 / 409 两种拒绝、403 / 401 权限、checkpoint 库缺失时的降级、以及重放前后 `GET /checkpoints?thread_id=` 的 total 不变。全部用 fake LLM + 真实 sqlite checkpointer，零外部调用。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_checkpoint_replay_api.py` | 新增 | 6 个用例 |

## verify 输出（必填）

```text
$ .venv/bin/ruff check tests/test_checkpoint_replay_api.py
All checks passed!
$ .venv/bin/ruff format --check tests/test_checkpoint_replay_api.py
1 file already formatted

$ .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t06 tests/test_checkpoint_replay_api.py
......                                                                   [100%]
6 passed in 2.92s

$ .venv/bin/pytest -q --basetemp=/tmp/fla-final          # 全量
136 passed in 34.55s
```

一次真实 200 响应（实际 body，键名可辨 camelCase）：

```json
{
  "source": {
    "threadId": "9eaf3f73-…", "checkpointId": "1f1e58d8-…", "step": 1,
    "next": ["respond"], "route": "chat", "response": null,
    "pendingAction": null, "promptVersion": "v1:14cbaab47286"
  },
  "replay": {
    "threadId": "replay-925bff84-…", "route": "chat", "response": "guidance#2",
    "pendingAction": null,
    "tokenUsage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    "durationMs": 8, "promptVersion": "v1:14cbaab47286",
    "model": "gpt-4.1-mini", "checkpointRowsAdded": 2
  },
  "diff": {"routeChanged": false, "responseChanged": true, "pendingActionChanged": false}
}
```

## 用例与 AC 对应

| 用例 | 断言要点 |
|---|---|
| `test_replay_returns_200_with_camel_case_contract` | AC-1：三段齐全、两侧 `promptVersion` 相等、`durationMs > 0`、`checkpointRowsAdded >= 1`；显式断言**没有** `prompt_version` |
| `test_replay_rejects_unknown_checkpoint_with_404` | AC-4 |
| `test_replay_rejects_terminal_checkpoint_with_409` | AC-4 |
| `test_replay_requires_admin` | AC-6：普通用户 403、匿名 401 |
| `test_replay_degrades_when_checkpoint_store_missing` | AC-6：**404**（非 500），无 `Traceback` |
| `test_replay_keeps_thread_checkpoint_total_unchanged` | AC-2 的 HTTP 视角 |

## 6 维自查（测试代码，简版）

- ✅ **R1**：每用例 < 45 行，建 run 的流程抽成模块级 helper。
- ✅ **R2**：只新增 1 个测试文件。
- ✅ **R3**：`start_chat_run()` / `pick_replayable()` 复用，未重复样板。
- ✅ **R4**：没有为"以后可能"的路径写空用例。
- ✅ **R5**：只通过 HTTP 与公开状态观察，不 patch 内部方法。
- ✅ **R6**：断言名用 `camel_case_contract` / `degrades` / `unchanged` 等行为词。

## 越界检查

```text
✅ TASK 声明的 write_files：
  - backend/tests/test_checkpoint_replay_api.py

✅ 实际 diff 涉及：同 1 个文件（新增）

→ 越界：0
```

## 破坏性变更

**未命中**：纯新增测试。

## 决策与偏离

1. **`tokenUsage` 内层保持 snake_case（`prompt_tokens`）**：`CamelModel` 的 alias 只作用于模型字段，不递归改 dict 内容。核对既有 `/agent/runs/{id}` 的 `token_usage` 同样是原始键名，因此**保持一致**，不自创 `promptTokens`。前端拿到的形状是 `tokenUsage.prompt_tokens`。
2. **降级用例实际是 404 而不是 503**：`checkpoint_sqlite_path` 指向不存在的文件时，`CheckpointRepository._url()` 返回 None、`get()` 返回 None，于是 service 走「不存在」分支。语义上说得通（库没有 → 这个 checkpoint 在这个环境里确实取不到），且满足 AC-6「不 500、不抛栈」。若要区分「库不可用」与「记录不存在」需新增探测，超出本 change 范围，记为已知取舍。
3. **`replay_anchor_ambiguous` 未覆盖**：该分支只在图出现并行边时才可能触发，当前 `START → classify → (respond | prepare | tool_create) → END` 是线性图，构造不出 `parent.next` 长度 > 1 的真实快照。属**已知覆盖缺口**，不是 AC-4 列举的三种拒绝之一。已在 LESSONS L-004 记录锚点语义，后续图结构支持并行时应补这条。

## 是否触发新工作

无（两条已知取舍已在此记录，未超出本 change 的 v1 范围）。

## 完成判定

6 条用例 + 全量 136 passed → **T06 done**。
