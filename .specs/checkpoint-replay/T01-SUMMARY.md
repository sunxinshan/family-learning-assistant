# SUMMARY: T01 - CheckpointRepository 增加锚点解析与 thread 计数

- **Change ID**: checkpoint-replay
- **Task ID**: T01
- **完成时间**: 2026-11-21 17:26
- **AI 角色**: Dev

---

## 做了什么（一段话）

在 `CheckpointRepository` 上新增 `routing_target()` 与 `count_thread()`，沿用文件既有的 `_url()` + `_engine_for()` + `SQLAlchemyError` 降级风格，不建新引擎、不建新类。`routing_target` 查 `writes` 表 `branch:to:%` 命中的唯一目标，0 条返回 None、多条返回 None 并记 warning。`count_thread` 返回该 thread 在 `checkpoints` 的行数，库不可用返回 0。

**命名与定位有变化（实测驱动）**：TASK 里叫 `producing_node`，实现时发现它返回的其实是「下一跳」而非「产出节点」（证据见下）。名字会直接诱导后来者拿它当 `as_node` 锚点，踩同一个坑，因此改名为 `routing_target` 并在 docstring 里写死这个区别。它**不进入重放链路**，只作管理页诊断用。

## 关键实测：`branch:to` 是「下一跳」不是「产出节点」

a→b 两节点图跑完后（临时 SQLite，langgraph 1.2.19）：

```
mid          next=('b',)  values={'text':'a'}      ← 由节点 a 产出
mid.parent   branch:to 目标 = 'b'                  ← 按 parent 查得到的是「下一跳」
mid.parent   next = ('a',)                         ← 真正的产出节点
grandparent  branch:to 目标 = 'a'
```

这个结论直接导致 T02 放弃「由 admin 传 anchor」的方案，改为 runtime 内部读父快照的 `next` 解析锚点。完整影响面见 `T02-SUMMARY.md`「决策与偏离」第 1 条与 `TASK.md`「修正 1」。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/modules/admin/checkpoint_repository.py` | 修改 | +67/-0：新增 `routing_target()` / `count_thread()` 与注释段 |
| `backend/tests/test_checkpoint_anchor_repository.py` | 新增 | 6 个用例，真 SqliteSaver 落文件 |

## verify 输出（必填）

```text
$ .venv/bin/ruff check app/modules/admin/checkpoint_repository.py tests/test_checkpoint_anchor_repository.py
All checks passed!

$ .venv/bin/ruff format --check app/modules/admin/checkpoint_repository.py tests/test_checkpoint_anchor_repository.py
2 files already formatted

$ .venv/bin/pytest -q --basetemp=/tmp/fla-verify-t01b tests/test_checkpoint_anchor_repository.py
......                                                                   [100%]
6 passed in 0.16s

$ .venv/bin/pytest -q --basetemp=/tmp/fla-wave1            # Wave 1 合并后全量
122 passed in 29.60s
```

6 个用例覆盖：

| 断言 | 证明 |
|---|---|
| `routing_target(thread, parent_id) == "b"` 且 `(grandparent_id) == "a"` | 明确把「下一跳」与「产出节点」区分开，防止误用 |
| 无 `branch:to` 写入的 checkpoint → None | 终点/无分支安全返回 |
| 单条 `checkpoint_id` 有多条 branch（`branch:to:b` / `branch:to:c`）→ None + warning | 并行分支安全失败，不猜 |
| `count_thread` 与 `select count(*)` 交叉验证 | 不硬编码数字 |
| 未知 thread → 0 | 降级 |
| `checkpoint_sqlite_path` 指向不存在文件 → None / 0 且不抛 | AC-6 的降级要求 |

## 6 维自查（生产代码改动必填 · 来自 4-dev 步骤 4）

> 未装 brooks-lint，走内置 R1~R6 快查。

- ✅ **R1 认知过载**：两个方法分别 47 行 / 17 行，无嵌套深于 2 层。
- ✅ **R2 变更传播**：只改 `checkpoint_repository.py` + 新增一个测试文件。
- ✅ **R3 知识重复**：连接与降级逻辑复用文件原有的 `_url()` / `_engine_for()` / `SQLAlchemyError` 分支，未复制粘贴。
- ✅ **R4 偶然复杂**：没有加"将来可能用"的参数；多条分支只记 warning 不引入重试。
- ✅ **R5 依赖混乱**：repository 属于 admin 层，读取的是 checkpoint 库，未反向 import agent 业务服务。
- ✅ **R6 领域扭曲**：`routing_target` / `count_thread` 均为领域动作词；弃用 `producing_node` 正是因为它在语义上是错的。

## 越界检查（必填 · 来自 4-dev 步骤 5 / R6.5）

```text
✅ TASK 声明的 write_files：
  - backend/app/modules/admin/checkpoint_repository.py
  - backend/tests/test_checkpoint_anchor_repository.py

✅ 实际 diff 涉及：
  - backend/app/modules/admin/checkpoint_repository.py（+67/-0）
  - backend/tests/test_checkpoint_anchor_repository.py（新增）

→ 越界：0
```

改名时 grep 过全库：`routing_target`（原 `producing_node`）只在上述两个文件出现，无其它调用点需要同步。

## 破坏性变更（涉及破坏性改动必填 · 来自 4-dev 步骤 1.8）

**未命中**：纯新增方法。改名发生在同一任务内的新代码上，无外部调用者（grep 已确认）。

## 决策与偏离（如有）

1. **`producing_node` → `routing_target`**：TASK 的命名基于一个错误假设（认为 `branch:to` 指向产出节点）。实测证伪后，保留原名等于把陷阱留在代码库里。改名 + docstring 显式警告，成本极低。
2. **`count_thread` 未被 runtime 使用**：T02 改用 `get_state_history` 计数，避免 agent → admin 反向依赖。此方法留给 admin 侧响应组装（`checkpoint_rows_added` 若需要跨 thread 统计时可用），当前无调用者，属**已知小问题 🟢**，不删的理由是它同时被测试用作 `routing_target` 的交叉验证工具；若 A-evolve 认为冗余可移除。

## 是否触发新工作

**是，一条**：DESIGN §2.3 与 §9.1 需修订（`producing_node` 的取法 off-by-one）。未擅自改 DESIGN（R3.2），已记入 `TASK.md`「与设计的偏离」并需用户批准。

## 完成判定

verify 全绿（ruff + 6 passed + 全量 122 passed），6 条断言覆盖返回值/降级/歧义 → **T01 done**。
