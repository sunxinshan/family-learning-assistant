# 服务器环境移交说明（新应用：paihangbang.xyz）

> 移交日期：2026-11-06
> 服务器：`115.159.77.118`（腾讯云轻量应用服务器，Ubuntu 24.04.4 LTS）
> 现有应用：**家庭学习助手 / 英语森林**（`project2`，域名 `yidongxun.com`）—— **本应用继续对外服务，本次移交不涉及它的任何改动**
> 接收方：即将上线的**第二个应用**，域名 `paihangbang.xyz`（详见第 0 节关于域名的确认）

---

## 0. 先说一个必须确认的问题：域名拼写

你提到的是 `panghangbang.xyz`（多一个 n）。我在服务器和 DNS 两侧核对的结果：

| 域名 | DNS 解析 | 证书 | 当前响应 |
| --- | --- | --- | --- |
| `paihangbang.xyz` | 已指向 `115.159.77.118` | 已有，2026-12-18 到期 | HTTPS 返回 `410 Gone`（占位） |
| `panghangbang.xyz` | **无解析记录** | 无 | 无 |

`paihangbang.xyz` 是这台机器上**曾经跑过「经典小说排行榜」应用**的域名，2026-11-02 该应用下线，域名被冻结成 410 占位，证书一直由 certbot 自动续期，仍然有效。所以：

- **如果目标就是 `paihangbang.xyz`**：DNS、证书、nginx 占位块都已就绪，新应用接上去只需改一处 nginx 配置 + 起服务，最省事。本文档按这个前提写。
- **如果确实是新注册的 `panghangbang.xyz`**：需要先加 A 记录指向 `115.159.77.118`，再单独签发证书（见 6.2）。**两个域名指向同一台机器、共用 80/443，只要 server_name 不同就不冲突**，做法在文档里也覆盖了。

---

## 1. 一分钟速查

| 项目 | 值 |
| --- | --- |
| 公网 IP | `115.159.77.118` |
| 系统 | Ubuntu 24.04.4 LTS / 内核 6.8.0-124-generic |
| 规格 | 4 vCPU / 3.6 GiB 内存 / 1.9 GiB swap / 40 GB 系统盘（剩 18 GB） |
| 时区 | `Asia/Shanghai`（CST +0800），chrony 已对时 |
| Web 服务器 | nginx 1.24.0，配置目录 `/etc/nginx/conf.d/`（`sites-enabled` 为空） |
| 已占用端口 | 22、80、443、3306、33060、8002、8003（+ 本地 53） |
| **给新应用的端口** | **`127.0.0.1:8004`（API）与 `127.0.0.1:8005`（Web）** |
| 数据库 | MySQL 8.0.46，仅监听 `127.0.0.1:3306` |
| 现有应用 | `project2.service` → `/opt/project2`，release `familylearning-fac55ad` |
| 现有数据库 | `english_forest`（**不得改动**） |
| 运行时 | 系统 `python3` 3.12.3；**无** node/npm/php/java/docker/redis |
| 证书续期 | `certbot.timer` 已启用，每日 05:15 前后检查 |

---

## 2. 服务器上现在有哪几个「应用」

| 应用 | 状态 | 目录 | 用户 | 端口 | 域名 |
| --- | --- | --- | --- | --- | --- |
| `project2`（家庭学习助手） | **运行中，必须保持** | `/opt/project2` | `project2` | 8002 / 8003 | `yidongxun.com`、`www.yidongxun.com` |
| `ranking`（经典小说排行榜） | 已下线，`disabled` | `/opt/ranking`（109 MB，保留备查） | `deploy` | 原 8000（现空闲） | `paihangbang.xyz`（410 占位） |
| 新应用（本次接收） | 待上线 | 建议 `/opt/app3` | 建议新建 `app3` | **8004 / 8005** | `paihangbang.xyz` |

系统用户：`ubuntu`(1000)、`lighthouse`(1001)、`deploy`(1002，旧 ranking 所有者)、`project2`(1003)。

> `deploy` 用户和 `/opt/ranking` 目录**不要删除**：旧应用的回滚依赖它们，且第 11 节的红线要求保留。

---

## 3. 端口契约（最重要的一条）

```text
公网 443 (nginx) ┬─ server_name yidongxun.com  → /api/ → 127.0.0.1:8002  (project2 API)
                 │                              → /     → 127.0.0.1:8003  (project2 静态站)
                 ├─ server_name paihangbang.xyz → 新应用（当前返回 410）
                 └─ default_server              → 410（占位，见 5.2）

公网 80 (nginx) → yidongxun.com 301 到 https；其余 host → 410
127.0.0.1:3306  → MySQL（仅本机）
127.0.0.1:8002/8003 → project2（仅本机，不对外）
```

**新应用必须：**

1. 只监听 `127.0.0.1`，**不要**监听 `0.0.0.0`（外网只走 nginx，避免绕过 HTTPS 和防火墙策略）；
2. **不要用 8002 / 8003**——那是 `project2` 的，占了会直接让它起不来；
3. 也不要抢 8000：旧 ranking 的 API 端口，虽然当前空闲，但留给它回滚用；
4. 推荐 **8004（API）+ 8005（静态/前端）**，两个端口当前都确认空闲。

---

## 4. 现有应用 `project2` 的结构（了解即可，不要改）

```text
/opt/project2/
├── app-v2 -> releases/familylearning-fac55ad   # 当前生效的软链接
├── releases/                                   # 23 个历史版本，共 13 GB
├── shared/
│   ├── env/familylearning.env                  # 全部配置（DB、JWT、LLM Key），权限 600
│   ├── storage/                                # 上传文件、教材资源
│   └── familylearning_uploads/
├── logs/                                       # out/err 日志 + logrotate.state + backup.log
├── backups/                                    # 2.4 GB，每日 03:45 自动备份
├── nginx/project2.conf                         # nginx 配置源文件
└── deploy/                                     # systemd 单元、logrotate 配置、启动脚本
```

启动方式（**同一时间只能有 systemd 或手动进程其中一种**，否则端口冲突）：

```bash
systemctl cat project2     # ExecStart=/opt/project2/app-v2/deploy/project2-start.sh
```

该脚本同时启动 `uvicorn 8002` 与 `serve_spa.py 8003`（系统 python3 起的静态站，带 SPA fallback），`wait -n` 托管，`trap` 清理。

当前运行快照（2026-11-06 20:2x）：

| 项 | 值 |
| --- | --- |
| `project2.service` | `active / running / enabled`，启动于 2026-11-05 18:21:57 |
| release | `familylearning-fac55ad` |
| 进程 | uvicorn PID 4091855（RSS ≈ 174 MB）、serve_spa PID 4091856 |
| 健康检查 | `https://yidongxun.com/api/v1/health/ready` → 200；首页 → 200 |

---

## 5. Nginx 现状与接入方式

### 5.1 现有配置文件

| 文件 | 作用 | 能否改 |
| --- | --- | --- |
| `/etc/nginx/conf.d/project2.conf` | `yidongxun.com` 全部规则 | **禁止修改** |
| `/etc/nginx/conf.d/ranking.conf` | `paihangbang.xyz` 的 410 占位 + `default_server` | 需与新应用协调后替换（见 5.2） |
| `ranking.conf.bak-20260920-144716`、`ranking.conf.offline-bak-20261102-202919` | 旧排行榜应用的配置备份 | 保留，不要删 |

`project2.conf` 关键内容（供对照，不必修改）：

```nginx
upstream english_forest_api { server 127.0.0.1:8002; keepalive 16; }
upstream english_forest_web { server 127.0.0.1:8003; keepalive 16; }

server {
    listen 443 ssl;                       # 注意：这里没有 default_server
    server_name yidongxun.com www.yidongxun.com;
    ssl_certificate     /etc/letsencrypt/live/yidongxun.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yidongxun.com/privkey.pem;
    client_max_body_size 20m;

    location /api/   { proxy_pass http://english_forest_api; ... }
    location /_next/ { proxy_pass http://english_forest_web; ... }
    location /       { proxy_pass http://english_forest_web; ... }   # 含 WebSocket Upgrade
}
```

### 5.2 `default_server` 陷阱（新应用最容易踩的坑）

当前 `ranking.conf` 里有两个块占着 `default_server`：

```nginx
server { listen 80  default_server; ... return 410; }
server { listen 443 ssl default_server; ... return 410; }
```

后果：

- 任何**未匹配到 server_name 的请求**（包括直接用 IP 访问、或新域名还没配置）都会拿到 410；
- 如果新应用在自己的配置里再写一次 `default_server`，`nginx -t` 会直接报错 `duplicate default server`，**reload 失败**；
- 更危险的是：有人为了「让它生效」去 `systemctl restart nginx`，此时 nginx 会因为坏配置**起不来**，`yidongxun.com` 跟着全线挂掉。

**正确做法（二选一）：**

- **方案 A（推荐，改动最小）**：新应用新建 `/etc/nginx/conf.d/paihangbang.conf`，**不写 default_server**，只写 `listen 443 ssl; server_name paihangbang.xyz www.paihangbang.xyz;`。由于 server_name 精确匹配优先级高于 default_server，它会正常接管该域名；`ranking.conf` 的两块可以原样留着当兜底。
- **方案 B**：把 `ranking.conf` 里两个 410 块删掉（或改成不含 default_server 的占位），由新应用的配置承担默认站点。**风险更大，需要同步确认用 IP 直接访问的行为**。

无论哪种，落地顺序必须是：

```bash
nginx -t            # 必须通过
systemctl reload nginx    # 只能 reload，绝对不要 restart
```

### 5.3 新应用的 nginx 配置模板

```nginx
# /etc/nginx/conf.d/paihangbang.conf
upstream app3_api { server 127.0.0.1:8004; keepalive 16; }
upstream app3_web { server 127.0.0.1:8005; keepalive 16; }

server {
    listen 80;
    listen [::]:80;
    server_name paihangbang.xyz www.paihangbang.xyz;
    return 301 https://paihangbang.xyz$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name paihangbang.xyz www.paihangbang.xyz;

    ssl_certificate     /etc/letsencrypt/live/paihangbang.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/paihangbang.xyz/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 20m;          # 按新应用需要调整

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location /api/ {
        proxy_pass http://app3_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://app3_web;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

是否同时监听 IPv6（`listen [::]`）取决于新应用，按需保留。

---

## 6. HTTPS 证书

### 6.1 现有证书

| 域名 | 路径 | 到期 | 说明 |
| --- | --- | --- | --- |
| `yidongxun.com` | `/etc/letsencrypt/live/yidongxun.com/` | 2026-12-19 | project2 在用，**不要动** |
| `paihangbang.xyz` | `/etc/letsencrypt/live/paihangbang.xyz/` | 2026-12-18 | 410 占位在用，新应用可直接复用 |

`certbot.timer` 已启用（下次触发 2026-11-07 05:15），**续期是全自动的**，新应用只要把证书路径写进 nginx 即可。

注意：`/etc/letsencrypt/` 目录对非 root 不可读，`nginx -t` 也必须 root（要读私钥）。所以「改 nginx 配置」这个动作必须走 root 或受限 sudo 助手脚本。

### 6.2 如果要签新域名（`panghangbang.xyz` 的情况）

```bash
# 1) 先在域名服务商处加 A 记录，确认已经生效
dig +short panghangbang.xyz        # 必须返回 115.159.77.118

# 2) 先让 80 端口能响应验证（临时加一个只 listen 80 的 server 块并 reload）
# 3) 签发（certonly 更稳，不让 certbot 自动改 nginx 配置）
sudo certbot certonly --nginx -d panghangbang.xyz -d www.panghangbang.xyz \
     --non-interactive --agree-tos
```

证书会落到 `/etc/letsencrypt/live/panghangbang.xyz/`，再把 nginx 配置里的路径改过去。

---

## 7. 数据库

| 项 | 值 |
| --- | --- |
| 版本 | MySQL 8.0.46（Ubuntu 24.04 包），服务 `mysql` |
| 监听 | `127.0.0.1:3306`（+ `33060` mysqlx），**不对外** |
| 字符集 | `utf8mb4` |
| `sql_mode` | `ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION` |
| `max_connections` | 151（**两个应用共享**，新应用连接池请控制在 10～20） |
| `innodb_buffer_pool_size` | 128 MB（偏小，但改它需要重启 MySQL，属高风险动作，本次不建议动） |
| 现有库 | `english_forest`（project2 专用） |
| 现有账号 | `english_forest_migrate`，配置在 `/opt/project2/shared/env/familylearning.env` 的 `FLA_DATABASE_URL` |

### 新应用必须做的

```sql
-- 用 root 执行
CREATE DATABASE app3 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'app3'@'127.0.0.1' IDENTIFIED BY '<强密码>';
GRANT ALL PRIVILEGES ON app3.* TO 'app3'@'127.0.0.1';
FLUSH PRIVILEGES;
```

**红线：**

- 不要使用、不要修改 `english_forest` 库；
- 不要复用 `english_forest_migrate` 账号（那是 project2 的迁移账号）；
- 任何 `DROP DATABASE` / 大规模 `DELETE` 之前必须先备份。

> 注：旧交接文档记载 `ranking` 库「保留」，但 `project2` 账号无权限、看不到它是否存在。需要 root 执行 `SHOW DATABASES;` 才能确认。**如果它还在，属于旧应用资产，不要删。**

---

## 8. 账号与 sudo 权限

### 8.1 `project2` 的受限 sudo（现状，供对照）

```text
/usr/local/bin/project2-apply-nginx       # 装 nginx 配置 + nginx -t + reload
/usr/local/bin/project2-apply-service     # 装 systemd 单元 + daemon-reload + enable --now
/usr/local/bin/project2-apply-certbot     # certbot --nginx -d yidongxun.com -d www...
/usr/bin/systemctl restart|start|stop|status project2
/usr/bin/systemctl reload nginx
```

三个助手脚本是「白名单式」的，作用是把「装配置 + 重载」这种需要 root 的动作收敛成固定命令，避免开全量 sudo。脚本内容：

- `project2-apply-nginx`：把 `/opt/project2/nginx/project2.conf` 安装到 `/etc/nginx/conf.d/project2.conf` → `nginx -t` → `systemctl reload nginx`；
- `project2-apply-service`：把 `/opt/project2/deploy/project2.service` 安装到 `/etc/systemd/system/` → `daemon-reload` → `enable --now project2`；
- `project2-apply-certbot`：只针对 `yidongxun.com` 签发。

**注意：这些脚本路径是硬编码指向 `project2` 的，新应用不能直接用。**

### 8.2 新应用需要 root 配合准备的东西

新应用需要一个对应的受限账号（参考 `project2` 的做法，最小权限）：

```bash
# 由具备 root 权限的人执行（腾讯云控制台 / ubuntu 用户 / root 登录）
useradd -m -s /bin/bash app3
mkdir -p /opt/app3/{releases,shared/env,logs,nginx,deploy}
chown -R app3:app3 /opt/app3

# 仿照 project2 写三个助手脚本（把路径和端口换成 app3 / 8004 / 8005）
install -o root -g root -m 755 app3-apply-nginx /usr/local/bin/app3-apply-nginx
install -o root -g root -m 755 app3-apply-service /usr/local/bin/app3-apply-service

# sudoers（用 visudo -f /etc/sudoers.d/app3 写入，写完 visudo -c 校验）
app3 ALL=(root) NOPASSWD: /usr/local/bin/app3-apply-nginx, /usr/local/bin/app3-apply-service, \
                          /usr/bin/systemctl restart app3, /usr/bin/systemctl start app3, \
                          /usr/bin/systemctl stop app3, /usr/bin/systemctl status app3
```

**不要给新应用 `systemctl reload nginx` 之外的 nginx 权限，尤其不要给 `restart nginx`。**

---

## 9. 运行时与依赖

- 系统只有 **Python 3.12.3**（`/usr/bin/python3`），**没有** node / npm / php / java / docker / composer / uv / redis / sqlite3 CLI；
- `project2` 自带私有运行时，**不要复用、不要修改**：
  - Node v24.21.0：`/opt/project2/runtime/node`
  - Tesseract OCR：`/opt/project2/runtime/tesseract`
- 服务器**访问不了 GitHub**（拉代码会超时），依赖安装也常受限。**生产构建请在自己的机器/CI 完成后上传产物**，不要在服务器上跑 `npm install` / `pip install` 大包。

如果新应用是 Node/PHP/Java：

- Node：建议下载官方 linux-x64 tar.gz 解到 `/opt/app3/runtime/node`，只给 app3 自己用（和 project2 一样的做法）；
- PHP/Java：需要 root 安装系统包，注意别升级系统级 Python 依赖（可能影响 project2 的 venv）。

---

## 10. 运维现状（备份、日志、定时任务）

| 项 | 现状 | 新应用要做什么 |
| --- | --- | --- |
| 数据库备份 | project2 用户 cron `45 3 * * *` 跑 `backup_project2.sh`，导出 `english_forest` + uploads，保留 14 天，落在 `/opt/project2/backups/familylearning-daily`（当前 2.4 GB） | **自建**自己的备份脚本和 cron，不要写进 project2 的备份目录 |
| 日志轮转 | project2 用户 cron `15 3 * * *` 跑 logrotate，state 文件独立 | 自建 logrotate 配置 + 独立 state 文件 |
| nginx 日志 | `/var/log/nginx/`，系统 logrotate 每日切割，保留 14 份 | 无需处理 |
| systemd | `project2.service`（enabled）、`ranking.service`（disabled） | 新建 `app3.service`，命名不要冲突 |
| journald | 有 `/etc/logrotate.d/ranking` 遗留配置 | 可忽略 |

---

## 11. 红线清单（碰到任何一条都可能让 `yidongxun.com` 挂掉）

1. **不要修改** `/etc/nginx/conf.d/project2.conf`、`/opt/project2/nginx/project2.conf`。
2. **不要修改** `/etc/systemd/system/project2.service`，不要 `systemctl stop/restart project2`。
3. **不要占用 8002 / 8003**，也不要 `pkill -f uvicorn`（会误杀 project2 的进程）。
4. **不要写 `default_server`**（会和 `ranking.conf` 冲突，见 5.2）。
5. **不要 `systemctl restart nginx`**——配置有错时会让 nginx 起不来，两个站点同时挂。永远 `nginx -t && systemctl reload nginx`。
6. **不要动 `/etc/letsencrypt/`** 里 `yidongxun.com` 的证书，不要跑不带 `-d` 限制的 `certbot` 全量命令。
7. **不要动** `english_forest` 数据库和 `english_forest_migrate` 账号。
8. **不要删除** `/opt/ranking`（109 MB）和 `/opt/project2` 下的 `releases` / `backups` / `shared`。
9. **不要两个进程同时抢同一个端口**（project2 历史上就因为「systemd + 手动 start.sh」双跑出现过 `EADDRINUSE` 重启循环）。
10. **不要升级系统级 Python 3.12**（project2 的 venv 依赖它）。

---

## 12. 资源余量（决定新应用能开多大）

| 资源 | 总量 | 已用 | 可用 | 建议给新应用的上限 |
| --- | --- | --- | --- | --- |
| CPU | 4 vCPU | project2 空闲时接近 0 | — | 不限核，但别跑常驻高负载任务 |
| 内存 | 3.6 GiB | MySQL 485 MB + project2 约 250 MB + 系统 300 MB | ≈ 2.4 GiB（含 cache） | **常驻 RSS ≤ 600 MB**，systemd 加 `MemoryMax=800M` |
| Swap | 1.9 GiB | 291 MB | 1.6 GiB | 仅兜底，不要依赖 |
| 磁盘 | 40 GB | 20 GB（`/opt/project2` 13 GB + backups 2.4 GB + `/var/log` 277 MB） | **18 GB** | **release 只保留最近 3 个**，并自建清理 |

内存是最紧的：这台机器如果 OOM，内核会挑 RSS 最大的进程杀，**很可能先杀 project2 的 uvicorn**。所以：

- 新应用建议配 `MemoryMax=800M`（systemd 会在超限时只杀它自己）；
- 不建议在这台机器上再跑 Redis / Elasticsearch 这类常驻内存服务；
- 如确需更多空间，可清理 project2 的 23 个历史 release（能回收数 GB），但**必须先确认保留哪几个**，这属于 project2 的运维动作，不要自己删。

---

## 13. 新应用上线步骤（推荐顺序）

```bash
# ① 准备代码（本地构建完成后上传，服务器不跑重依赖）
ssh app3@115.159.77.118
RELEASE=/opt/app3/releases/$(date +%Y%m%d-%H%M)
mkdir -p "$RELEASE"
rsync -az dist/ app3@115.159.77.118:$RELEASE/     # 或 scp
ln -sfn "$RELEASE" /opt/app3/current

# ② 起服务（systemd，User=app3，Restart=always，MemoryMax=800M）
sudo app3-apply-service

# ③ 本机自测（不经过 nginx，先确认应用本身没问题）
curl -fsS http://127.0.0.1:8004/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8005/

# ④ 接 nginx（配置见 5.3，不要写 default_server）
sudo app3-apply-nginx      # 内部会 nginx -t 再 reload

# ⑤ 公网验收
curl -fsS https://paihangbang.xyz/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' https://paihangbang.xyz/

# ⑥ 回归确认现有应用没被影响（每次必做，见第 14 节）
```

`app3-apply-nginx` 记得把「安装配置 → `nginx -t` → `reload`」这三步固化进去，`nginx -t` 失败就中止，绝不允许后面加 `restart`。

---

## 14. 验收检查清单（新应用每次发布后都要跑）

现有应用是否被破坏，看这 6 条就够：

```bash
# 1) 服务在跑
systemctl is-active project2 nginx mysql        # 期望 active active active

# 2) 本机健康
curl -fsS -o /dev/null -w 'api:%{http_code}\n' http://127.0.0.1:8002/api/v1/health/ready
curl -fsS -o /dev/null -w 'web:%{http_code}\n' http://127.0.0.1:8003/

# 3) 公网健康
curl -fsS -o /dev/null -w 'prod-api:%{http_code}\n' https://yidongxun.com/api/v1/health/ready
curl -fsS -o /dev/null -w 'prod-web:%{http_code}\n' https://yidongxun.com/

# 4) 证书没被覆盖（SNI 检查，各自应返回自己的域名）
echo | openssl s_client -servername yidongxun.com -connect 115.159.77.118:443 2>/dev/null \
  | openssl x509 -noout -subject
echo | openssl s_client -servername paihangbang.xyz -connect 115.159.77.118:443 2>/dev/null \
  | openssl x509 -noout -subject

# 5) nginx 配置语法
sudo nginx -t        # 或通过任一 apply-nginx 助手间接校验

# 6) 日志无新增异常
tail -50 /opt/project2/logs/project2.err.log
```

补充人工确认：浏览器打开 `https://yidongxun.com` 登录 admin、进任务列表、开一个听写任务，页面静态资源无大片 404。

---

## 15. 出问题怎么回滚

**新应用出问题**（不影响 project2）：

```bash
sudo systemctl stop app3
sudo rm -f /etc/nginx/conf.d/paihangbang.conf   # 或换回 410 占位
sudo nginx -t && sudo systemctl reload nginx
```

**project2 被误伤时**（极少数情况，如端口被抢）：

```bash
sudo /usr/bin/systemctl restart project2
# 若 release 被误切：
ln -sfn /opt/project2/releases/familylearning-fac55ad /opt/project2/app-v2
```

最近一次已知可用的 project2 release：`familylearning-fac55ad`（2026-11-05 18:21 上线，运行至今正常）。

---

## 16. 已知风险与建议

| 风险 | 说明 | 建议 |
| --- | --- | --- |
| 内存紧张 | 3.6 GiB 跑 MySQL + 两个应用，OOM 时可能误杀 project2 | 新应用设 `MemoryMax=800M`；不要加 Redis 等常驻服务 |
| 磁盘增长 | `/opt/project2/releases` 已 13 GB（23 个版本），剩 18 GB | 新应用 release 只留 3 个；project2 的旧 release 清理需另行确认 |
| MySQL 共享 | `max_connections=151`，buffer pool 仅 128 MB | 新应用连接池 ≤ 20；不要跑大表全表扫描类查询 |
| nginx 单点 | 两个站点共用同一个 nginx 进程与配置目录 | 一律 `nginx -t` 后 `reload`，禁止 `restart`；改动前先 `cp` 备份配置 |
| 证书耦合 | 续期由同一个 certbot.timer 负责 | 新增证书不要删改已有 lineage；续期后 `nginx -t` + `reload` 自动完成 |
| SSH 偏弱 | `PermitRootLogin yes`、`PasswordAuthentication yes` | 新应用上线稳定后建议改成仅密钥登录、禁止 root 直连，并收窄安全组 22 端口来源 |
| 无 GitHub 访问 | 服务器拉不到代码 | 构建在本地/CI 完成，只上传产物 |

---

## 17. 移交确认

- 现有应用负责人：________
- 新应用负责人：________
- 目标域名（确认拼写）：`paihangbang.xyz` / `panghangbang.xyz`（划掉不要的）
- 新应用端口：`8004` API / `8005` Web（如需变更，先确认 8002/8003 之外全部空闲）
- 计划上线时间：________
- 新应用 release / commit：________
- 上线后第 14 节清单执行结果：________
