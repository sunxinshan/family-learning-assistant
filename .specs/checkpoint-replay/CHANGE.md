# CHANGE: 从历史 checkpoint 分叉重跑（调试重放）

- **Change ID**: checkpoint-replay
- **创建日期**: 2026-11-21
- **路径建议**: 中等（REQUIREMENT 增量 → DESIGN → TASK → DEV → TEST）
- **状态**: draft

---

## Why（为什么做）

用户报「执行失败」或「答得不对」时，现在只有三条线索：日志（一句话）、`agent_runs`（终态 + 错误文案）、`checkpoint`（每一步的完整 state）。

第三条最有用，但目前只能**看**不能**验**。11-20 那次 `InterfaceError` 就卡在这里：能看到 checkpoint 里停在什么状态，却没法回答「如果现在再跑一次，是同样的结果吗？」「换掉这段 prompt 会不会不同？」。只能靠重启服务 + 让用户重说一遍，既不可复现，也不可对比。

已有的 admin checkpoint 巡检（未提交 WIP）解决了「看」；本 change 解决「验」。

## What（做什么）

给管理员一个动作：指定 `(thread_id, checkpoint_id)`，把该刻的 state 复制到一个隔离的新 thread，用**当前**的代码/prompt/模型继续执行，返回与原执行可对比的结果（route、response、pending_action、token 用量、耗时）。

原 thread 的 checkpoint 链与业务数据不动，会话里不会多出消息，`agent_runs` 不会多出记录。

## 影响面

- [ ] 影响 `REQUIREMENT.md`（新建，无存量）
- [x] 影响 `DESIGN.md` / 引入新 ADR（ADR-017 重放隔离方式、ADR-018 副作用边界）
- [ ] 影响现有 AC
- [ ] 影响数据模型 / 迁移（**无迁移**，MVP 不落库）
- [x] 影响外部 API 兼容性（新增 admin 端点，纯增量，老接口不变）
- [ ] 仅修复 bug

## 范围排除（这次不做）

- **不做前端界面**。先用 admin API + curl 验证链路；界面等 ② 的 AdminPage WIP 提交后再接（避免和未提交改动纠缠）。
- 不做 ① 事件重放的 `Last-Event-ID` / 事件表保留策略。
- 不做 ④ 崩溃续跑（进程重启后孤儿 run 自动恢复）—— 那是另一个 change，且优先级更高，单独开。
- 不做「重放结果持久化 / 历史列表 / 两次重放 diff」。MVP 返回即弃，需要留痕再议。
- 不做「修改 state 后再跑」（注入式调试），只做「原样从该点重跑」。

## 验收线（粗粒度）

1. 给一个真实 `(thread_id, checkpoint_id)`，能拿到重放结果，并和原执行并排看出差异。
2. 重放前后，原 thread 的 checkpoint 条数、`get_state` 结果、会话消息数、业务表行数**全部不变**。
3. 同一 checkpoint 重放两次都成功，互不干扰。

## 风险与未知

- **必然的差异不是 bug**：重放用当前 prompt/模型，若 `prompt_version` 已变，结果不同是预期。返回里必须带版本号，否则会被误读成"重放不稳定"。
- **费用**：每次重放至少一次 LLM 调用；从 `classify` 之前重放会跑完整链路。
- **单 worker 全局锁**：重放若同步占用 Agent 执行锁，会阻塞真实用户请求数秒。需要在设计里明确取舍。
- **checkpoint 表膨胀**：每次重放新增若干行（实测一次 2 节点图约 3~4 行）。MVP 接受，需登记清理缺口。
- **未知**：`as_node` 锚点的可靠性依赖 `writes` 表里 `branch:to:<node>` 的写法规格，LangGraph 大版本升级需复核（已记为 DESIGN 的复检点）。
