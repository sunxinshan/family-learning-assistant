# 家庭学习助手前端

React 19 + TypeScript + Vite。默认连接真实 FastAPI；Mock 仅在 `VITE_API_MODE=mock` 时启用。

## 启动

```bash
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

后端默认地址：`http://127.0.0.1:8000/api/v1`。可通过 `VITE_API_BASE_URL` 覆盖。

## 验证

```bash
npm run typecheck
npm run build
npm run test:e2e
npm audit --audit-level=high
```

E2E 覆盖桌面 Chromium 与 iPhone 13 视口，包括真实 Token 刷新、服务端导入、Agent 确认恢复、线上/线下听写、Learning 和 Admin。
