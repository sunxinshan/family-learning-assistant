# AGENTS.md

本文件记录本仓库中需要 AI 编码助手长期遵守的开发约定。

## capability_guide.md 维护规范

能力清单位置：`backend/app/modules/agent/prompts/capability_guide.md`

- 运行时用途：意图识别无法匹配业务操作时，后端读取该文件，与用户原始输入一起交给兜底 LLM 生成自然语言引导（实现见 `backend/app/modules/agent/guidance.py`）。
- 配套 Prompt：`backend/app/modules/agent/prompts/fallback_guidance.txt`，只写回答行为规则，不写能力清单。
- 该文件不是 Tool Registry，也不描述函数、类、参数 Schema 或调用协议。

### 后续维护：增量更新，不全量重扫

1. 默认不主动扫描项目、不主动修改能力清单；只有开发者明确要求更新时才改。
2. 只检查本次对话涉及的功能、代码变更和相关调用链，不要求每次重新扫描整个代码库。
3. 不以需求文档、设计稿、注释、测试桩、未接通的接口或 Tool Registry 定义作为「能力已实现」的证据。
4. 每项能力必须核实：用户入口可达、后端链路完整、数据真实持久化、普通用户权限允许。
5. 未接通、仅 Mock、只有后端没有前端入口、仍依赖人工步骤的功能，不得写入「当前可用能力」。
6. 更新能力说明时同步更新限制条件和自然语言示例；能力下线时一并移除示例。
7. 已确认不支持的能力写入「明确不支持的能力」，避免运行时 LLM 误推荐。
8. 内容面向普通用户，保持简洁；不要写类名、函数名、参数 Schema、Tool 名称或内部术语。
9. 修改后至少运行：
   ```bash
   cd backend
   .venv/bin/pytest -q tests/test_agent_fallback_guidance.py
   ```

### 兜底链路约束

- 兜底阶段只解释和引导，不执行业务操作、不修改业务数据、不新增消息类型或前端交互。
- 意图识别成功后的现有流程（Python 文本解析、参数拼装、业务写入）不因引导能力改动而变化。

## Tool Calling 约定

- 灰度开关：`FLA_AGENT_TOOL_CALLING_ENABLED`，默认关闭；关闭时必须保留原业务链路。
- Registry 只注册有真实 Handler 的工具，不再保留占位实现。
- 工具内部名可以使用点号（如 `task.create.preview`），但 Provider 侧名称会转换为下划线；新增工具必须避免转换后重名。
- 工具参数 Schema 不得包含 `user_id`、`role` 等身份字段，身份由 Executor 注入；Schema 必须设置 `extra="forbid"`。
- 新增工具必须补齐：`description`、`args_schema`、`workflows`、真实 Handler、Executor/Registry 测试与端到端测试。
- Workflow 只向 LLM 暴露当前场景需要的工具，不能一次性暴露全部 Registry 工具。
- 预览类工具只读；正式写入必须留在用户确认后的 Workflow Node 中调用 Service。
- 工具调用与结果分别写入 `conversation_messages`（`tool_call` / `tool_result`），通过 `tool_call_id` 关联，并发送 `tool_status` 事件。
