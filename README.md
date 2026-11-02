# 家庭学习助手

以 Agent 对话为核心入口的家庭学习助手。当前仓库处于 **正式开发 Phase 0**：前端原型可运行，后端基础设施骨架已建立，尚未实现正式业务模块。

## 项目结构

```text
.
├── docs/       # 总体架构、原型、审查、决策和实施计划
├── frontend/   # React + TypeScript + Vite 前端
├── backend/    # Python + FastAPI Phase 0 基础设施
└── .github/    # CI
```

## 快速启动

### 前端

```bash
cd frontend
npm install
npm run dev
```

演示账户：

- 普通用户：`Alice` / `demo123`
- 管理员：`Admin` / `admin123`
- 管理员：`Manager` / `manager123`

### 后端

```bash
cd backend
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

- `http://127.0.0.1:8000/api/v1/health/live`
- `http://127.0.0.1:8000/api/v1/health/ready`

## 当前状态

- 前端原型：完整可操作，仍使用 Mock API + LocalStorage。
- 后端 Phase 0：配置、日志、统一错误、请求 ID、数据库连接、Alembic、pytest、CI 和健康检查已完成。
- 正式业务模块：尚未开始。
- 前端 API 边界：已整理为统一 `frontend/src/api/index.ts`，仍由 Mock adapter 提供实现，后续可替换为 HTTP adapter。

## 文档

- [系统架构与开发设计文档 V1.0](docs/家庭学习助手系统架构与开发设计文档%20V1.0.md)
- [前端原型设计方案](docs/前端原型设计方案.md)
- [原型开发实施记录](docs/原型开发实施记录.md)
- [正式开发实施计划](docs/正式开发实施计划.md)
- [架构审查问题清单](docs/架构审查问题清单.md)
- [开发任务拆分清单](docs/开发任务拆分清单.md)
- [正式开发决策记录](docs/正式开发决策记录.md)
- [Phase 0 实施记录](docs/阶段0实施记录.md)
