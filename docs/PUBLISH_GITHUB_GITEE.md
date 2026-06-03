# GitHub 主仓库 + Gitee 镜像发布指南

推荐把 GitHub 作为唯一主仓库，把 Gitee 作为国内访问镜像。日常只维护 GitHub，Gitee 用导入或同步保持更新。

## 1. 本地首次提交

先确认敏感文件不会进入提交：

```bash
git status --ignored --short
```

预期 `.env`、`.env.*`、`secrets/`、`private/`、`backups/`、`incoming/`、`prepared-media/` 被忽略。

暂存公开文件：

```bash
git add README.md LICENSE .gitignore .env.example .env.*.example \
  compose*.yml caddy config docs examples mikrotik mu-plugins scripts shortcuts systemd themes android
git status --short
```

提交：

```bash
git commit -m "Initial open source release"
```

## 2. 推送到 GitHub 主仓库

在 GitHub 新建空仓库，不要在网页上初始化 README、LICENSE 或 `.gitignore`。

然后在本地添加 GitHub 远端：

```bash
git remote add origin git@github.com:YOUR_GITHUB_USER/home-wordpress-stack.git
git push -u origin main
```

如果使用 HTTPS：

```bash
git remote add origin https://github.com/YOUR_GITHUB_USER/home-wordpress-stack.git
git push -u origin main
```

## 3. 导入到 Gitee 国内镜像

在 Gitee 选择“从 GitHub/GitLab 导入仓库”，填入 GitHub 仓库地址：

```text
https://github.com/YOUR_GITHUB_USER/home-wordpress-stack
```

建议 Gitee 仓库说明写明：

```text
国内镜像仓库，主仓库在 GitHub。
```

## 4. 后续更新

日常更新只推送 GitHub：

```bash
git push origin main
```

然后在 Gitee 触发同步，或配置 Gitee 的 GitHub 同步功能。不要同时在 GitHub 和 Gitee 两边改代码，避免历史分叉。

## 5. README 推荐链接

发布后可在 README 增加：

```markdown
主仓库：<https://github.com/YOUR_GITHUB_USER/home-wordpress-stack>
国内镜像：<https://gitee.com/YOUR_GITEE_USER/home-wordpress-stack>
```
