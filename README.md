# Personal Knowledge Base WordPress Stack

一个面向家庭自托管的 WordPress 知识库部署包。它把 WordPress、MariaDB、Caddy、WP-CLI、主题、MU 插件、内容导入脚本、移动端分享入口和备份恢复脚本整理在一个 Docker Compose 项目里。

默认示例域名使用 `kb.example.com` 和 `family.example.com`。真实域名、数据库密码、Cloudflare Tunnel token、DNS API key、WordPress Application Password 和 SSH key 都应只保存在本地 `.env`、服务器 `.env` 或 `secrets/` 中，不应提交到 Git。

本仓库适合发布到 Gitee 作为开源部署模板。开源范围只包括 Docker Compose、Caddy 配置、WordPress 主题/MU 插件、初始化脚本、导入脚本、移动端模板和通用运维文档。本机专用恢复材料、真实密钥、运行数据、私有截图、个人网盘备份工作流等应保留在被忽略目录里，不进入公开仓库。

推荐发布方式：

- GitHub 作为主仓库，负责正式提交、版本和主要协作。
- Gitee 作为国内访问镜像，方便国内用户浏览和克隆。
- 日常只向 GitHub 推送，再从 Gitee 导入或同步 GitHub 仓库。

## 功能

- 个人知识库站点，可选家庭站点。
- Caddy 反向代理和安全响应头。
- Cloudflare Tunnel、直连 HTTPS、边缘中转三种部署思路。
- WordPress 初始化脚本，自动创建用户、分类、主题和 Application Password。
- 登录保护、匿名 REST 拦截、`xmlrpc.php` 禁用、私有归档 shortcode。
- URL/HTML 导入、图片搬运、手机分享发布、视频发布辅助脚本。
- 数据库、uploads、插件和站点配置备份与恢复。

## 快速开始

本地测试只会启动个人知识库，不会连接生产服务器：

```bash
./scripts/make-kb-local-env.sh
./scripts/init-kb-local.sh
```

打开：

```text
http://localhost:8080/wp-login.php
```

生产部署从安装文档开始：

```bash
less docs/INSTALL.md
```

Cloudflare Tunnel 部署：

```bash
less docs/KB_CLOUDFLARE_TUNNEL_DEPLOY.md
```

上线后的内容推送、备份恢复和安全巡检：

```bash
less docs/KB_OPERATIONS.md
```

## 目录

- `compose*.yml`：不同部署模式的 Docker Compose 文件。
- `caddy/`：Caddy 配置和带 AliDNS 插件的构建文件。
- `themes/kanso-minimal/`：知识库主题。
- `mu-plugins/`：登录保护、分享链接、来源字段和安全策略。
- `scripts/`：初始化、导入、发布、同步、备份、恢复和巡检脚本。
- `docs/`：安装、部署、运维、移动端分享和排障文档。
- `android/`、`shortcuts/`：移动端分享发布模板。
- `systemd/`：服务器端定时备份和 DDNS timer 模板。

## 开源前检查

这些内容已被 `.gitignore` 排除，初始化仓库前仍建议再检查一次：

- `.env`、`.env.*` 中的真实配置。
- `secrets/` 中的 SSH key、Application Password 或其他凭证。
- `backups/`、`incoming/`、`prepared-media/` 中的运行数据。
- `private/` 中的本机专用资料。
- `*.shortcut` 这类可能嵌入个人主机和账号的快捷指令二进制。

推荐按 [Gitee 开源检查清单](docs/GITEE_OPEN_SOURCE.md) 扫描后再执行首次 commit。
发布流程见 [GitHub 主仓库 + Gitee 镜像发布指南](docs/PUBLISH_GITHUB_GITEE.md)。

可用下面的命令做公开文件敏感词扫描：

```bash
rg -n "CHANGE_ME|example.com|YOUR_|<VM_IP>|password|secret|token|private key" \
  --glob '!private/**' --glob '!secrets/**' --glob '!backups/**'
```

`CHANGE_ME`、`example.com`、`YOUR_*` 和 `<VM_IP>` 应保留为模板占位；真实域名、邮箱、IP、用户名、token 和 key 不应出现在公开文件中。

## 许可证

本项目按 `GPL-2.0-or-later` 发布，和仓库内 WordPress 主题的许可声明保持一致。
