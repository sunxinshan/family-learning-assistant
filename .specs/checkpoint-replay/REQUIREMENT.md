# REQUIREMENT: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **创建日期**: 2026-11-21

---

## 用户故事

作为**系统维护者**，当用户反馈「执行失败」或「答得不对」时，我想拿当时那一刻的 checkpoint 原地再跑一遍，
这样我能分清三件事：是**模型/提示词**的问题（重放稳定复现）、是**当时环境**的问题（重放正常，说明是连接/数据状态）、还是**用户输入理解**的问题（route 就分叉了）。
不必让用户重说一遍，也不必靠重启服务去"再试一次"。

## 验收准则（AC）

### AC-1 · 能重放并对照
给定存在的 `(thread_id, checkpoint_id)`，管理员触发重放后，返回至少包含：
原执行的 `route` / `response` / `pending_action` / `token_usage`，以及重放的对应值、耗时、使用的 `prompt_version` 与模型名。
响应必须能让人**不用再查库**就看出"哪里不一样"。

### AC-2 · 原 thread 零污染
重放前后，对同一 `thread_id` 断言全部成立：
`checkpoints` 表该 thread 的行数不变、`get_state(thread_id)` 的值与 `next` 不变、`writes` 表该 thread 行数不变。

### AC-3 · 不产生业务副作用
重放不得新增/修改：`conversation_messages`、`agent_runs`、`agent_run_events`、以及 task / vocabulary / practice 等业务表任何行。
此条为**结构性保证**（不经过写入路径），不依赖运行时开关。

> **2026-11-23 修订（6-review C-1，实测后补）**：`prepare` 的 `vocabulary_import` 分支会调
> `ContentService.extract()`，写 `content_extractions` 并改 `materials.status` —— 该路由重放**结构性做不到**无副作用。
> 因此把它列为**不可重放路由**（`replay_unsupported_route` 409），AC-3 对「可重放路由」成立。
> 这不是放宽 AC-3，而是把"哪些路由根本不许重放"写清：宁可拒绝，也不假装只读。

### AC-4 · 目标不可重放时明确拒绝
以下情况返回明确错误码与说明，不做任何执行：
目标 checkpoint 不存在；该点已到 `END`（`next` 为空，无可执行节点）；该点处于 `interrupt` 挂起且尚未解决。

### AC-5 · 可重复
同一 `(thread_id, checkpoint_id)` 连续重放两次都成功，且两次互不影响（各自独立的执行环境）。

### AC-6 · 权限与降级
非管理员 401/403。未配置 checkpoint 库（`_url()` 返回 None）时返回明确错误，不 500、不抛栈。

### AC-7 · 不拖垮在线服务
重放若因锁被占用或超时无法在限定时间内完成，必须尽早返回「忙碌/超时」，不得让真实用户的请求排在后面无限等待。

## 范围切分

### v1（本次必做）
- 后端单端点 + `AgentRuntime.replay_from_checkpoint()`
- 产出节点锚定、隔离 thread、read-only 执行
- 单元测试：隔离性（AC-2/AC-5）、拒绝路径（AC-4）、无写入（AC-3）
- 用一次真实 checkpoint 手工跑通并记录证据

### v2（下一轮考虑，不本次）
- AdminPage 的重放按钮与差异视图
- 重放记录落库（`replay_runs`）与历史列表
- 「改 state 再跑」的注入式调试
- replay thread 的 TTL 清理任务

### out（永远不做）
- 让普通用户触发重放（会绕过确认流程、产生费用）
- 在重放里执行正式写入（那是 confirm 流程的职责）

## 非功能性需求

- 单次重放默认超时 60s，超时即返回，不写任何状态。
- 重放产生的 checkpoint 行数需在响应里可见（便于评估膨胀）。
- 日志必须带 `source_thread` / `source_checkpoint` / `replay_thread` / `prompt_version`，可反查。

## 依赖与假设

- 依赖：`langgraph>=1.2`（`get_state_history` / `update_state(as_node=...)`）；已验证实测行为，见 DESIGN §2。
- 依赖：现有 `CheckpointRepository`（admin，未提交 WIP）提供 checkpoint 读取；本 change 复用，不重写。
- 假设：`task_create` 工具路径只做只读预览（AGENTS.md 已约定），因此重放到 `prepare`/`tool_create` 不写业务表。
- 假设：`_execute_new_run` 中的消息落库在图执行**之后**，因此绕过该函数即不写消息 —— 设计依赖此结构，若将来把落库移进节点需重审。
