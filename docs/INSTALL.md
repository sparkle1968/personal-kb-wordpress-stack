# 安装部署指南

本文是开源版入口文档。先在本地跑通，再选择一种生产部署方式。

## 1. 准备

需要：

- 一台安装 Docker 和 Docker Compose plugin 的 Linux 服务器。
- 一个域名，例如 `example.com`，并准备 `kb.example.com`。
- 可选：Cloudflare Tunnel token，或可直连公网 `80/443` 的服务器。
- 可选：AliDNS API key，仅在使用阿里云 DDNS 或 DNS-01 证书签发时需要。

不要把真实 `.env`、SSH key、Application Password、Cloudflare token 或 DNS API key 提交到 Git。

## 2. 本地测试

本地测试使用 `.env.kb-local` 和 `compose.kb-local.yml`，只监听 `localhost:8080`：

```bash
./scripts/make-kb-local-env.sh
./scripts/init-kb-local.sh
```

打开：

```text
http://localhost:8080/wp-login.php
```

常用命令：

```bash
./scripts/kb-local-compose.sh ps
./scripts/kb-local-compose.sh logs -f kb-wordpress-local
./scripts/kb-local-compose.sh down
```

更完整的本地测试清单见 [KB_LOCAL_TEST.md](KB_LOCAL_TEST.md)。

## 3. 生成生产配置

把项目复制到服务器，例如 `/opt/home-wordpress`：

```bash
sudo mkdir -p /opt/home-wordpress
sudo chown -R "$USER":"$USER" /opt/home-wordpress
rsync -a /path/to/home-wordpress-stack/ debian@your-server.example.com:/opt/home-wordpress/
```

在服务器上生成 `.env`：

```bash
cd /opt/home-wordpress
./scripts/make-env.sh
nano .env
```

至少修改：

- `DOMAIN_KB`
- `LETSENCRYPT_EMAIL`
- `CLOUDFLARE_TUNNEL_TOKEN`，如果使用 Cloudflare Tunnel。
- `ALIYUN_*`，如果使用 AliDNS。
- 所有 `CHANGE_ME` 占位。

`.env` 权限建议为 `600`：

```bash
chmod 600 .env
```

## 4. 选择部署方式

推荐优先使用 Cloudflare Tunnel，适合家庭网络和不想开放入站端口的场景：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh up -d
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/init-kb-production.sh
```

详细步骤见 [KB_CLOUDFLARE_TUNNEL_DEPLOY.md](KB_CLOUDFLARE_TUNNEL_DEPLOY.md)。

如果服务器可以直接暴露 `80/443`，可以用直连 HTTPS 部署，见 [KB_PRODUCTION_DEPLOY.md](KB_PRODUCTION_DEPLOY.md)。

如果入口在一台公网边缘服务器，WordPress 在家里服务器，见 [KB_RELAY_DEPLOY.md](KB_RELAY_DEPLOY.md)。

双站点部署见 [DEPLOY.md](DEPLOY.md)。

## 5. 验证

生产启动后运行：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-compose.sh ps
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
```

预期：

- 登录页可访问。
- 匿名 REST 文章接口返回 401 或 403。
- `xmlrpc.php` 被阻止。
- 最新备份校验通过，或在初次部署时提示尚无备份。

## 6. 备份与恢复

手动备份：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/backup-kb.sh
```

安装每日备份 timer：

```bash
sudo cp systemd/home-wordpress-kb-cloudflare-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-kb-cloudflare-backup.timer
```

恢复会覆盖数据库和媒体文件，必须显式确认：

```bash
RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA \
  KB_COMPOSE_FILE=compose.kb-cloudflare.yml \
  ./scripts/restore-kb.sh backups/YYYYmmdd-HHMMSS-kb
```

更多运维命令见 [KB_OPERATIONS.md](KB_OPERATIONS.md)。

## 7. 发布内容

从 URL 或 HTML 导入内容：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --url "https://example.com/article" \
  --category "资料" \
  --status draft
```

移动端分享发布见：

- [KB_MOBILE_SHORTCUT.md](KB_MOBILE_SHORTCUT.md)
- [KB_ANDROID_SHARE.md](KB_ANDROID_SHARE.md)
