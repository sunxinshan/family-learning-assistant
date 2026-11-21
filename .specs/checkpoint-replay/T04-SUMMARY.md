# SUMMARY: T04 - AdminService 编排 + 响应 schema

- **Change ID**: checkpoint-replay
- **Task ID**: T04
- **完成时间**: 2026-11-21 17:34
- **AI 角色**: Dev

---

## 做了什么（一段话）

在 `admin/schemas.py` 补了 `ReplaySourceOut` / `ReplayRunOut` / `ReplayDiffOut` / `CheckpointReplayOut` 四个 `CamelModel`，字段逐一对照 `runtime.replay_from_checkpoint` 的实际返回（source 8 键、replay 9 键、diff 3 键）。在 `AdminService` 加了 `replay_checkpoint()`：先 `checkpoint_repository.get()` 判存在（复用既有 404 文案），再委托 runtime，最后记一条操作日志并组装响应。**没有**实现 TASK 原计划的「取 parent_id → `routing_target` 算锚点」两步 —— 锚点已改为 runtime 内部解析（见 TASK.md「修正 2」），service 只透传四种 409。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/modules/admin/schemas.py` | 修改 | +45/-0：4 个响应模型 |
| `backend/app/modules/admin/service.py` | 修改 | +33/-1：`TYPE_CHECKING` 导入 + `replay_checkpoint()` |

## verify 输出（必填）

```text
$ .venv/bin/ruff check app/modules/admin/service.py app/modules/admin/schemas.py
All checks passed!

$ .venv/bin/ruff format --check app/modules/admin/service.py app/modules/admin/schemas.py
2 files already formatted

$ .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t05 tests/test_admin_checkpoints.py
.....                                                                    [100%]
5 passed in 1.78s
```

契约形状实测（确保前端拿到的是 camelCase，不是 snake）：

```text
source : ['threadId','checkpointId','step','next','route','response','pendingAction','promptVersion']
replay : ['threadId','route','response','pendingAction','tokenUsage','durationMs','promptVersion','model','checkpointRowsAdded']
```

## 6 维自查（生产代码改动必填 · 来自 4-dev 步骤 4）

- ✅ **R1 认知过载**：`replay_checkpoint` 12 行，线性三句。
- ✅ **R2 变更传播**：只改 service/schemas，未动 router（T05）、未动 runtime。
- ✅ **R3 知识重复**：404 文案复用既有 `get_checkpoint` 的那句，未另造。
- ✅ **R4 偶然复杂**：没有在 service 里重复实现 anchor / terminal / interrupted 判断 —— 那些留在 runtime，避免两处逻辑漂移。
- ✅ **R5 依赖混乱**：用 `TYPE_CHECKING` + 字符串前向引用引入 `AgentRuntime`，运行期不 import，避免把 graph/llm 重依赖拉进 admin 的导入链（`admin` 已经 import 了 `agent.redaction`，不能再加深）。
- ✅ **R6 领域扭曲**：`replay_checkpoint` / `source` / `diff` 均为领域词。

## 越界检查（必填 · 来自 4-dev 步骤 5 / R6.5）

```text
✅ TASK 声明的 write_files：
  - backend/app/modules/admin/service.py
  - backend/app/modules/admin/schemas.py

✅ 实际 diff 涉及：同样 2 个文件（+78/-1）

→ 越界：0
```

## 破坏性变更

**未命中**：`AdminService.__init__` 签名未变（`agent_runtime` 是方法参数），既有 fixture 不受影响。

## 决策与偏离（如有）

1. **不实现「取 parent_id → routing_target」两步**：锚点改由 runtime 自解（TASK.md「修正 2」），service 少两条分支，也少一处与 runtime 语义漂移的风险。
2. **`agent_runtime: "AgentRuntime"` 用 `TYPE_CHECKING`**：兼顾类型可读性与零运行期依赖。
3. **唯一的写入是操作日志**：`self.log(admin_id, "重放 checkpoint", "checkpoint", checkpoint_id, thread_id)`，落 admin 的 `operation_logs`，不碰业务表与 agent 表，符合 AC-3。

## 是否触发新工作

无。

## 完成判定

verify 全绿，camelCase 实测正确，既有 admin 用例不回归 → **T04 done**。
