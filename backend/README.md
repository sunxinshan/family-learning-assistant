# 家庭学习助手后端

Python + FastAPI + LangGraph 正式后端。

## 启动

```bash
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 质量门禁

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

MySQL 全量测试通过 `FLA_TEST_DATABASE_URL`、`FLA_TEST_CHECKPOINT_BACKEND=mysql`、`FLA_TEST_CHECKPOINT_URL` 切换。

## 运维脚本

- `scripts/load_check.py`：只读并发冒烟。
- `scripts/backup_mysql.sh` / `restore_mysql.sh`：业务库与 Checkpoint 备份恢复。
- `scripts/cleanup_agent_history.py`：过期 Agent 事件与 Checkpoint 清理。

详见 `../docs/部署说明.md`。
