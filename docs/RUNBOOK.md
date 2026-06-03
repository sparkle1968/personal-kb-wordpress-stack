# 运维速查

## 常用命令

```bash
cd /opt/home-wordpress
docker compose ps
docker compose logs -f caddy
docker compose logs -f wordpress-kb
docker compose logs -f wordpress-family
docker compose pull
docker compose up -d
```

## 健康检查

```bash
curl -I https://kb.example.com
curl -I https://family.example.com
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
python3 scripts/ddns-alidns.py --dry-run
./scripts/backup.sh
```

当前只上线个人知识库时，优先使用：

```bash
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/backup-kb.sh
```

## 更新容器

```bash
./scripts/backup.sh
docker compose pull
docker compose up -d
docker compose ps
```

## 恢复

恢复会覆盖当前数据库和媒体文件。先确认备份目录存在，再执行：

```bash
RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA ./scripts/restore.sh backups/YYYYmmdd-HHMMSS
```

只恢复个人知识库：

```bash
RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA \
  KB_COMPOSE_FILE=compose.kb-cloudflare.yml \
  ./scripts/restore-kb.sh backups/YYYYmmdd-HHMMSS-kb
```

## 安全边界

- 公网只暴露 TCP `80/443`。
- 两个站点分别登录：`kb.example.com` 和 `family.example.com` 不使用统一门户。
- 匿名用户不能进入网站正文内容，必须先登录各自站点。
- WordPress 管理后台使用强密码。
- PVE、SSH、MariaDB 不做公网端口转发。
- 远程管理仍通过 WireGuard。
- 阿里云 RAM Key 只保存在 Debian VM 的 `.env`，权限只给 AliDNS 记录查询和更新。
