# 家庭学习助手 · 前端原型

Phase 0 的可运行 React + TypeScript 交互原型。产品以 Agent 对话为核心入口，词汇与听写在独立练习页面完成。

## 环境要求

- Node.js 20 或更高版本
- npm 10 或更高版本

## 本地启动

```bash
cd frontend
npm install
npm run dev
```

打开终端输出的本地地址，默认是：

```text
http://127.0.0.1:5173
```

## 演示账户

| 身份 | 昵称 | 密码 |
|---|---|---|
| 普通用户 | Alice | `demo123` |
| 管理员 | Admin | `admin123` |

登录页也提供普通用户和管理员的一键演示入口。

## 常用命令

```bash
npm run dev        # 启动开发服务器
npm run typecheck  # TypeScript 类型检查
npm run build      # 类型检查并生成生产构建
npm run preview    # 预览生产构建
```

## 数据说明

- 所有原型数据保存在浏览器 `LocalStorage`。
- 登录页和账户菜单均可重置演示数据。
- 首次打开会载入内置的任务、词库、练习记录和操作日志。
- 正式后端开发前不会向服务端发送任何业务数据。

## 路由

| 路由 | 页面 |
|---|---|
| `/login` | 登录与注册 |
| `/` | Agent 对话 |
| `/tasks` | 学习任务列表 |
| `/tasks/:taskId` | 任务详情 |
| `/vocabulary` | 个人/公共词库 |
| `/vocabulary/:libraryId` | 词库详情 |
| `/learning` | 学习记录 |
| `/admin` | 管理员后台 |
| `/practice/vocabulary/:taskId` | 词汇练习 |
| `/practice/dictation/:taskId` | 听写练习 |

## 相关文档

- 总体架构：[../docs/家庭学习助手系统架构与开发设计文档 V1.0.md](../docs/家庭学习助手系统架构与开发设计文档%20V1.0.md)
- 前端方案：[../docs/前端原型设计方案.md](../docs/前端原型设计方案.md)
- 实施记录：[../docs/原型开发实施记录.md](../docs/原型开发实施记录.md)
