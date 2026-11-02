# 家庭学习助手后端

正式开发 Phase 0 基础设施骨架。

## 环境要求

- Python 3.12+
- uv

## 初始化

```bash
cd backend
cp .env.example .env
uv sync --dev
```

## 启动

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

- `GET http://127.0.0.1:8000/api/v1/health/live`
- `GET http://127.0.0.1:8000/api/v1/health/ready`

## 数据库迁移

```bash
uv run alembic upgrade head
```

Phase 0 只提供迁移机制和初始空迁移，不创建正式业务表。

## 测试

```bash
uv run pytest
uv run ruff check .
uv run pytest --cov=app
```
