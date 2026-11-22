# STATE — 跨会话项目状态

> 仓库根 `STATE.md`。AI 每次开始新会话先读这个，结束前更新。

---

## 当前位置

- **活跃 Change**: `checkpoint-replay`（从历史 checkpoint 分叉重跑）
- **当前阶段**: **5-test 完成** —— 五轮金字塔跑完，140 用例全绿，AC 7/7 覆盖。产物 `.specs/checkpoint-replay/TEST.md`。下一步 `6-review`
- **当前 Task**: —（T07 属 7-integration，待部署后执行）
- **中断任务**（来自 R1.5 清窗）: 无
- **会话开始建议**:
  - 先读 `.specs/CONTEXT.md`（rules 层，每次必读）
  - 本 change 再读 `.specs/checkpoint-replay/{CHANGE,REQUIREMENT,DESIGN,TASK,TEST}.md`
  - 2-design / 架构类任务再读 `.specs/ARCHITECTURE.md`（as-built，含 ADR-001~016）
  - 未决项见 `.specs/intel-scan-2026-11-20.md`「待用户确认」：Q1（Dictation 归属）、Q4（跨模块 Repository）
  - 下一步：`@flow-kit/prompts/6-review.md`

## 阻塞与待决策

| 项 | 类型 | 详情 | 待谁 | 自 |
|---|---|---|---|---|
| **文档偏差待回写（3 条）** | 决策 | ① REQUIREMENT「超时即返回，不写任何状态」措辞过强（update_state 已在隔离 thread 写入，不碰原链/业务表）；② DESIGN §2.3 锚点公式 off-by-one；③ DESIGN §9.1 与实现不一致。均已在 TEST.md 结论段列出 | 用户 | 2026-11-22 |
| Q1 Dictation 模块归属 | 决策 | 架构文档列为独立模块，代码中不存在，听写折入 task/practice | 用户 | 2026-11-20 |
| Q4 跨模块 Repository 访问 | 决策 | 9 处现存违规（架构 §3.3 禁止），已登记技术债 TD-A | 用户 | 2026-11-20 |
| ~~**W00 WIP 基线提交**~~ | 已解决 | 2026-11-21 已提交基线 `0383acd`（checkpoint 巡检：后端 5 文件 + 前端 6 文件 + e2e）。`admin/{router,service,schemas}.py` 现为干净基线，本 change 改动可独立成 commit 与回滚 | — | 2026-11-21 |
| 工作区未提交改动 | 范围 | admin checkpoint 巡检 / Agent 脱敏 / AdminPage，11 文件改动 + 7 未跟踪（域名迁移已单独提交，未混入） | 用户 | 2026-11-20 |
| 后端 CORS 遗留 | 配置 | `FLA_CORS_ORIGINS` 仍是 `yidongxun.com`；同源访问不受影响，下次重启服务时一并更新 | 用户 | 2026-11-20 |
| ICP 备案 | 合规 | `zijixue.xyz` 页面底部仍显示 `苏ICP备2026067314号-1`（原属 yidongxun.com），需确认该域名是否已在该备案主体下 | 用户 | 2026-11-20 |
| 双份 `app` 代码 | 技术债 | release 里同时存在 `backend/app`（生产实际使用）与 venv 内 `site-packages/app`（残缺旧副本，缺 `executor.py`）。不在 `backend/` 下执行的脚本会静默加载旧代码。建议删除副本或换 `.pth` | 用户 | 2026-11-21 |

## 决策日志（最近 10 条，倒序）

- `[2026-11-22]` **5-test 完成**：五轮金字塔，140 passed。抓到两个实质问题：① **AC-7 此前零覆盖**（超时/不抢锁都没测），补 `tests/test_checkpoint_replay_resilience.py` 4 条；② **pip-audit 报 dnspython 2.9.1 CVE-2026-128089（CVSS 7.5 High）**，已升 2.9.2 并复扫为 0，`uv.lock` 变更 → 生产发布需重装依赖。bandit 0 High、2 Medium（B608 误报，where 为常量二选一）；秘钥扫描 0 命中 — `TEST.md`
- `[2026-11-21]` 4-dev 完成（T01–T06 + T-FIX-01，8 个提交）：后端新增 `POST /api/v1/admin/checkpoints/{thread}/{checkpoint}/replay`，全量 136 passed。两条已知取舍：`tokenUsage` 内层保持 snake_case 以对齐既有 `/agent/runs` 契约；`replay_anchor_ambiguous` 在线性图下无法构造，未覆盖 — `T06-SUMMARY.md`
- `[2026-11-21]` T-FIX-01：`not src.values` 会把「存在的入口 checkpoint」误报成 404（入口的 values 也是 `{}`，输入在 pending writes 里）。改用 `src.created_at is None` 判存在；实测入口→409 terminal、不存在→404。由 T03 写测试时发现 — `T03-SUMMARY.md`
- `[2026-11-21]` **DESIGN §2.3 被实测推翻**：`writes.branch:to` 指向的是「下一跳」而非「产出节点」，差一层。照原公式当 `as_node` 会一个节点都不跑却返回 200。已改为运行时读父快照的 `next` 解析锚点，`replay_from_checkpoint(thread_id, checkpoint_id)` 不再接收 anchor；`producing_node` 改名 `routing_target` 并标注不可用于锚点。DESIGN.md 本身未改，待批准回写 — `T02-SUMMARY.md`「决策与偏离」1
- `[2026-11-21]` Wave 1 完成：T01（routing_target / count_thread + 6 断言）、T02（重放核心 + 端到端冒烟），全量 122 passed；T01/T02 的 SUMMARY 与 `.specs/LESSONS.md`（3 条真实踩坑）已入库
- `[2026-11-21]` W00 完成：checkpoint 巡检 WIP 已作为基线提交（`0383acd`，后端 + 前端 + e2e 共 13 文件），提交前后端 116 passed、前端 `tsc --noEmit` 通过。另提交 `c0addd8`（LLM trace 工具 + `/logs/` 忽略）、`d615452`（本 change 工件）、`b26135d`（服务器交接文档） — 工作区仅剩 flow-kit 与两个不入库项
- `[2026-11-21]` 3-task 完成：拆成 T01–T07 / 5 个波次。锚点解析由 admin service 算好再传给 runtime（避免 agent→admin 反向依赖，与 DESIGN §2.2 的落位有一处细化）；token_usage 只记本次增量（update_state 会继承原 usage）；`checkpoint_rows_added` 用 `get_state_history` 长度，runtime 不引入 admin 依赖 — `.specs/checkpoint-replay/TASK.md`
- `[2026-11-21]` 开 change `checkpoint-replay`：重放选「从某点重跑」而非崩溃续跑；隔离用新 thread + `update_state(as_node=产出节点)`，锚点取 parent 的 `branch:to:<node>`；重放自建 checkpointer 连接，不共用主连接、不抢执行锁 — `~/.specs/checkpoint-replay/DESIGN.md`（ADR-017~021）
- `[2026-11-20]` Checkpointer 断连修复上线（选择"根治"而非仅重启）：`ping(reconnect=True)` 探活 + 连接级异常重试一次，包住 `invoke`/`get_state`/`update_state`；release `familylearning-3a03d12` — `docs/生产部署记录-20261120.md` §2
- `[2026-11-20]` 域名迁移落地：`https://zijixue.xyz` 根路径上线（前端 base `/`、独立 LE 证书、旧子路径 301），按 HEAD `cf5f18f` 干净构建，未带工作区未提交改动 — `docs/生产部署记录-20261120.md`
- `[2026-11-20]` 架构文档分两层：`.specs/ARCHITECTURE.md` 为 as-built 现状，`docs/…V1.0.md` 保留为设计意图；对外域名改为 `zijixue.xyz`，`yidongxun.com` 停服 — 用户确认
- `[2026-11-20]` 采用 flow-kit 作为本项目开发流程框架，CONTEXT.md 为单一 AI 上下文源 — 本次扫描
- `[2026-11-05]` Agent 采用原生 Tool Calling + Registry/Executor，`task_create` 首批接入 — `docs/Tool_Calling与Tool_Registry改造-Phase1实施记录.md`
- `[2026-11-02]` 生产统一 DeepSeek `deepseek-v4-flash` — `docs/技术决策记录.md#TD-16`

## 已归档 Changes（最近 5 个，倒序）

| 日期 | Change | 摘要 | PR |
|---|---|---|---|
| — | — | 项目此前未使用 flow-kit，无 CHANGE 归档 | — |

---

## 横向命令状态

```yaml
ai_context_doc: .specs/CONTEXT.md
last_intel_scan: 2026-11-20
last_architect_at:            # 未跑
last_evolve_at:               # 未跑
last_evolve_promoted: []
last_health_at:               # 未跑
last_health_score:            # 未跑
```

`last_intel_scan` 基线：`main @ cf5f18f` + 工作区未提交改动（详见 `.specs/intel-scan-2026-11-20.md`）。

---

## 健康检查（AI 每次会话开始前自检）

- [x] `.specs/` 目录存在
- [x] 活跃 change `checkpoint-replay` 工件齐备（CHANGE / REQUIREMENT / DESIGN / TASK）
- [x] 没有未归档但已合并的 change
- [x] 没有 > 3 轮自动重试仍未解决的失败
