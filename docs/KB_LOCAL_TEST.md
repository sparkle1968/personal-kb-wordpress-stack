# 个人知识库本地测试流程

这个流程只在 Mac mini Docker 上启动个人知识库，不启动“布丁一家人”，也不触碰 Debian 正式服务器。

## 启动

```bash
cd /path/to/home-wordpress-stack
./scripts/make-kb-local-env.sh
./scripts/init-kb-local.sh
```

打开：

```text
http://localhost:8080/wp-login.php
```

管理员账号在 `.env.kb-local`：

```text
WP_ADMIN_USER
WP_ADMIN_PASSWORD
```

## 常用命令

```bash
./scripts/kb-local-compose.sh ps
./scripts/kb-local-compose.sh logs -f kb-wordpress-local
./scripts/kb-local-compose.sh down
```

## 测试项

- 匿名访问 `http://localhost:8080/` 会跳转登录页。
- 登录页显示“个人知识库”，没有印章或单字章。
- 登录后首页可以进入站点。
- 分类包含：技术、健康、生活、资料、未分类。
- API 发布用户 `codex-publisher` 已创建。
- REST API 未登录访问会返回 401。

## API 草稿测试

初始化脚本会把 `WP_KB_APP_PASSWORD` 自动写回 `.env.kb-local`。然后执行：

```bash
python3 scripts/publish-draft.py \
  --env-file .env.kb-local \
  --site kb \
  --title "本地测试：个人知识库第一篇草稿" \
  --content-file examples/kb-post.html \
  --private-archive-file examples/kb-private-archive.html \
  --source-url "https://example.com/article" \
  --source-site "Example" \
  --category "资料" \
  --tag "本地测试"
```
