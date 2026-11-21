# SUMMARY: T05 - 新增重放端点

- **Change ID**: checkpoint-replay
- **Task ID**: T05
- **完成时间**: 2026-11-21 17:36
- **AI 角色**: Dev

---

## 做了什么（一段话）

在 `admin/router.py` 追加 `POST /admin/checkpoints/{thread_id}/{checkpoint_id}/replay`，`require_admin` 鉴权，从 `request.app.state.agent_runtime` 取运行时，把所有逻辑转给 `service.replay_checkpoint()`。端点本身 10 行，是纯薄壳。路由放在既有 `GET .../{thread_id}/{checkpoint_id}` 之后，避免匹配顺序冲突。

## 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/modules/admin/router.py` | 修改 | +19/-0：导入 `CheckpointReplayOut` + 新端点 |

## verify 输出（必填）

```text
$ .venv/bin/ruff check app/modules/admin/router.py
All checks passed!

$ .venv/bin/ruff format --check app/modules/admin/router.py
1 file already formatted

$ .venv/bin/python -c "app.openapi()['paths'] 里含 replay 的路径"
replay route: ['/api/v1/admin/checkpoints/{thread_id}/{checkpoint_id}/replay']
methods: ['post']

$ .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t05 tests/test_admin_checkpoints.py
.....                                                                    [100%]
5 passed in 1.78s
```

端点确实进了 OpenAPI（不是只写了函数没挂上），且既有 admin 路由未回归。

## 6 维自查

- ✅ **R1**：10 行。
- ✅ **R2**：只改 router.py。
- ✅ **R3**：无重复逻辑，全部委托 service。
- ✅ **R4**：没有加 query 参数、没有加开关。
- ✅ **R5**：依赖方向 admin → agent 只通过 `app.state` 取运行时，没有 import。
- ✅ **R6**：`replay_checkpoint` 命名与既有 `get_checkpoint` 对齐。

## 越界检查

```text
✅ TASK 声明的 write_files：
  - backend/app/modules/admin/router.py

✅ 实际 diff 涉及：同 1 个文件（+19/-0）

→ 越界：0
```

## 破坏性变更

**未命中**：只新增路由，既有 5 个端点未动。

## 决策与偏离

无。端点内不做任何业务判断，与既有 4 个 admin 端点风格一致。

## 是否触发新工作

无。

## 完成判定

OpenAPI 里能看到该路径、方法为 POST、既有用例全绿 → **T05 done**。
