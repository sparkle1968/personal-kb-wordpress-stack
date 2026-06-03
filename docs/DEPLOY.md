# 家庭双 WordPress 部署手册

## 1. Debian VM 准备

把本目录复制到 Debian VM，例如：

```bash
sudo mkdir -p /opt/home-wordpress
sudo chown -R "$USER":"$USER" /opt/home-wordpress
rsync -a ./home-wordpress-stack/ debian-user@VM_IP:/opt/home-wordpress/
```

在 Debian VM 上安装依赖：

```bash
cd /opt/home-wordpress
sudo ./scripts/bootstrap-debian.sh
```

如果当前用户要直接运行 Docker：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

## 2. 生成配置

```bash
cd /opt/home-wordpress
./scripts/make-env.sh
nano .env
```

先核对域名：

- 当前默认配置是 `kb.example.com` 和 `family.example.com`。
- 第一阶段只部署个人知识库时，确认 `.env` 里的 `DOMAIN_KB=kb.example.com`。
- 如果用 Cloudflare Tunnel，不需要阿里云 DDNS，也不需要 MikroTik 转发公网 `80/443`。

需要手动填入：

- `LETSENCRYPT_EMAIL`
- `ALIYUN_ACCESS_KEY_ID`
- `ALIYUN_ACCESS_KEY_SECRET`
- `OFFSITE_BACKUP_TARGET`，如果已经准备好异地备份位置

## 3. 阿里云 DNS

当前 `scripts/ddns-alidns.py` 更新的是 `A` 记录。按你现在已经建好 `CNAME` 的情况，有两种走法：

- 如果 `kb`、`family` 两个 CNAME 指向另一个会自动更新到家里公网 IP 的域名，就不要再对 `kb`、`family` 运行这个 DDNS 脚本。
- 如果想让本项目自己管理 DDNS，需要把 `kb`、`family` 做成 `A` 记录，或让它们 CNAME 到某个单独的 A 记录，然后把 `.env` 里的 `ALIYUN_RR_LIST` 改成那个 A 记录的 RR。

Caddy 申请证书前，两个公网域名必须最终解析到家里的公网 IP，并且 MikroTik 已经把公网 TCP `80/443` 转发到 Debian VM。

先测试 DDNS，不真实更新：

```bash
set -a
source .env
set +a
python3 scripts/ddns-alidns.py --dry-run
```

确认无误后执行：

```bash
python3 scripts/ddns-alidns.py
```

安装定时器：

```bash
sudo cp systemd/alidns-ddns.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alidns-ddns.timer
systemctl list-timers | grep alidns
```

## 4. 启动网站

```bash
cd /opt/home-wordpress
docker compose up -d
docker compose ps
```

首次初始化 WordPress：

```bash
./scripts/init-wordpress.sh
```

脚本会创建：

- `个人知识库`
- `布丁一家人`
- `site-admin`
- `codex-publisher`
- `Members` 插件
- `family_member` 家人角色
- 推荐分类
- REST API application passwords
- 站点级隐私设置：关闭公开注册，搜索引擎不收录

把脚本输出的 `WP_KB_APP_PASSWORD` 和 `WP_FAMILY_APP_PASSWORD` 填回 `.env`。

两个站点没有统一登录入口：

- `https://kb.example.com/wp-login.php` 使用“禅意资料馆”登录界面，站名为“个人知识库”。
- `https://family.example.com/wp-login.php` 使用“日式生活杂志”登录界面。

个人知识库的已发布单篇文章普通链接可免登录阅读，方便把文章链接分享给别人。首页、搜索、分类、标签、后台和 REST 内容仍需要登录；草稿和私密文章也不会匿名公开。

## 5. MikroTik 端口转发

确认 Debian VM 的内网 IP 后，修改 `mikrotik/port-forward-template.rsc` 里的：

```routeros
:local vmIp "10.0.0.50"
```

然后在 WinBox Terminal 粘贴执行，或手工创建两条 TCP `80/443` 转发。不要把 SSH、数据库、PVE 管理端口转发到公网。

如果你的 WAN 不是 `pppoe-out1`，同时把模板里的：

```routeros
:local wanInterface "pppoe-out1"
```

改成 MikroTik 里实际的公网接口名。常见检查命令：

```routeros
/interface print
/ip address print
```

## 6. 发布草稿

知识库草稿：

```bash
python3 scripts/publish-draft.py \
  --site kb \
  --title "示例知识库文章" \
  --content-file examples/kb-post.html \
  --private-archive-file examples/kb-private-archive.html \
  --source-url "https://example.com/article" \
  --source-site "Example" \
  --category "资料" \
  --tag "示例"
```

私有全文归档优先放在 `--private-archive-file` 指向的 HTML 片段里，由 `[private_archive]` shortcode 控制登录可见。不要把私有全文作为普通媒体文件上传；如果以后确实需要附件，统一放到 `wp-content/uploads/private-archive/`，Caddy 已经对这个路径返回 404。

家庭活动草稿：

```bash
python3 scripts/publish-draft.py \
  --site family \
  --title "周末家庭活动" \
  --content-file examples/family-post.html \
  --category "日常" \
  --tag "家庭"
```

## 7. 备份

手动备份：

```bash
./scripts/backup.sh
```

安装每日备份定时器：

```bash
sudo cp systemd/home-wordpress-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-backup.timer
systemctl list-timers | grep home-wordpress
```
