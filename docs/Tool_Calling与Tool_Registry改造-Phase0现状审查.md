# Tool Calling 与 Tool Registry 改造 · Phase 0 现状审查

**审查日期：** 2026-11-05
**代码基线：** `b093d7c`（本地 `main`）
**对应文档：** `Tool_Calling与Tool_Registry改造设计文档_V1.1`
**审查范围：** `backend/app/modules/agent/`、`conversation`、`main.py`、`frontend/src` 消息模型与 SSE
**约束：** 本阶段只审查、不修改业务逻辑。除本文档外无代码改动。

---

## 1. 结论摘要

| 结论 | 说明 |
| --- | --- |
| 意图识别入口存在且可保留 | 单节点 `classify`，输出 8 种 route，位置正确 |
| 能力指引兜底已实现 | 文档中的"固定字符串"描述已过时；当前已读取 `capability_guide.md` 调用 LLM |
| 意图识别成功后的处理 **不是 Workflow** | 只有一个 `prepare` 节点，内部全是 Python 正则解析，属于文档要替换的对象 |
| Tool Registry 未接入运行链路 | 仅在 `runs/{id}/details` 展示字段和单测中出现；`invoke()` 生产零调用 |
| LLM Adapter 不支持原生 Tool Calling | 无 `tools`/`tool_choice` 参数，无 `tool_calls` 解析，无 tool 消息回传 |
| 消息/SSE 已有部分工具承载能力 | `conversation_messages.tool_call_id` 字段已存在但未使用；前端已支持 `tool_status` 与执行卡片，后端从未发送 |
| 核心结构障碍 | `AgentBusinessService` 同时承担文本解析、预览构造、Service 编排、Repository 构造，Handler 无法直接复用 |

**总体判断：** 目标架构与现状差距较大，但入口、确认协议、Service 边界、消息与前端承载点都已具备，可以按 Phase 1 做单场景闭环，不需要推倒重来。

---

## 2. 实际端到端链路

```text
POST /api/v1/agent/runs/stream                    router.py:26
  └─ AgentRuntime.start_run                        runtime.py:364
       ├─ 创建 agent_run（status=running, lease 2min）
       ├─ 写入 user 消息                             runtime.py:406
       └─ 后台线程 _execute_new_run                  runtime.py:281（全局 _execution_lock）
            └─ graph.invoke(state)                  runtime.py:300
                 ├─ classify                        runtime.py:57
                 │    └─ llm.classify_intent        llm.py:300
                 ├─ prepare                         runtime.py:79
                 │    └─ _prepare_task_action / AgentBusinessService.prepare_*
                 │         └─ 正则解析原始文本 + 读 Service + 拼装 pending_action
                 ├─ wait_for_confirmation           runtime.py:111（LangGraph interrupt）
                 └─ respond                         runtime.py:93（learning 或能力引导兜底）
            └─ 读取 graph state，写 assistant 消息、SSE message/confirmation_required/done

POST /api/v1/agent/actions/{run_id}/confirm       router.py:141
  └─ start_confirm → _execute_confirm              runtime.py:481
       └─ graph.invoke(Command(resume=...))        runtime.py:496
            └─ wait 节点继续 → business.execute    service.py:563
                 └─ TaskService / VocabularyService / ContentService
```

关键事实：

- 每个 run 都会把完整 `text` 交给 `classify`，但**不携带历史消息**；多轮上下文只存在于 checkpoint 的 state，不进入 LLM 请求。
- 意图识别成功后没有独立 Workflow/Subgraph，`prepare` 一个节点覆盖 5 种业务路由。
- 预览阶段只读 Service，不写业务数据；正式写入只发生在确认后的 `wait` 节点 → `execute`。

---

## 3. 意图识别入口、Prompt、输出与路由

### 3.1 入口与输出

- 图节点：`classify`（`runtime.py:57`），调用 `llm.classify_intent(state["text"])`。
- 输出结构：`{"route": str, "source": "llm"|"mock", "usage": {...}, ...}`。
- 路由白名单（`runtime.py:66-76`）：`task_create`、`task_update`、`task_delete`、`vocabulary_create`、`vocabulary_import`、`learning`、`chat`、`unclear`；未知值统一降级为 `unclear`。
- 路由分支（`runtime.py:148-159`）：5 种业务路由 → `prepare`；`learning` / `chat` / `unclear` → `respond`。

### 3.2 Prompt 来源（存在不一致）

- 真正决定分类结果的是 `OpenAICompatibleAdapter.classify_intent` 里**硬编码的英文 system prompt**（`llm.py:300-308`）。
- `backend/app/modules/agent/prompts/main_agent.txt` **没有参与分类**，只在 `AgentRuntime.__init__` 加载（`runtime.py:194`），用于写 `run.prompt_version`（`runtime.py:401`）。
- 因此执行详情里的 `prompt_version` 记录的不是本次分类实际使用的 Prompt，排障时会产生误导。
- Mock 适配器用关键词规则模拟分类（`llm.py:80`），仅用于测试/本地。

### 3.3 与目标的一致性

| 目标 | 现状 | 结论 |
| --- | --- | --- |
| 意图识别是第一步 | 是 | 一致 |
| 输出稳定业务路由 | 是，8 种 route | 一致 |
| 不拼装领域对象 | 是，只返回 route | 一致 |
| 不承担参数抽取 | 是 | 一致（参数抽取在下一步） |
| 可观测的 Prompt 版本 | 记录的是未使用的 `main_agent` | **不一致，需修正** |

---

## 4. 意图识别失败与能力指引兜底

- 触发：`route ∈ {chat, unclear}` 进入 `respond`（`runtime.py:93`）。
- 实现：`FallbackGuidanceService.respond`（`guidance.py:38`）：
  1. `PromptRegistry.get_document("capability_guide")` 读取 `backend/app/modules/agent/prompts/capability_guide.md`（`prompt_registry.py:49`）；
  2. 注入 `fallback_guidance.txt` 的 `{capability_guide}` 变量；
  3. 以用户原始输入作为 user message 调用 `llm.generate_guidance`（纯文本模式，`llm.py:297`）；
  4. 返回普通 assistant 文本，不调用 Registry、不执行业务、不写数据。
- 失败降级：Guide 缺失 / Prompt 缺失 / LLM 异常 / 空响应 → `FALLBACK_GUIDANCE_TEXT`（`guidance.py:18`），run 仍 `completed`；日志前缀 `app.agent.guidance`。
- 生产路径：`FLA_PROMPT_DIR=/opt/project2/app-v2/backend/app/modules/agent/prompts`，依赖 `app-v2` 软链接。
- 覆盖测试：`tests/test_agent_fallback_guidance.py`（11 条），包括"不写业务数据""LLM 失败仍可继续"。

**结论：** 与目标第 3.2 节一致，且已优于设计文档中"返回固定字符串"的描述；文档第 2.6 条已过时，Phase 0 报告中应以此为准。此路径后续不需要 Tool Calling。

---

## 5. 当前 Python 文本解析与 Task 拼装链路

全部位于 `backend/app/modules/agent/service.py`，由 `prepare` 节点按 route 调用。

| 位置 | 函数 | 职责 | 解析方式 |
| --- | --- | --- | --- |
| `service.py:55` | `_quoted` | 提取「」/“”/"" 中的名称 | 正则 |
| `service.py:60` | `_parse_selected_ids` | 全部 / 前 N 个 / 序号 / 区间 | 关键词 + 正则 |
| `service.py:93` | `_prepare_task_action` | 选词库、选词条、听写参数、命名、模式 | 正则 + 关键词 |
| `service.py:173` | `_update_changes_from_text` | 分组数、播放方式、间隔、朗读次数、提示、强制重做、改名、任务模式 | 正则 + 关键词 |
| `service.py:293` | `_parse_tags` | 标签解析 | 正则 |
| `service.py:316` | `_find_task` | 按名称/状态选任务 | 名称匹配 |
| `service.py:326` | `prepare_task_update` | 组装修改预览 | 调上面的解析 |
| `service.py:358` | `prepare_task_delete` | 组装删除预览 | 调 `_find_task` |
| `service.py:374` | `prepare_vocabulary_create` | 学科、名称、标签 | 关键词/正则 |
| `service.py:411` | `prepare_vocabulary_import` | 学科判断 + 解析文件 | 关键词 + ContentService |

典型的隐式规则（都是文档要求迁移的对象）：

- `task_create`：`"长期"` 才建长期任务，否则固定任务；`wordsPerGroup` 固定 `min(5, 已选数)`；`"强制"` 才开强制重做；`"线下听写"`、`"自动播放"`、`"间隔N秒"`、`"朗读N次"`、`"中文/释义"` 决定听写参数。
- `task_update`：`"每题/每组 N 个"`、`"改名为「」"`、`"长期任务"`/`"固定任务"` 等通过正则改配置。
- 名称缺省：`f"{library.name} · 听写"`；词库缺省：第一个可用词库；任务缺省：进行中的第一个任务。
- 创建时若未指定词条，`selectedEntryIds=[]`，预览可生成但确认会被 Service 拒绝（`no_entries_selected`）。

**结构问题：** `AgentBusinessService` 同时是「文本解析器 + 预览构造器 + Service 编排器 + Repository 构造器」。例如 `prepare_vocabulary_import` 直接 `ContentRepository(...)` / `MaterialRepository(...)` / `VocabularyRepository(...)`（`service.py:421-423`），与目标架构"Handler 不直接访问 Repository"冲突。

---

## 6. Tool Registry 现状

定义：`backend/app/modules/agent/tools.py`。

### 6.1 定义结构

```python
ToolDefinition(name, label, required_role, handler)
ToolResult(ok, value, error_code, error_message)
```

缺少 `description`、`args_schema`、场景/Workflow 标签、风险与确认元数据。

### 6.2 注册的 7 个工具与真实行为

| 工具 | required_role | 当前 handler 实际行为 | 与名称是否一致 |
| --- | --- | --- | --- |
| `learning.stats` | user | `business.learning_stats_text(user_id)`，真实只读统计 | 一致 |
| `task.create_preview` | user | 返回 `[task.id ...]`（`available_tasks`） | **不一致（占位）** |
| `task.update_preview` | user | 同上，返回任务 ID 列表 | **不一致（占位）** |
| `task.delete_preview` | user | 同上，返回任务 ID 列表 | **不一致（占位）** |
| `vocabulary.create_preview` | user | 返回 `[vocabulary.id ...]` | **不一致（占位）** |
| `vocabulary.import_preview` | user | 返回 `[vocabulary.id ...]` | **不一致（占位）** |
| `admin.execution_detail` | admin | 返回常量 `{"scope": "admin"}` | **不一致（占位）** |

### 6.3 使用位置

- `router.py:94`：`GET /agent/runs/{id}/details` 把 `available(role)` 写入 `available_tools` 字段（`schemas.py:39`）。
- 前端**没有调用**该详情接口；该字段目前只有测试断言（`test_agent_infrastructure.py:159`）。
- `invoke()`（`tools.py:82`）只出现在单元测试 `test_tool_registry_permission_filtering`，生产链路零调用。
- 未传入 `AgentRuntime`，未传入 LLM Adapter，未参与图执行。

### 6.4 权限

- `available(role)`：`required_role == "user" or role == "admin"`，只有 admin 能看到管理员工具。
- `invoke()` 再判一次 admin。
- 没有场景过滤，没有 Schema 校验，没有可信身份注入（`user_id` 由调用方传入）。

---

## 7. LLM Adapter 与原生 Tool Calling

`backend/app/modules/agent/llm.py`：

- 协议 `LLMAdapter`：`classify_intent`、`analyze_headers`、`generate_guidance`（`llm.py:14-19`）。
- 两个实现：`MockLLMAdapter`（规则模拟）、`OpenAICompatibleAdapter`（DeepSeek/OpenAI 兼容）。
- 底层统一 `_chat(system, user, json_mode)`（`llm.py:224`）：
  - 只发送 `messages=[system, user]`；
  - `json_mode=True` 时带 `response_format={"type":"json_object"}`，否则纯文本、temperature 0.4；
  - **没有 `tools`、`tool_choice`、`parallel_tool_calls` 参数**；
  - **不解析 `choices[0].message.tool_calls`**；
  - **不支持 `role="tool"` 消息回传**；
  - 不支持多轮 tool 循环。
- 已有的错误映射：429 / 5xx / 超时 / 非法 JSON，最多 3 次退避重试。
- 模型：生产 `deepseek-v4-flash`（`FLA_LLM_MODEL`），Provider 是否支持原生 function calling 尚未在项目中验证。

---

## 8. Workflow / Subgraph 组织方式

- 单一 `StateGraph(AgentState)`，在 `build_agent_graph` 内联构造（`runtime.py:167-179`）。
- 节点：`classify`、`prepare`、`respond`、`wait`；没有 Subgraph，没有 `ToolNode`，没有循环工具节点。
- 边：`START → classify → (prepare | respond)`；`prepare → wait | END`；`wait → wait | END`；`respond → END`。
- 确认：`interrupt()` + `Command(resume=...)`（`runtime.py:115`、`runtime.py:496`）；两阶段删除在 `wait` 内再 `interrupt` 一次。
- Checkpointer：`thread_id = conversation_id`，因此同一会话的图状态跨 run 持久化，但 `AgentState`（`service.py:34-48`）只有 `text/route/response/pending_action/draft_version/config_hash/token_usage/links/material_id`，**没有 messages 或 tool_calls**。
- 执行并发：`AgentRuntime._execution_lock`（`runtime.py:300`）是进程级全局锁，所有会话串行；当前按单 worker 运行。

---

## 9. 消息、SSE 与前端承载能力

### 9.1 已有基础

- `conversation_messages.message_type`（`conversation/models.py:33`）是自由字符串，已有 `tool_call_id` 字段（`:35`）。
- `ConversationService.append_message` 已支持 `tool_call_id` 参数（`service.py:36`），但所有调用方都没传。
- `AgentRunEvent.event_type` 也是自由字符串（`agent/models.py:33`）。
- 前端 `ChatMessageKind` 已包含 `execution`，`AgentEvent` 已包含 `{type:"tool_status"}`（`types/domain.ts:231-287`），`MessageComponents` 有 `ExecutionCard` 可展开参数/结果。

### 9.2 当前实际

- 后端只写 `role=user/assistant` 的文本消息（`runtime.py:246`、`:406`、`:512`），没有 `tool_call` / `tool_result` 消息。
- 后端 SSE 只发 `progress`、`message`、`confirmation_required`、`error`、`done`；**从未发送 `tool_status`**（全仓 grep 仅前端 mock 有）。
- 因此"工具执行卡片"目前只是前端预留能力，真实后端无数据。

---

## 10. 与目标架构的差距矩阵

| 目标要求 | 现状 | 结论 | 需要动作 |
| --- | --- | --- | --- |
| 保留意图识别并路由 | classify + route | ✅ 一致 | 保留 |
| 失败走能力指引 | 已实现 | ✅ 一致（优于文档） | 保留 |
| 成功后进入 Workflow/Subgraph | 单个 prepare 节点 + 正则 | ⚠️ 部分 | 新增场景 Workflow/工具节点 |
| 场景内受限工具集 | 无场景概念 | ❌ 缺失 | Registry 增加 workflow 标签与过滤 |
| LLM 原生 Tool Calling | 无 tools 参数/解析 | ❌ 缺失 | Adapter 增加 tool 调用与回传 |
| Executor 校验/权限/身份注入 | 无 | ❌ 缺失 | 新增 Executor |
| Tool Result 回传 | 无 | ❌ 缺失 | 消息模型 + Adapter 循环 |
| Tool Call/Result 持久化 | 字段有、未用 | ⚠️ 部分 | 复用 `tool_call_id`，补 message_type |
| Tool Definition 完整性 | 仅 name/label/role/handler | ❌ 缺失 | 增加 description/args_schema/scene |
| Handler 委托 Service | 7 个中 6 个占位 | ❌ 不一致 | 重写真实 handler |
| Service 是业务唯一入口 | 确认后 execute 走 Service | ✅ 一致 | 保持 |
| 不直连 Repository | AgentBusinessService 构造 Repository | ❌ 不一致 | Handler 改为注入 Service/门面 |
| 预览→确认→执行边界 | interrupt + 版本/哈希校验 | ✅ 一致 | 保持 |
| 可观测 Prompt 版本 | 记录的是未使用的 main_agent | ⚠️ 问题 | Phase 1 修正 |
| 单 worker/串行执行 | 全局锁 | ⚠️ 限制 | Phase 1 评估 |

---

## 11. 文档假设与代码的差异

1. **设计文档 2.6 / 3.2** 说"意图识别失败返回固定字符串"——已在 `d0d4004` 改为 capability guide + LLM，本文档描述过时。
2. **设计文档 2.2 / 2.5** 说 Registry 未接入——仍然成立，且 6 个 handler 是占位，不只是"未接入"。
3. **设计文档 5.1** 说 ToolDefinition 只有 4 个字段——准确。
4. **设计文档 9** 说 Python 逐句解析——准确，且集中在 `service.py` 的 9 个函数。
5. **设计文档第 8 节**列出的工具名与现有 Registry 名称一致，但 handler 行为与名称严重不符。
6. **设计文档提到的 `task.create` 路由**：实际 route 是 `task_create`（下划线），不是 `task.create`；Phase 1 不要照抄文档里的命名。

---

## 12. Phase 1 建议的最小闭环（待确认后实施）

### 12.1 场景选择

建议先做 **`task.create_preview`**，理由：

- 同时覆盖"自然语言 → 结构化参数 → 权限/业务校验 → 预览 → 确认"完整链路；
- 现有确认协议（`action_id + draft_version + config_hash`）可直接复用；
- 比 `learning.stats` 更能证明参数抽取能力，又比导入词库少文件依赖。

`learning.stats` 可作为第二个零参数工具，验证工具集合过滤。

### 12.2 最小改动清单（建议）

1. **Registry**
   - `ToolDefinition` 增加 `description`、`args_schema`（Pydantic）、`workflows: frozenset[str]`；
   - 增加 `get(name)`、`for_workflow(role, workflow)`、`to_openai_tools(...)`；
   - 移除 `invoke()` 或保留为 Executor 内部调用，不作为 LLM 入口。
2. **Executor（新文件）**
   - 查找 → 角色校验 → Pydantic 校验 → 注入 `user_id/role` → 调 handler → 统一 `ToolResult`；
   - 错误码：`tool_not_found` / `forbidden` / `invalid_arguments` / `business_error` / `tool_execution_error`。
3. **LLM Adapter**
   - 新增 `chat_with_tools(messages, tools, ...)`，解析 `message.tool_calls`；
   - 支持 `role="tool"` 回传，最多 N 轮工具循环；
   - Mock 适配器支持脚本化的 tool_calls，保证确定性测试。
4. **Workflow**
   - 在 `build_agent_graph` 中新增 `task_create` 分支/子图：构建受限工具集 → LLM tool call → Executor → 预览 → `wait`；
   - 保留 `classify`、`respond`/能力指引、确认与取消路径不变。
5. **Handler**
   - 新增 `AgentBusinessService.build_task_preview(user_id, args)`，只接受结构化参数并组装 `_build_task_create_action`；
   - 不再读取原始 `text`；正则解析暂不作为静默兜底，若需灰度则用显式开关 + 日志。
   - 把 Repository 构造收敛到模块 Service 或注入的工厂，避免 Handler 直连 Repository。
6. **持久化与 UI**
   - 写 `tool_call` / `tool_result` 消息（复用 `tool_call_id`），发 `tool_status` SSE；
   - 前端 `ExecutionCard` 已有，只需确认字段对齐。
7. **可观测性**
   - 修正 `prompt_version`：记录实际使用的分类 Prompt 哈希；
   - 日志记录 `tool_name`、`tool_call_id`、`workflow`、耗时、结果码。

### 12.3 风险

- DeepSeek 兼容接口的原生 tool calling 未验证；需要先做一次真实请求探测（工具定义、`tool_choice`、并行调用）。
- 现有 `AgentBusinessService` 职责过重，Handler 复用前需要先拆分，否则 Phase 1 会引入新的耦合。
- 工具循环与 `_execution_lock` 串行叠加，需限制最大轮次与超时，避免一次请求长时间占用全局锁。
- 预览 payload 已有历史大字段问题（交接文档记录过 30 万字符），Tool Result 持久化要控制大小并做截断。
- 不能删除旧正则解析直到新路径通过等价性测试；切换需要显式开关和回滚方式。

### 12.4 Phase 1 验收测试建议

- Registry：按 workflow/role 过滤、未注册工具、OpenAI 工具格式转换。
- Executor：合法/非法参数、越权、身份注入、Handler 异常、结果结构。
- Mock LLM 集成：意图识别 → 工具调用 → Executor → 预览 → 确认 → Service 创建。
- 反向用例：意图失败不调用工具；缺少参数先追问；取消不写数据；重复确认幂等。
- 真实 LLM 冒烟：一句自然语言创建任务，核对预览字段与最终任务。

---

## 13. 当前测试覆盖（与本改造相关）

| 文件 | 覆盖内容 | 与 Tool Calling 的关系 |
| --- | --- | --- |
| `tests/test_agent_workflows.py`（13 条） | 创建/修改/删除/词库导入、确认、取消、重放、跨用户 | 现有正则链路回归基线 |
| `tests/test_agent_infrastructure.py`（7 条） | 适配器重试、Prompt、Registry 权限、详情脱敏 | Registry 仅测 `available`/`invoke` |
| `tests/test_agent_fallback_guidance.py`（11 条） | 能力引导、失败降级、不写数据 | 验证兜底路径 |
| `tests/test_agent_active_run.py`（1 条） | 大 pending action 恢复 | 确认协议 |

目前**没有** Executor、原生 tool call、tool 消息持久化、场景过滤的测试。

---

## 14. 下一步

Phase 0 完成，未修改业务代码。建议按第 12 节实施 Phase 1 的 `task.create_preview` 闭环；实施前需确认：

1. 是否接受"旧正则路径暂时保留但由显式开关控制"的灰度方式；
2. 是否先做 DeepSeek 原生 tool calling 探测；
3. Phase 1 是否同时补消息持久化与前端 `tool_status`，还是先用 Graph state 传递结果。

未确认前不进入编码。
