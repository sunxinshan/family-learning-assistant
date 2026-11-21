# STATE — 跨会话项目状态

> 仓库根 `STATE.md`。AI 每次开始新会话先读这个，结束前更新。

---

## 当前位置

- **活跃 Change**: 无
- **当前阶段**: 无（入场扫描 + as-built 架构文档 + 域名迁移 + Checkpointer 断连修复均已上线）
- **当前 Task**: —
- **中断任务**（来自 R1.5 清窗）: 无
- **会话开始建议**:
  - 先读 `.specs/CONTEXT.md`（rules 层，每次必读）
  - 2-design / 架构类任务再读 `.specs/ARCHITECTURE.md`（as-built，含 ADR-001~016）
  - 未决项见 `.specs/intel-scan-2026-11-20.md`「待用户确认」：Q1（Dictation 归属）、Q4（跨模块 Repository）
  - 无活跃 change → 等用户给新 CHANGE，走 `@flow-kit/prompts/0-change.md`

## 阻塞与待决策

| 项 | 类型 | 详情 | 待谁 | 自 |
|---|---|---|---|---|
| Q1 Dictation 模块归属 | 决策 | 架构文档列为独立模块，代码中不存在，听写折入 task/practice | 用户 | 2026-11-20 |
| Q4 跨模块 Repository 访问 | 决策 | 9 处现存违规（架构 §3.3 禁止），已登记技术债 TD-A | 用户 | 2026-11-20 |
| 工作区未提交改动 | 范围 | admin checkpoint 巡检 / Agent 脱敏 / AdminPage，11 文件改动 + 7 未跟踪（域名迁移已单独提交，未混入） | 用户 | 2026-11-20 |
| 后端 CORS 遗留 | 配置 | `FLA_CORS_ORIGINS` 仍是 `yidongxun.com`；同源访问不受影响，下次重启服务时一并更新 | 用户 | 2026-11-20 |
| ICP 备案 | 合规 | `zijixue.xyz` 页面底部仍显示 `苏ICP备2026067314号-1`（原属 yidongxun.com），需确认该域名是否已在该备案主体下 | 用户 | 2026-11-20 |
| 双份 `app` 代码 | 技术债 | release 里同时存在 `backend/app`（生产实际使用）与 venv 内 `site-packages/app`（残缺旧副本，缺 `executor.py`）。不在 `backend/` 下执行的脚本会静默加载旧代码。建议删除副本或换 `.pth` | 用户 | 2026-11-21 |

## 决策日志（最近 10 条，倒序）

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
- [x] 当前无活跃 change（无工件齐备性问题）
- [x] 没有未归档但已合并的 change
- [x] 没有 > 3 轮自动重试仍未解决的失败
