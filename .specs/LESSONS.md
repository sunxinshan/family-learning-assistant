# LESSONS — 跨任务失败知识库

> 项目级常驻文件。**每个新任务开工前必扫**（R1.8）。

---

## 标签索引

- `arch` 架构决策类 · `lib` 第三方库陷阱 · `tool` 构建/测试工具链 · `data` 数据建模/迁移
- `perf` 性能 · `sec` 安全 · `ux` 交互视觉 · `ops` 部署运维 · `proc` 流程协作

---

## 条目

### L-001 · [ops, tool] release 里有两份 `app` 代码，离线脚本必须显式指定 PYTHONPATH

- **首发**: 生产运维 · 2026-11-20
- **上次复核**: 2026-11-21
- **适用栈**: 生产 release 目录 `familylearning-*`（uvicorn + venv）
- **状态**: active
- **关键词**: PYTHONPATH site-packages app 副本 探针 脚本 import uvicorn 导入来源

**问题场景**
在服务器上跑一次性脚本（数据核对、探针、迁移）时，`import app.xxx` 拿到的是旧代码，报 `cannot import name ...`，让人误判"功能没生效"。

**为什么不行**
release 里同时存在 `backend/app/`（源码）与 `backend/.venv/lib/python3.12/site-packages/app/`（早期安装的残缺副本，缺 `executor.py`）。生产服务由 `cd backend && .venv/bin/uvicorn` 启动，uvicorn 把 cwd 插到 `sys.path[0]`，所以**运行时用源码目录**；但 `python /tmp/x.py` 的 `sys.path[0]` 是 `/tmp`，会静默落到那份残缺副本上。

**当前推荐做法**
离线脚本一律：
```bash
cd /opt/project2/app-v2/backend && set -a && source /opt/project2/shared/env/familylearning.env && set +a \
  && PYTHONPATH=$PWD .venv/bin/python /tmp/probe.py
```
并在脚本第一步打印 `import app.modules.x as m; print(m.__file__)` 自证导入来源。

**何时可重新评估**
删掉 `site-packages/app` 或改成指向源码的 `.pth` 之后（已登记 STATE.md 待决策）。

---

### L-002 · [lib, ops] PyMySQLSaver 是单条连接，空闲会被 MySQL 掐断且不自愈

- **首发**: 生产运维 · 2026-11-20
- **上次复核**: 2026-11-21
- **适用栈**: langgraph 1.2 + langgraph-checkpoint-mysql + PyMySQL
- **状态**: active
- **关键词**: InterfaceError wait_timeout checkpoint pymysql reconnect ping 断连 执行失败

**问题场景**
Agent 报"执行失败，请稍后重试"，日志里 `pymysql.err.InterfaceError: (0, '')`，发生在 `checkpoint/mysql/__init__.py` 的 `get_tuple`。

**为什么不行**
`PyMySQLSaver.from_conn_string()` 只在进程启动时建**一条**裸连接（`autocommit=True`），全程复用、无池、无 ping。MySQL `wait_timeout=28800`（8h）会单方面关闭空闲连接，客户端对象仍在，且**不会自愈** —— 后续每次调用都失败，直到重启。

**当前推荐做法**
调用 `invoke` / `get_state` / `update_state` 前先 `conn.ping(reconnect=True)`，并捕获连接级异常重试一次。已封装为 `runtime._with_checkpoint_retry(saver, fn, *args)`，**新增图调用必须走它**，不要直接 `graph.invoke`。

**何时可重新评估**
langgraph 的 MySQL saver 内置连接池/ping 之后。

---

### L-003 · [tool] 本机 `pytest` 默认 basetemp 会 EEXIST 失败

- **首发**: checkpoint-replay · 2026-11-21
- **上次复核**: 2026-11-21
- **适用栈**: 本机 macOS + 沙箱
- **状态**: active
- **关键词**: pytest basetemp tmp pytest-of-unknown EEXIST 测试失败

**问题场景**
全量 pytest 出现几十条 `FileExistsError: [Errno 17] ... pytest-of-unknown`，看起来像代码大面积出错，实际与改动无关。

**当前推荐做法**
统一带 `--basetemp=/tmp/<唯一名>`：
```bash
cd backend && .venv/bin/pytest -q --basetemp=/tmp/fla-pt-t03 tests/xxx.py
```

**何时可重新评估**
本机 `TMPDIR` 权限正常、且不再出现该错误时。

---

### L-004 · [lib, arch] checkpoint 的 `branch:to` 指向「下一跳」，不是「产出节点」

- **首发**: checkpoint-replay · T02 · 2026-11-21
- **上次复核**: 2026-11-21
- **适用栈**: langgraph 1.2.19（SqliteSaver / PyMySQLSaver 一致）
- **状态**: active
- **关键词**: checkpoint replay as_node update_state branch:to writes anchor 锚点 重放 fork

**问题场景**
要做「从历史 checkpoint 分叉重跑」，需要 `update_state(values, as_node=<产出该 checkpoint 的节点>)`，否则 `next` 会被重算成入口节点，已完成节点被重跑。

**当时尝试的方案**
按直觉查 `writes` 表：目标 checkpoint 的 parent 上那条 `channel = 'branch:to:<node>'` 的目标，认为它就是产出节点。

**为什么不行**
差一层。实测 a→b 两节点图：
```
mid          next=('b',)  values={'text':'a'}   ← 由 a 产出
mid.parent   branch:to 目标 = 'b'               ← 取到的是「下一跳」
mid.parent   next = ('a',)                      ← 真正的产出节点
```
用 `'b'` 当锚点：`update_state` 后 `next == ()`，`invoke` **一个节点都不执行**，values 原样返回，HTTP 仍 200、diff 全 false —— 看起来像"重放确认结果稳定"。

**当前推荐做法**
锚点 = **父快照的 `next`**（`graph.get_state(src.parent_config).next`），长度不为 1 就拒绝（并行分支安全失败）。不要从 `writes` 的字符串里推断，也不要从 `snap.metadata` 找 `writes`（langgraph 1.2 的 metadata 只有 `source`/`step`/`parents`）。

**何时可重新评估**
langgraph 变更 checkpoint 结构或 `update_state` 的 `as_node` 语义之后；届时先跑一个两节点图打印 `next` / `writes` 再动手。

---

### L-005 · [test] 换掉 `runtime.llm` 不会让节点变慢：`guidance` 里存了另一份引用

- **首发**: checkpoint-replay · 5-test · 2026-11-22
- **上次复核**: 2026-11-22
- **适用栈**: 本项目 AgentRuntime（`FallbackGuidanceService` 构造时绑定 llm）
- **状态**: active
- **关键词**: 超时测试 timeout SlowLLM guidance 依赖注入 假 LLM 打不中节点

**问题场景**
要测「重放超时返回 504」，做法是把重放预算压到 0.1s、让 respond 节点慢 0.5s。于是把 `runtime.llm = SlowLLM()`。

**为什么不行**
`AgentRuntime.__init__` 里 `self.guidance = FallbackGuidanceService(llm, prompt_dir)` 把**构造时的** llm 存进了 guidance 实例。respond 节点调的是 `self.guidance.respond()` → 内部用 `guidance.llm`，与 `runtime.llm` 无关。结果 graph 一点没慢，`future.result(timeout=0.1)` 直接返回，测试报 `DID NOT RAISE`。

**当前推荐做法**
打桩要跟着调用链走：`runtime.llm = slow` **且** `runtime.guidance.llm = slow`。写这类测试时先确认节点实际调用的是哪个属性，别只看构造函数签名。

**何时可重新评估**
`FallbackGuidanceService` 改成每次从 runtime 取 llm，或 guidance 被移出图节点时。

---

## 提名条件

调试/试错 > 30 分钟；错因跨任务复用；6 个月内可能再撞；否决理由不写就丢。

**不入库**：一次性笔误、项目业务规则（进 CONTEXT.md）、已在 ADR 详述的架构权衡。
