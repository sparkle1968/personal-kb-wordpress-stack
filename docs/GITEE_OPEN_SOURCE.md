# Gitee 开源检查清单

这份清单用于把项目发布到 Gitee 前做最后确认。目标是保留可恢复的本地项目状态，同时只提交可公开复用的模板代码和文档。

本项目推荐先发布到 GitHub 主仓库，再导入或同步到 Gitee 国内镜像。具体步骤见 [PUBLISH_GITHUB_GITEE.md](PUBLISH_GITHUB_GITEE.md)。

## 1. 确认仓库状态

```bash
git status --short --untracked-files=all
git status --ignored --short
```

预期：

- `main` 可以没有历史 commit。
- `.env`、`.env.*`、`secrets/`、`private/`、`backups/`、`incoming/`、`prepared-media/`、`.DS_Store` 应显示为 ignored。
- `README.md`、`LICENSE`、`.env.example`、`.env.*.example`、`compose*.yml`、`docs/`、`scripts/`、`themes/`、`mu-plugins/` 可以作为公开提交候选。

## 2. 检查密钥和个人信息

```bash
rg -n --hidden -S \
  --glob '!.git/**' \
  --glob '!private/**' \
  --glob '!secrets/**' \
  --glob '!backups/**' \
  --glob '!incoming/**' \
  --glob '!prepared-media/**' \
  '(/Users/|/Volumes/|192\.168\.|@192\.168\.|BEGIN (RSA|OPENSSH|PRIVATE) KEY|AKIA|PASSWORD=|TOKEN=|SECRET=|KEY=|gmail|CloudStorage|My Drive)' .
```

允许出现：

- `CHANGE_ME`、`example.com`、`your-server.example.com`、`<VM_IP>`。
- 文档中的通用示例路径，例如 `/opt/home-wordpress`。
- 变量名，例如 `CLOUDFLARE_TUNNEL_TOKEN`、`ALIYUN_ACCESS_KEY_SECRET`。

不应出现：

- 真实域名、真实内网 IP、真实服务器账号。
- 真实邮箱、个人本机路径、Obsidian vault 私有路径。
- 私钥、公钥、WordPress Application Password、Cloudflare token、DNS API key。

## 3. 确认不开源的内容

以下内容只保留在本地，不进入 Gitee：

- 真实 `.env` 和 `.env.*`。
- `secrets/` 中的 SSH key、Application Password 或其他凭证。
- `private/` 中的截图、快捷指令二进制、个人恢复资料和本机网盘备份工作流。
- `incoming/`、`backups/`、`prepared-media/` 中的运行数据。

## 4. 首次提交建议

```bash
git add README.md LICENSE .gitignore .env.example .env.*.example \
  compose*.yml caddy config docs examples mikrotik mu-plugins scripts shortcuts systemd themes android
git status --short
```

确认没有 ignored 文件被加入暂存区后再提交：

```bash
git commit -m "Initial open source release"
```

首次 commit 完成后，先推送到 GitHub 主仓库，再在 Gitee 从 GitHub 导入或配置同步。
