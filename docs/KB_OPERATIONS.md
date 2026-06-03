# 个人知识库内容推送、备份、安全巡检

当前线上站点：

```text
https://kb.example.com
Debian VM: <VM_IP>
Remote path: /opt/home-wordpress
Compose file: compose.kb-cloudflare.yml
```

## 1. 从 Mac 推送项目文件到 Debian

这个脚本只同步代码、Compose、Caddy、主题、MU 插件和运维脚本，不会覆盖 Debian 上的 `.env`、`secrets/`、`backups/`、`incoming/`、`prepared-media/`。

```bash
cd /path/to/home-wordpress-stack
REMOTE_HOST=your-server.example.com REMOTE_USER=debian ./scripts/push-kb-stack.sh
```

同步后顺便重启并巡检：

```bash
REMOTE_HOST=your-server.example.com REMOTE_USER=debian RESTART_KB=1 RUN_REMOTE_HEALTHCHECK=1 ./scripts/push-kb-stack.sh
```

默认目标是：

```text
REMOTE_HOST=your-server.example.com
REMOTE_DIR=/opt/home-wordpress
KB_COMPOSE_FILE=compose.kb-cloudflare.yml
```

如果需要清理远端已经删除的旧项目文件，再加：

```bash
RSYNC_DELETE=1 REMOTE_HOST=your-server.example.com REMOTE_USER=debian ./scripts/push-kb-stack.sh
```

## 2. 推送内容到个人知识库

在 Debian VM 上执行最稳，因为 `/opt/home-wordpress/.env` 里已经保存了 Application Password。上传入口不会新增匿名接口，只使用 WordPress Application Password 调用已认证 REST API。

从网页链接抓取标题、摘要、正文、来源信息，并创建草稿：

```bash
cd /opt/home-wordpress
python3 scripts/kb-import.py \
  --site kb \
  --url "https://example.com/article" \
  --category "资料" \
  --tag "待读" \
  --status draft
```

先预演，不写入 WordPress，也不会上传图片：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --url "https://example.com/article" \
  --category "资料" \
  --tag "待读" \
  --status draft \
  --dry-run
```

导入本地整理好的 HTML 或笔记：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --content-file examples/kb-post.html \
  --title "手动整理的一篇笔记" \
  --category "技术" \
  --tag "网络" \
  --status draft
```

从 Mac 本地测试站导入：

```bash
cd /path/to/home-wordpress-stack
python3 scripts/kb-import.py \
  --env-file .env.kb-local \
  --site kb \
  --content-file examples/kb-post.html \
  --title "本地测试：导入一篇资料" \
  --category "资料" \
  --tag "本地测试" \
  --status draft
```

更新已有文章：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --post-id 123 \
  --title "更新后的标题" \
  --content-file examples/kb-post.html \
  --status draft
```

明确发布为正式文章：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --url "https://example.com/article" \
  --category "资料" \
  --tag "已整理" \
  --status publish
```

正文图片默认会从外站搬运到 WordPress 媒体库，并把文章里的 `img src` 改成本站媒体地址。安全默认值：

- 跳过 `data:` 图片、私网/本机图片 URL、非图片 MIME。
- 默认最多搬运 20 张，每张最多 8 MB。
- 可用 `--no-copy-images` 只保存正文和外链图片地址。
- 可用 `--max-images 10` 或 `--max-image-bytes 4194304` 调整限制。

如果只是上传已经整理好的本地图片，可继续使用：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --content-file examples/kb-post.html \
  --title "带本地图片的资料" \
  --media prepared-media/photo.jpg \
  --featured-media prepared-media/cover.jpg \
  --category "资料" \
  --status draft
```

带登录可见全文归档：

```bash
python3 scripts/kb-import.py \
  --site kb \
  --title "资料卡片：长文归档" \
  --content-file examples/kb-post.html \
  --private-archive-file examples/kb-private-archive.html \
  --category "资料" \
  --status private
```

旧的 `scripts/publish-draft.py` 仍可用于已经整理好 HTML 的简单发布；新内容导入优先用 `scripts/kb-import.py`。

## 3. 同步到 Obsidian

Obsidian 同步是单向镜像：WordPress 个人知识库是权威源，Obsidian 只保存本地 Markdown 副本。第一版不会从 Obsidian 反向发布到 WordPress。

在 Mac 上准备本地配置：

```bash
cp .env.obsidian.example .env.obsidian
```

把 `.env.obsidian` 里的 `WP_KB_APP_PASSWORD` 改成 WordPress Application Password。这个文件会被 `.gitignore` 排除，不要提交。

先预演同步计划，不写入 Obsidian：

```bash
python3 scripts/kb-obsidian-sync.py --env-file .env.obsidian --dry-run
```

确认计划后执行同步：

```bash
python3 scripts/kb-obsidian-sync.py --env-file .env.obsidian
```

site-admin 登录后可以在前台左侧栏进入“同步设置”，选择定时同步或实时同步。这个设置由 Mac 本机脚本读取；WordPress 服务器不会直接写入本地 Obsidian vault。

让本机脚本按网站设置持续同步：

```bash
python3 scripts/kb-obsidian-sync.py --env-file .env.obsidian --watch
```

“实时同步”第一版是近实时轮询，默认每 30 秒检查一次 WordPress；“定时同步”按设置的分钟间隔执行。调试时可以限制运行次数：

```bash
python3 scripts/kb-obsidian-sync.py --env-file .env.obsidian --watch --max-runs 1 --dry-run
```

默认同步 `publish,draft,private` 三类帖子到：

```text
${OBSIDIAN_VAULT_DIR}/个人知识库
```

同步规则：

- 按主分类写入目录，例如 `个人知识库/技术/123-标题.md`。
- Markdown frontmatter 会保存 WordPress ID、slug、状态、日期、链接、分类、标签和来源信息。
- `tags` 会自动转换为 Obsidian 可用标签，例如空格转为连字符；WordPress 原始标签保存在 `wp_tags_original`。
- 图片和视频保留 WordPress 远程链接，不下载附件。
- 如果本地 Markdown 被手动改过，脚本会先移到 `_conflicts/`，再写入 WordPress 最新版本。
- 如果 WordPress 里对应帖子消失或不在同步状态内，本地文件会移到 `_archived/`，不会直接删除。
- `_sync/index.json` 保存同步状态，不需要手动编辑。

可选覆盖目标目录或状态：

```bash
python3 scripts/kb-obsidian-sync.py \
  --env-file .env.obsidian \
  --target-dir "个人知识库" \
  --status publish,draft,private
```

## 4. 从手机分享菜单发布

如果手机已经通过 WireGuard/VPN 回到家里网络，可以用 iOS 快捷指令或安卓 Termux 分享入口通过 SSH 触发服务器发布，不新增任何公开接口。

服务器端入口：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "https://example.com/article" \
  --category "技术"
```

默认直接发布为 `publish`。iOS 配置见 [KB_MOBILE_SHORTCUT.md](KB_MOBILE_SHORTCUT.md)，Android 配置见 [KB_ANDROID_SHARE.md](KB_ANDROID_SHARE.md)。

## 5. 分享阅读和分类管理

已发布文章的普通文章链接可以免登录阅读，适合直接发给别人。站点首页、搜索、分类页、标签页、后台和 REST API 仍需要登录；草稿和私密文章不会匿名公开。

`site-admin` 可以在首页侧栏进入“分类管理”，也可以直接打开：

```text
https://kb.example.com/wp-admin/edit-tags.php?taxonomy=category
```

分类管理规则：

- `site-admin` 可以新增、重命名、删除分类。
- `site-admin` 可以在文章编辑页修改文章所属分类。
- 手机发布脚本每次运行都会读取当前 WordPress 分类；分类增删后，动态分类快捷指令会自动使用最新列表。
- 删除分类后，固定分类快捷指令如果仍传旧分类名，服务器会拒绝发布并显示当前可用分类，避免把已删除分类重新创建回来。

## 6. 账号管理

`site-admin` 登录后可以在侧边栏进入“账号管理”，新增、删除普通账号、调整账号权限或重置网页登录密码。受保护账号不能在这里删除或降权，包括 `site-admin` 和 `.env` 中用于发布/API 的账号；但仍可由 `site-admin` 重置网页登录密码。

前台“改登录密码”只影响网页登录密码，不会修改 WordPress Application Password。`WP_KB_APP_PASSWORD` 这类 API 同步凭证需要在 WordPress 后台重新生成，或在服务器 `.env` / 本地 `.env.obsidian` 中单独维护。

当前前台可管理的账号类型：

- `阅读账号` / `kb-viewer`：只能登录阅读已发布资料。
- `整理账号` / `kb-author`：可以新增、发布和维护自己的资料，不能管理分类或其他人的内容。
- `发布账号` / `editor`：可以新增、发布、编辑、删除资料，并管理分类。

删除普通账号时，账号名会被删除，原有内容会归还给当前 `site-admin`，避免文章丢失。

## 7. 手动备份和自动备份

手动备份：

```bash
cd /opt/home-wordpress
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/backup-kb.sh
```

备份内容包括：

- MariaDB 数据库：`db-kb.sql.gz`
- 上传文件：`uploads-kb.tar.gz`
- 已安装 WordPress 插件：`plugins-kb.tar.gz`
- 不含密钥的部署配置：`site-config.tar.gz`
- 插件列表、Compose 状态、WordPress Core 版本
- `env-redacted.txt` 和 `env-template.txt`
- `SHA256SUMS` 校验文件

安装每日自动备份：

```bash
sudo cp systemd/home-wordpress-kb-cloudflare-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-wordpress-kb-cloudflare-backup.timer
systemctl list-timers | grep home-wordpress-kb-cloudflare
```

如果有异地备份目标，在 `.env` 中设置：

```text
OFFSITE_BACKUP_TARGET=user@nas:/volume1/backups/home-wordpress
OFFSITE_BACKUP_DELETE=0
```

`OFFSITE_BACKUP_DELETE=1` 会让异地目录跟随本地保留策略删除旧备份，确认后再开启。

## 8. 恢复演练

恢复会覆盖当前数据库和媒体文件，必须显式确认：

```bash
cd /opt/home-wordpress
RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA \
  KB_COMPOSE_FILE=compose.kb-cloudflare.yml \
  ./scripts/restore-kb.sh backups/YYYYmmdd-HHMMSS-kb
```

恢复脚本会先检查 `SHA256SUMS`，再恢复数据库、uploads，并在备份包含插件包时恢复插件目录。

## 9. 安全巡检

```bash
cd /opt/home-wordpress
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
```

巡检会检查：

- `.env` 权限是否接近 `600`
- Compose 文件和核心容器是否可见
- 登录页是否可访问
- 匿名 REST 文章接口是否被拦截
- `xmlrpc.php` 是否被拦截
- 最新备份的校验文件是否通过
- systemd 自动备份 timer 是否启用

## 10. 当前安全边界

- Cloudflare Tunnel 主动出站连接，不开放家庭公网入站端口。
- WordPress 全站登录后可见，匿名 REST 内容接口被拦截。
- 单篇文章的公开分享只通过带 token 的链接生效，不开放目录页、搜索页、REST 内容接口或其他文章。
- `xmlrpc.php` 在 Caddy 和 WordPress 层都关闭。
- 登录失败按来源 IP 做 20 分钟窗口限制，8 次失败后暂时锁定。
- `.env`、`secrets/` 不随项目同步，也不进入普通备份包。
- Caddy 和 WordPress 都设置基础安全头，KB 站点默认 `noindex,nofollow`。

密钥仍需单独保存一份加密备份，至少包括 `/opt/home-wordpress/.env` 和 `/opt/home-wordpress/secrets/`。
