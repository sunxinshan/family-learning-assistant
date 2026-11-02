# 家庭学习助手

以 Agent 对话为核心入口的家庭学习助手，支持词库导入、听写任务、线上/线下练习、学习统计和管理员管理。

## 技术栈

- Frontend：React 19 + TypeScript + Vite + Playwright。
- Backend：Python 3.12 + FastAPI + SQLAlchemy + Alembic + LangGraph。
- Database：MySQL 8.4（生产验证）/ SQLite（开发测试）。
- Agent：OpenAI-compatible Adapter + Mock Adapter、LangGraph Interrupt/Resume、MySQL Checkpointer、SSE。

## 快速启动

```bash
cd backend
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

开发演示账户：

- 普通用户：`Alice` / `demo123`
- 普通用户：`Bob` / `demo123`
- 管理员：`Admin` / `admin123`
- 管理员：`Manager` / `manager123`

## 验证

```bash
cd backend
uv run ruff check .
uv run pytest

cd ../frontend
npm run typecheck
npm run build
npm run test:e2e
npm audit --audit-level=high
```

当前记录：后端 59 passed、桌面+移动 E2E 6 passed、MySQL 8.4.7 全量通过。

## 文档

- [开发总结](docs/开发总结.md)
- [部署说明](docs/部署说明.md)
- [开发进度](docs/开发进度.md)
- [测试报告](docs/测试报告.md)
- [技术决策记录](docs/技术决策记录.md)
- [系统架构与开发设计文档 V1.0](docs/家庭学习助手系统架构与开发设计文档%20V1.0.md)
- [正式开发实施计划](docs/正式开发实施计划.md)
- [开发任务拆分清单](docs/开发任务拆分清单.md)
