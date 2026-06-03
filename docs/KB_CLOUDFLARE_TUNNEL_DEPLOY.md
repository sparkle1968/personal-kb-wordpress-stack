# 个人知识库 Cloudflare Tunnel 部署流程

第一阶段只部署 `kb.example.com`，不启动“布丁一家人”。这个方案不需要阿里云香港 VPS，也不需要 MikroTik 转发公网 `80/443`。

访问路径：

```text
浏览器 -> Cloudflare -> Cloudflare Tunnel -> 家里 Debian VM -> Caddy -> WordPress
```

## 1. 前提

- `example.com` 已经在 Cloudflare 账户里，并且域名注册商 NameSilo 的 nameserver 已指向 Cloudflare。
- 家里 Debian VM 内网 IP 是 `<VM_IP>`。
- Debian VM 能主动访问互联网。
- 第一版只用 WordPress 自己的登录页，不额外开启 Cloudflare Access。

Cloudflare Tunnel 是由家里的 `cloudflared` 主动连到 Cloudflare，不需要开放入站端口。

## 2. Cloudflare 控制台创建 Tunnel

在 Cloudflare Dashboard：

```text
Zero Trust -> Networks -> Tunnels -> Create tunnel
```

推荐选择：

```text
Connector: cloudflared
Tunnel name: home-kb
Environment: Docker
```

复制 Docker 安装命令里的 token，也就是 `<cloudflare-tunnel-token>`。不要把 token 发到公开聊天或截图里。

添加 Public Hostname：

```text
Subdomain: kb
Domain: example.com
Type: HTTP
URL: caddy:80
```

Cloudflare 会自动把 `kb.example.com` 指到这个 Tunnel。

如果 Cloudflare 页面显示 `Additional application settings`，可把 HTTP Host Header 填成：

```text
kb.example.com
```

## 3. Debian VM 部署

把项目复制到 Debian VM：

```bash
sudo mkdir -p /opt/home-wordpress
sudo chown -R "$USER":"$USER" /opt/home-wordpress
rsync -a /path/to/home-wordpress-stack/ debian@your-server.example.com:/opt/home-wordpress/
```

在 Debian VM 上安装 Docker：

```bash
cd /opt/home-wordpress
sudo ./scripts/bootstrap-debian.sh
sudo usermod -aG docker "$USER"
newgrp docker
```

生成配置：

```bash
./scripts/make-env.sh
nano .env
```

确认或填写：

```text
DOMAIN_KB=kb.example.com
KB_PUBLIC_URL=
CLOUDFLARE_TUNNEL_TOKEN=<cloudflare-tunnel-token>
```

如果 `.env` 里没有 `CLOUDFLARE_TUNNEL_TOKEN`，就手动加到文件末尾。

这套 Compose 会强制 `cloudflared` 使用 HTTP/2 连接 Cloudflare。家用宽带或路由器经常会拦 UDP/7844，日志里如果出现 QUIC 失败但 TCP/HTTP2 通过，不是 WordPress 故障。

启动：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh up -d
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/init-kb-production.sh
```

查看状态：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh ps
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh logs -f cloudflared
```

## 4. 验证

在 Debian VM 上：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh exec caddy wget -S -O - http://localhost
```

在外网浏览器打开：

```text
https://kb.example.com/wp-login.php
```

预期：

- 不需要公网端口转发。
- 不需要阿里云 DDNS。
- 打开的是 Cloudflare 证书下的 HTTPS。
- 匿名访问首页会跳转到登录页。
- 登录后进入个人知识库前台首页。

如果 Cloudflare 报 `Bad gateway` 或 `Unable to reach the origin`，优先检查 Public Hostname 的 URL 是否是 `http://caddy:80`，以及 `cloudflared` 和 `caddy` 是否都在 `compose.kb-cloudflare.yml` 里运行。

## 5. 备份

手动备份：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/backup-kb.sh
```

安装每日备份：

```bash
sudo cp systemd/home-wordpress-kb-cloudflare-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-kb-cloudflare-backup.timer
systemctl list-timers | grep home-wordpress-kb-cloudflare
```

上线后的内容推送、备份恢复、安全巡检统一看：

```bash
less docs/KB_OPERATIONS.md
```

快速巡检：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
```
