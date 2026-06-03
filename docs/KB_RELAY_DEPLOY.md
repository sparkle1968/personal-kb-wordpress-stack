# 个人知识库公网中转部署流程

适用场景：家里有公网 IP，但运营商封了入站 TCP `80/443`。这时不要继续做 MikroTik 端口转发，改用一台公网云服务器做 HTTPS 入口。

访问路径：

```text
浏览器 -> 阿里云边缘服务器 80/443 -> WireGuard -> 家里 Debian VM 10.66.66.2:80 -> WordPress
```

第一阶段只部署 `kb.example.com`。

## 1. DNS

把 `kb.example.com` 解析到阿里云边缘服务器的公网 IP。

如果你现在用 CNAME，也可以这样做：

```text
kb.example.com CNAME edge.example.com
edge.example.com A 阿里云边缘服务器公网 IP
```

这个方案下家里公网 IP 不需要被 DNS 暴露，`scripts/ddns-alidns.py` 可以先不用。

## 2. 阿里云边缘服务器

边缘服务器只做两件事：

- Caddy 监听公网 TCP `80/443`，自动申请 `kb.example.com` 证书。
- WireGuard 服务端，和家里的 Debian VM 建隧道。

安全组至少放行：

```text
TCP 80
TCP 443
UDP 51820
```

安装依赖：

```bash
sudo apt-get update
sudo apt-get install -y wireguard docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

生成 WireGuard 密钥：

```bash
umask 077
wg genkey | tee ~/edge_private.key | wg pubkey > ~/edge_public.key
wg genkey | tee ~/home_private.key | wg pubkey > ~/home_public.key
```

边缘服务器 `/etc/wireguard/wg0.conf`：

```ini
[Interface]
Address = 10.66.66.1/24
ListenPort = 51820
PrivateKey = EDGE_PRIVATE_KEY

[Peer]
PublicKey = HOME_PUBLIC_KEY
AllowedIPs = 10.66.66.2/32
```

启动 WireGuard：

```bash
sudo systemctl enable --now wg-quick@wg0
sudo wg
```

复制本项目到边缘服务器，例如 `/opt/home-wordpress-edge`，然后创建 `.env.edge`：

```bash
cd /opt/home-wordpress-edge
cp .env.edge.example .env.edge
nano .env.edge
```

确认：

```text
DOMAIN_KB=kb.example.com
HOME_KB_ORIGIN=10.66.66.2:80
```

启动边缘 Caddy：

```bash
./scripts/edge-compose.sh up -d
./scripts/edge-compose.sh logs -f caddy
```

## 3. 家里 Debian VM

家里 Debian VM 内网 IP 是：

```text
<VM_IP>
```

不需要 MikroTik 端口转发 TCP `80/443`。

安装 WireGuard：

```bash
sudo apt-get update
sudo apt-get install -y wireguard
```

家里 Debian VM `/etc/wireguard/wg0.conf`：

```ini
[Interface]
Address = 10.66.66.2/24
PrivateKey = HOME_PRIVATE_KEY

[Peer]
PublicKey = EDGE_PUBLIC_KEY
Endpoint = EDGE_PUBLIC_IP:51820
AllowedIPs = 10.66.66.1/32
PersistentKeepalive = 25
```

启动 WireGuard：

```bash
sudo systemctl enable --now wg-quick@wg0
sudo wg
ping -c 3 10.66.66.1
```

复制本项目到家里 Debian VM `/opt/home-wordpress`，生成 `.env`：

```bash
cd /opt/home-wordpress
./scripts/make-env.sh
nano .env
```

确认：

```text
DOMAIN_KB=kb.example.com
LETSENCRYPT_EMAIL=你的邮箱
```

启动家里 WordPress 和内部 Caddy：

```bash
KB_COMPOSE_FILE=compose.kb-home-relay.yml ./scripts/kb-compose.sh up -d
KB_COMPOSE_FILE=compose.kb-home-relay.yml ./scripts/init-kb-production.sh
```

## 4. 验证

在边缘服务器上：

```bash
curl -I http://10.66.66.2
curl -I https://kb.example.com
```

在任意外网设备上：

```text
https://kb.example.com/wp-login.php
```

预期：

- Caddy 在边缘服务器成功申请证书。
- 外网访问不需要端口号。
- 家里 MikroTik 不需要转发 80/443。
- 登录后进入个人知识库首页。

## 5. 备份

备份仍然在家里 Debian VM 上做：

```bash
KB_COMPOSE_FILE=compose.kb-home-relay.yml ./scripts/backup-kb.sh
```

安装定时备份时，把 systemd service 的 `ExecStart` 改成：

```bash
sudo cp systemd/home-wordpress-kb-relay-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-kb-relay-backup.timer
systemctl list-timers | grep home-wordpress-kb-relay
```
