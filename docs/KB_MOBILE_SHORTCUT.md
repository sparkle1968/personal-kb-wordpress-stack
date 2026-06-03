# 手机分享发布到个人知识库

这个流程用于 iPhone / iPad 通过 WireGuard/VPN 回到家里后，把当前网页直接发布到个人知识库。安卓手机可使用同一个服务器入口，配置见 [KB_ANDROID_SHARE.md](KB_ANDROID_SHARE.md)。手机只通过 SSH 触发服务器脚本，WordPress Application Password 仍只保存在 Debian VM 的 `/opt/home-wordpress/.env` 中。

## 1. 服务器端命令

脚本位置：

```bash
/opt/home-wordpress/scripts/kb-mobile-publish.py
```

最小调用方式：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "https://example.com/article" \
  --category "技术"
```

默认行为：

- 默认发布为 `publish`，不是草稿。
- 必须传 `--category`，允许值为当前 WordPress 分类，例如 `技术`、`健康`、`生活`、`资料`、`未分类`。
- 可传 `--tag` 或 `--tags`。
- 不新增公开 HTTP 接口，不放宽匿名 REST，不开启 XML-RPC。
- 不在输出里打印 WordPress Application Password。

常用例子：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "https://example.com/article" \
  --category "健康" \
  --tags "乳腺癌, 医学资料"
```

先预演：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "https://example.com/article" \
  --category "资料" \
  --dry-run
```

## 2. iOS 快捷指令：推荐版（动态分类）

当前推荐配置是：使用动态入口 `发布到个人知识库`。动态入口运行时先从服务器读取当前 WordPress 分类，再让你选择分类。这样 `site-admin` 在页面里新增或删除分类后，手机端下一次打开快捷指令就会同步看到最新分类。

服务器端分类列表命令：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py --list-categories
```

快捷指令设置：

- 打开“在共享表单中显示”。
- 接收类型选择 URL、Safari 网页、文本。

动作建议：

1. 添加 `Receive` 动作，来源设为 `Share Sheet`。
2. `If there's no input` 设为 `Get Clipboard`。
3. 先把 `Shortcut Input` 转成文本并保存为 `sharedInput`，避免后续动作覆盖原始分享链接。
4. 添加第一个“通过 SSH 运行脚本”，脚本填 `python3 /opt/home-wordpress/scripts/kb-mobile-publish.py --list-categories`。
5. 添加“拆分文本”，按换行拆分上一步输出。
6. 添加“从列表中选取”，提示文字可写“选择知识库分类”。
7. 添加第二个“通过 SSH 运行脚本”，`Input` 设为 `sharedInput`，脚本里的 `KB_CATEGORY` 插入上一步“从列表中选取”的结果。
8. 添加“显示结果”，显示第二个 SSH 动作返回的发布结果，便于在手机上确认成功或失败。

SSH 配置：

- 主机：`<VM_IP>`
- 用户：`<ssh-user>`
- 认证方式：`SSH Key`。
- Shortcuts 会为“Run Script Over SSH”生成自己的 ed25519 key。点 `SSH Key` 后用 `Copy Public Key` 复制公钥，再把它追加到服务器 `~/.ssh/authorized_keys`。

第二个 SSH 动作的脚本内容：

```bash
set -e
KB_CATEGORY="这里插入上一步选择的项目"
KB_INPUT="$(timeout 5 cat || true)"
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "$KB_INPUT" \
  --category "$KB_CATEGORY"
```

分享菜单传入的内容会从 stdin 传给服务器。这里不要在快捷指令里预先判断是否以 `http` 开头，因为 iPhone 分享表单有时传入的是网页文本或 HTML；服务器脚本会从其中提取真实 URL。

## 2.1 固定分类快捷指令

固定分类入口仍然可用，例如 `发布到知识库-技术`。这类快捷指令速度最快，但不会自动增删入口；如果删除或改名了某个分类，服务器会拒绝旧分类发布并显示当前可用分类。旧的 `待读` / `未读` 会自动按 `未分类` 处理。

固定分类脚本示例：

```bash
set -e
KB_INPUT="$(timeout 5 cat || true)"
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py \
  --url "$KB_INPUT" \
  --category "技术"
```

## 3. 进阶版：手机提取正文后上传

有些网页是重 JavaScript 页面，服务器直接抓 URL 可能只能拿到空壳。快捷指令可以先在手机上提取文章正文，再用 JSON 通过 SSH 发给服务器。

服务器脚本支持从 stdin 读取 JSON：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-publish.py --stdin-json
```

JSON 字段：

```json
{
  "url": "https://example.com/article",
  "title": "文章标题",
  "html": "<p>带链接的正文 HTML</p>",
  "category": "技术",
  "tags": ["资料", "待读"],
  "source_site": "example.com",
  "source_author": "作者"
}
```

脚本会先清理 HTML，只保留常见正文标签、链接、图片、列表、表格和代码块，再交给 `kb-import.py` 发布。正文图片仍按原有规则搬运到 WordPress 媒体库。

## 4. 适用边界

- 常规文章网页：优先用基础版，分享 URL 即可。
- X、Claude、MediSearch、需要登录或页面高度动态渲染的内容：如果 URL 抓取效果不好，改用进阶版，或先让 Codex 整理后发布。
- 需要专业判断和重写的内容：这个手机入口负责归档和发布，不替代人工/Codex 的深度整理。

## 5. iOS 快捷指令：发布视频到知识库

`kb.example.com` 走 Cloudflare Tunnel，后台直接上传大视频可能碰到 Cloudflare 单次请求体限制。视频发布入口改走 SSH：手机把视频文件传给 Debian VM，服务器把视频保存到知识库静态目录，再创建一篇带视频的文章。

服务器端脚本：

```bash
/opt/home-wordpress/scripts/kb-mobile-video-publish.py
```

最小调用方式：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-video-publish.py \
  --title "视频标题" \
  --category "技术" \
  --filename "video.mp4"
```

快捷指令建议命名为 `发布视频到知识库`：

1. 打开“在共享表单中显示”。
2. 接收类型选择 `媒体`、`文件`，也可以保留 `URL`。
3. 添加 `Receive` 动作，来源设为 `Share Sheet`。
4. 可选：添加“编码媒体”，格式选 H.264 / MP4，方便网页播放。
5. 添加“询问输入”，提示 `文章标题`，保存为 `videoTitle`。
6. 添加第一个“通过 SSH 运行脚本”，脚本填：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-video-publish.py --list-categories
```

7. 添加“拆分文本”，按换行拆分分类列表。
8. 添加“从列表中选取”，提示 `选择知识库分类`，保存为 `videoCategory`。
9. 可选：添加“询问输入”，提示 `正文说明`，允许留空，保存为 `videoBody`。
10. 添加第二个“通过 SSH 运行脚本”，`Input` 设为共享进来的媒体文件或“编码媒体”的输出，脚本填：

```bash
python3 /opt/home-wordpress/scripts/kb-mobile-video-publish.py \
  --title "这里插入 videoTitle" \
  --category "这里插入 videoCategory" \
  --body "这里插入 videoBody" \
  --filename "mobile-video.mp4"
```

11. 添加“显示结果”，显示第二个 SSH 动作返回的 JSON。

测试时先用十几秒的小视频。确认可播放后，再测试更大的视频。

## 6. 安全检查

上线后仍用原来的巡检：

```bash
cd /opt/home-wordpress
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
```

应继续满足：

- 匿名访问 `/wp-json/wp/v2/posts` 被拦截。
- `xmlrpc.php` 被拦截。
- 只有能 SSH 登录 Debian VM 的设备可以触发手机发布。
