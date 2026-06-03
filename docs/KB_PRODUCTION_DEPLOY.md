# 个人知识库正式部署流程

第一阶段只部署 `kb.example.com`，不启动“布丁一家人”。

如果运营商禁止公网入站 TCP `80/443`，不要使用本文的 MikroTik 端口转发方式。改用公网中转方案：

```bash
open docs/KB_RELAY_DEPLOY.md
```

## 1. 复制项目到 Debian VM

在 Mac mini 上执行：

```bash
rsync -a /path/to/home-wordpress-stack/ debian@your-server.example.com:/opt/home-wordpress/
```

如果 `/opt/home-wordpress` 还不存在，先在 Debian VM 上创建：

```bash
sudo mkdir -p /opt/home-wordpress
sudo chown -R "$USER":"$USER" /opt/home-wordpress
```

## 2. 安装 Docker

在 Debian VM 上执行：

```bash
cd /opt/home-wordpress
sudo ./scripts/bootstrap-debian.sh
sudo usermod -aG docker "$USER"
newgrp docker
```

## 3. 生成并检查配置

```bash
cd /opt/home-wordpress
./scripts/make-env.sh
nano .env
```

必须确认：

```text
DOMAIN_KB=kb.example.com
LETSENCRYPT_EMAIL=你的邮箱
```

第一阶段只部署个人知识库，`DOMAIN_FAMILY` 可以先保留默认值，不会被 `compose.kb.yml` 使用。

如果 `kb.example.com` 是 CNAME，确认它最终解析到家里的公网 IP。当前 DDNS 脚本更新的是 A 记录；如果你的 CNAME 已经指向别的 DDNS 目标，先不要启用 `alidns-ddns.timer`。

如果改成由本项目直接更新阿里云 A 记录，第一阶段建议设为：

```text
ALIYUN_RR_LIST=kb
```

## 4. MikroTik 端口转发

Debian VM 内网 IP 已确认是：

```text
<VM_IP>
```

在 MikroTik Terminal 里使用：

```routeros
:local vmIp "<VM_IP>"
:local wanInterface "pppoe-out1"

/ip firewall nat
add chain=dstnat in-interface=$wanInterface protocol=tcp dst-port=80 action=dst-nat to-addresses=$vmIp to-ports=80 comment="home-wordpress kb http"
add chain=dstnat in-interface=$wanInterface protocol=tcp dst-port=443 action=dst-nat to-addresses=$vmIp to-ports=443 comment="home-wordpress kb https"

/ip firewall filter
add chain=forward in-interface=$wanInterface protocol=tcp dst-address=$vmIp dst-port=80,443 action=accept comment="allow home-wordpress kb web"
```

如果公网接口不是 `pppoe-out1`，先用下面命令看实际名称，再替换上面的 `wanInterface`：

```routeros
/interface print
/ip address print
```

不要转发 SSH、PVE、MariaDB 或 WordPress 容器内部端口。

## 5. 启动个人知识库

在 Debian VM 上执行：

```bash
cd /opt/home-wordpress
./scripts/kb-compose.sh up -d
./scripts/kb-compose.sh ps
./scripts/init-kb-production.sh
```

打开：

```text
https://kb.example.com/wp-login.php
```

管理员账号在 `.env`：

```text
WP_ADMIN_USER
WP_ADMIN_PASSWORD
```

## 6. 验证

```bash
curl -I https://kb.example.com
curl -i https://kb.example.com/wp-json/wp/v2/posts
./scripts/kb-compose.sh logs -f caddy
```

预期：

- HTTP 会自动跳 HTTPS。
- 匿名访问首页会跳到登录页。
- 匿名 REST API 返回 401。
- 登录后进入个人知识库前台首页，不进入 WordPress Dashboard。

## 7. 备份

手动备份：

```bash
./scripts/backup-kb.sh
```

安装每日备份：

```bash
sudo cp systemd/home-wordpress-kb-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-kb-backup.timer
systemctl list-timers | grep home-wordpress-kb
```

第二阶段确认个人知识库稳定后，再部署 `family.example.com`。
