#!/usr/bin/env bash
# 把家庭学习助手绑定到 https://zijixue.xyz（根路径），并切换前端产物到根路径版本。
#
# 为什么需要 root：改 /etc/nginx、签发证书、reload nginx 都不是 project2 用户能做的。
#
# 前置条件：
#   1. zijixue.xyz / www.zijixue.xyz 的 A 记录已指向本机（已核对：115.159.77.118）
#   2. 前端已按 VITE_BASE_PATH=/ 构建，产物已上传到 STAGE 目录（见下方变量）
#   3. 本脚本对 sunxinshan.site/zijixue 只做 301，不动 personal-site 其它逻辑
#
# 幂等：可重复执行；已存在证书/已切换产物时会跳过。
set -euo pipefail

DOMAIN=zijixue.xyz
SRC=/opt/project2/nginx/zijixue.xyz.conf
CONF=/etc/nginx/conf.d/zijixue.xyz.conf
ACME_ROOT=/var/www/acme
RELEASE=$(readlink -f /opt/project2/app-v2)
DIST="$RELEASE/frontend/dist"
STAGE=/opt/project2/releases/.dist-zijixue-new
BAK=/opt/project2/nginx
TS=$(date +%Y%m%d-%H%M%S)

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
die() { printf '\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "必须 root 执行（sudo bash $0）"
[ -f "$STAGE/index.html" ] || die "缺少暂存产物：$STAGE"
grep -q 'src="/assets/' "$STAGE/index.html" || die "暂存产物不是根路径构建（未找到 /assets/ 引用）"

mkdir -p "$ACME_ROOT" "$BAK"

step "0/6 备份现有配置到 $BAK"
[ -f "$CONF" ] && cp -a "$CONF" "$BAK/zijixue.xyz.conf.bak-$TS"
cp -a /etc/nginx/conf.d/sunxinshan.conf "$BAK/sunxinshan.conf.bak-$TS"
echo "备份完成"

step "1/6 安装 80 端口 ACME 段（不引用证书，避免 nginx -t 失败）"
cat > "$CONF" <<'NGINX'
# 阶段一：仅用于证书签发，随后会被完整配置覆盖。
server {
    listen 80;
    listen [::]:80;
    server_name zijixue.xyz www.zijixue.xyz;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
    }

    location / {
        return 301 https://zijixue.xyz$request_uri;
    }
}
NGINX
nginx -t && systemctl reload nginx
echo "80 端口就绪"

step "2/6 签发 Let's Encrypt 证书"
if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  echo "证书已存在，跳过签发"
else
  certbot certonly --webroot -w "$ACME_ROOT" \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --cert-name "$DOMAIN" \
    --non-interactive --agree-tos \
    --deploy-hook "systemctl reload nginx" \
    || die "证书签发失败：确认 80 端口可从公网访问、DNS 已生效"
fi

step "3/6 安装完整 443 配置并 reload"
# 沿用项目约定：配置源文件放 /opt/project2/nginx/，再 install 到 /etc/nginx/conf.d/
cat > "$SRC" <<'NGINX'
# /etc/nginx/conf.d/zijixue.xyz.conf
# 家庭学习助手正式域名：zijixue.xyz，根路径部署（前端 base=/，接口 /api/v1）。
# 上游：127.0.0.1:8003 静态 SPA、127.0.0.1:8002 FastAPI。
# 2026-11-20 从「sunxinshan.site/zijixue 子路径」迁出。

upstream zijixue_api {
    server 127.0.0.1:8002;
    keepalive 16;
}

upstream zijixue_web {
    server 127.0.0.1:8003;
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name zijixue.xyz www.zijixue.xyz;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
    }

    location / {
        return 301 https://zijixue.xyz$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name www.zijixue.xyz;

    ssl_certificate     /etc/letsencrypt/live/zijixue.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/zijixue.xyz/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    return 301 https://zijixue.xyz$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name zijixue.xyz;

    ssl_certificate     /etc/letsencrypt/live/zijixue.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/zijixue.xyz/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 20m;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;

    # Agent 回复是 SSE 流式，proxy_buffering 必须关闭
    location ^~ /api/ {
        proxy_pass http://zijixue_api/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_connect_timeout 10s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://zijixue_web/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_connect_timeout 10s;
        proxy_read_timeout 300s;
    }
}
NGINX
chmod 644 "$SRC"
install -o root -g root -m 644 "$SRC" "$CONF"
nginx -t || die "nginx 配置校验失败，原配置在 $BAK"
systemctl reload nginx
echo "443 已生效"

step "4/6 切换前端产物（子路径版 → 根路径版）"
if grep -q '/zijixue/assets' "$DIST/index.html" 2>/dev/null; then
  mv "$DIST" "$DIST.bak-$TS"
  mv "$STAGE" "$DIST"
  chown -R project2:project2 "$DIST"
  echo "已切换；旧产物保留在 $DIST.bak-$TS"
else
  echo "当前已是根路径产物，跳过"
fi

step "5/6 sunxinshan.site/zijixue 改为 301 到新域名"
python3 - <<'PY' || echo "（跳过，不影响主流程）"
import subprocess, sys
p = '/etc/nginx/conf.d/sunxinshan.conf'
s = open(p, encoding='utf-8').read()
if 'https://zijixue.xyz' in s:
    print('已迁移过，跳过'); sys.exit(0)

pairs = [
    ('    location = /zijixue {\n        return 301 /zijixue/;\n    }',
     '    location = /zijixue {\n        return 301 https://zijixue.xyz/;\n    }'),
    ('    location ^~ /zijixue/ {\n        proxy_pass http://127.0.0.1:8080;',
     '    location ^~ /zijixue/ {\n        rewrite ^/zijixue/(.*)$ https://zijixue.xyz/$1 permanent;\n        proxy_pass http://127.0.0.1:8080;'),
]
miss = 0
for a, b in pairs:
    if a in s:
        s = s.replace(a, b)
    else:
        miss += 1
        print(f'WARN: 未匹配到片段 {a.splitlines()[0].strip()}')
if miss == len(pairs):
    sys.exit(0)
open(p, 'w', encoding='utf-8').write(s)
print('已写入 301 规则')
PY
if ! nginx -t; then
  cp -a "$BAK/sunxinshan.conf.bak-$TS" /etc/nginx/conf.d/sunxinshan.conf
  systemctl reload nginx
  die "sunxinshan.conf 改坏，已还原"
fi
systemctl reload nginx

step "6/6 冒烟验证"
JS=$(grep -o 'src="/assets/[^"]*"' "$DIST/index.html" | head -1 | cut -d'"' -f2)
echo "-- 首页：$(curl -sS -o /dev/null -w '%{http_code}' --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/)"
echo "-- 资源 $JS：$(curl -sS -o /dev/null -w '%{http_code}' --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN$JS)"
echo "-- 健康检查：$(curl -sS --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/api/v1/health/ready)"
echo "-- www 跳转：$(curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}' --resolve www.$DOMAIN:443:127.0.0.1 https://www.$DOMAIN/)"
echo "-- 80 跳转：$(curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}' --resolve $DOMAIN:80:127.0.0.1 http://$DOMAIN/)"
echo "-- 旧子路径：$(curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}' --resolve sunxinshan.site:443:127.0.0.1 https://sunxinshan.site/zijixue/)"

printf '\n\033[32m完成。回滚：\n'
echo "  cp -a $BAK/zijixue.xyz.conf.bak-$TS $CONF && systemctl reload nginx"
echo "  mv $DIST $DIST.new && mv $DIST.bak-$TS $DIST"
echo "  cp -a $BAK/sunxinshan.conf.bak-$TS /etc/nginx/conf.d/sunxinshan.conf && systemctl reload nginx"
printf '\033[0m'
