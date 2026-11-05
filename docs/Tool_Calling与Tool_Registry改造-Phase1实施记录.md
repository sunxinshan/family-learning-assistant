# Tool Calling 与 Tool Registry 改造 · Phase 1 实施记录

**实施日期：** 2026-11-05
**代码基线：** Phase 0 审查提交之后
**对应文档：** `Tool_Calling与Tool_Registry改造设计文档_V1.1`
**范围：** `task_create` 场景的原生 Tool Calling 最小闭环
**灰度开关：** `FLA_AGENT_TOOL_CALLING_ENABLED`，默认 `false`

---

## 1. 本阶段完成内容

- 意图识别、能力指引兜底、确认/取消协议保持不变。
- 开关开启时，`task_create` 路由不再进入正则解析，改为：
  1. 构建当前场景的受限工具集（仅 `task.create_preview`）；
  2. 把可用词库和工具定义交给 LLM；
  3. LLM 通过 Provider 原生 Tool Calling 返回结构化参数；
  4. Executor 做工具查找、权限、Schema、身份注入和错误归一；
  5. Handler 委托 `AgentBusinessService` 生成任务预览；
  6. 写 Tool Call / Tool Result 消息并发送 `tool_status`；
  7. 复用原有 `interrupt` 确认流程，确认后仍由 Workflow Node 调 Service 正式创建。
- 开关关闭时，保留原有 Python 正则链路，行为与当前生产一致。

## 2. 实际链路

```text
POST /agent/runs/stream
  └─ classify（不变）
       ├─ chat / unclear → capability guide 兜底（不变）
       └─ task_create + 开关开启
            └─ tool_create 节点
                 ├─ TaskCreateToolWorkflow.run
                 │    ├─ 读可用词库
                 │    ├─ Registry.to_openai_tools(role, "task_create")
                 │    ├─ LLM.chat_with_tools(messages, tools)
                 │    ├─ ToolExecutor.execute(name, args, context)
                 │    │     ├─ Registry.get
                 │    │     ├─ 角色 / workflow 校验
                 │    │     ├─ Pydantic Schema 校验
                 │    │     ├─ 注入 user_id / role / run_id
                 │    │     └─ Handler → AgentBusinessService.build_task_create_preview
                 │    └─ 返回 pending_action + tool_trace
                 └─ wait（interrupt，原确认协议）
                      └─ 用户确认 → business.execute → TaskService.create
```

## 3. 文件清单

| 文件 | 说明 |
| --- | --- |
| `backend/app/modules/agent/tool_schemas.py` | 新增，工具参数 Schema（`TaskCreatePreviewArgs` / `EmptyArgs`），禁止额外字段 |
| `backend/app/modules/agent/tools.py` | 重写 Registry：description、args_schema、workflow、LLM 名称映射、场景/角色过滤 |
| `backend/app/modules/agent/executor.py` | 新增，统一校验与执行 |
| `backend/app/modules/agent/tool_workflow.py` | 新增，task_create 原生 Tool Calling 流程 |
| `backend/app/modules/agent/prompts/task_create_tools.txt` | 新增，场景 Prompt（注入词库清单） |
| `backend/app/modules/agent/llm.py` | 新增 `chat_with_tools`，解析 `tool_calls`；抽取 `_post` 复用重试 |
| `backend/app/modules/agent/service.py` | 新增 `build_task_create_preview` 与结构化选择解析 |
| `backend/app/modules/agent/runtime.py` | 新增 `tool_create` 节点、工具消息持久化、`tool_status` 事件 |
| `backend/app/main.py` | `create_app` 支持注入 LLM，便于确定性测试 |
| `backend/app/core/config.py` | 新增 `agent_tool_calling_enabled` |
| `frontend/src/types/domain.ts` | 消息类型增加 `tool_call` |
| `frontend/src/features/conversation/MessageComponents.tsx` | 隐藏原始 `tool_call` 消息，只渲染 `tool_result` 执行卡片 |
| `tests/test_tool_executor.py` | 新增 8 条 Executor/Registry 单测 |
| `tests/test_tool_calling_phase1.py` | 新增 4 条端到端测试 |
| `tests/test_agent_infrastructure.py` | 更新 Registry 测试 |

## 4. Provider 兼容性结论

真实 DeepSeek 探测（`deepseek-v4-flash`）：

- 支持 OpenAI 兼容的 `tools` + `tool_choice=auto`，会返回 `tool_calls`。
- **函数名不允许点号**：`^[a-zA-Z0-9_-]+$`，`task.create_preview` 会直接 400。
- 处理方式：内部名称保持 `task.create_preview`，Registry 暴露给 Provider 时转为 `task_create_preview`；Executor 两种名称都能查找，日志与 UI 使用内部名称。

## 5. Schema 与选择方式

`TaskCreatePreviewArgs` 为扁平结构，避免嵌套 `$defs` 在部分 Provider 上的兼容问题：

- 任务：`name`、`library_id`、`task_mode`、`words_per_group`、`repeat_until_correct`
- 选择：`selection_mode`（`all` / `prefix` / `range` / `ids`）+ `prefix_count` / `range_start` / `range_end` / `entry_ids`
- 听写：`dictation_mode`、`playback_mode`、`interval_seconds`、`hint`、`repeat_count`、`speech_enabled`

Handler 只做确定性解析：

- `all`：全部词条；
- `prefix`：前 N 个，超出长度自动截断；
- `range`：按 1-based 序号切片；
- `ids`：校验全部属于该词库，去重保序；
- 空选择抛 `no_entries_selected`；
- `words_per_group` 在长期任务中限制在 `1..已选数量`，固定任务忽略；
- 语文词库强制 `hint=phonetic`。

## 6. 安全与边界

- `user_id`、`role`、`run_id` 由 Executor 从后端上下文注入，Schema 中不存在这些字段，且 `extra="forbid"` 会拒绝模型传入。
- Executor 每次执行都重新校验角色和 workflow；即使工具未暴露给 LLM，也无法越权执行。
- Handler 只调用模块 Service（`VocabularyService`），不直接查询数据库；Repository 构造沿用现有组合方式，Phase 3 再收敛到统一工厂。最终写入仍由确认后的 `business.execute` → `TaskService` 完成。
- 预览阶段只读，不写业务数据；重复调用同一工具不会产生副作用。
- 错误码：`tool_not_found` / `forbidden` / `invalid_arguments` / `business_error` / `tool_execution_error`。
- 单次流程只执行第一个 tool call，最多一个工具轮次；多轮工具循环留给 Phase 2。

## 7. 消息与可观测性

- 每个工具调用保存两条 `conversation_messages`：
  - `message_type=tool_call`，记录参数；
  - `message_type=tool_result`，记录执行结果；
  - 两者通过 `tool_call_id` 关联。
- 运行事件新增 `tool_status`，字段与前端 `ToolExecution` 对齐；前端已有执行卡片，可直接展开参数和结果。
- `agent_run_events` 保留事件序号，支持断线重放。
- 日志（`app.agent.tools`）记录工具名、错误码、run_id、耗时。
- 测试环境可开启 `FLA_LLM_TRACE_ENABLED=true`，把每次请求的 messages/tools 和响应 content/tool_calls 追加到 `FLA_LLM_TRACE_PATH`（默认 `./data/llm-trace.jsonl`），不记录 API Key。
- `token_usage` 合并分类调用与工具调用。

## 8. 测试

```text
cd backend
.venv/bin/pytest -q
101 passed
```

新增覆盖：

- Registry：角色/Workflow 过滤、名称映射、Schema 转换、未注册工具。
- Executor：成功、参数缺失/多余字段、越权、workflow 不匹配、业务异常、未知异常、身份注入。
- 端到端（Fake LLM）：
  - 工具调用成功 → 预览草稿 → 确认 → `TaskService` 创建任务；
  - 业务错误 → 不生成预览、不写数据；
  - LLM 只返回追问文本 → 不调用工具；
  - 开关关闭 → 仍走原正则链路。
- 真实 DeepSeek 冒烟：一句中文创建长期任务，工具返回 `prefix_count=2`、`dictation_mode=offline`、`repeat_count=3`，预览字段与预期一致。

## 9. 已知限制

1. 仅 `task_create` 接入；`task_update`、`task_delete`、`vocabulary_*` 仍走原链。
2. 单轮工具调用，Tool Result 尚未回传给 LLM 进行二轮决策。
3. `learning.stats` 已注册但当前 `learning` 路由仍直接走 `respond`，未通过工具调用。
4. 旧正则链路保留在开关后；Phase 2 完成等价性验证后删除。
5. 工具名称转换规则是全局的（点号 → 下划线），新增工具需避免转换后重名（Registry 已在初始化时校验）。
6. 大词库时 Prompt 只放词库摘要，`ids` 模式需要外部提供具体 ID，当前对话场景主要使用 `all/prefix/range`。

## 10. 发布方式

- 默认关闭，发布后行为不变。
- 验证时设置 `FLA_AGENT_TOOL_CALLING_ENABLED=true`（生产需重启）。
- 回滚：删除该环境变量或设为 `false` 后重启；无需数据库迁移。
- 前端产物有变化（消息类型与渲染），需随发布一起构建。
