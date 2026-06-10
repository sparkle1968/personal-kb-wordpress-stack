# App 化路线

这份路线用于把个人知识库逐步做成 App 应用。原则是复用现有 WordPress 知识库，不从零重建，不移动旧文件。

当前基线：

- 线上站点：`https://kb.marvin1968.top`
- 部署路径：`/opt/home-wordpress`
- 技术栈：WordPress + MariaDB + Caddy + Cloudflare Tunnel
- 已有能力：前台登录、目录、检索、分类、新资料、回收站、分类管理、同步设置、账号管理、Markdown 新增/编辑、手机分享导入、短链接公开分享、Obsidian 单向同步

## 第一阶段：PWA

目标是让现有网站先具备 App 外壳：

- 浏览器可安装到手机主屏幕和桌面。
- 使用独立窗口模式打开，保留现有登录、检索、新资料、分类和编辑流程。
- 支持系统分享到新资料页，并在只有来源链接时由服务器侧抓取正文和图片链接。
- 缓存图标、主题 CSS、manifest 和离线提示页。
- 不默认缓存私密文章正文、REST API、后台页面或登录表单提交结果。

已加入的入口：

- `/kb-app.webmanifest`
- `/kb-service-worker.js`
- `/kb-offline/`
- `themes/kanso-minimal/assets/kb-icon-192.png`
- `themes/kanso-minimal/assets/kb-icon-512.png`

验收建议：

1. 登录 `https://kb.marvin1968.top`。
2. 在 iPhone / Android / 桌面浏览器中执行“添加到主屏幕”或“安装应用”。
3. 从图标启动，确认首页、检索、新资料、文章编辑仍走原来的登录态。
4. 临时断网后刷新，应该只出现离线提示，不应该看到被缓存的私密文章正文。

## 第二阶段：移动端 App 壳

先使用一段时间 PWA，再决定是否进入第二阶段。

推荐路线：

- iOS / Android 使用 Capacitor 封装现有 Web 前台。
- 只添加真正需要原生能力的部分，例如分享扩展、深链接、通知、文件选择。
- 继续保留 iOS 快捷指令和 Android Termux 入口，直到原生分享扩展完全替代并验证稳定。

暂不推荐直接原生重写。原生重写会重复实现登录、列表、分类、编辑、上传、分享、同步和权限边界，成本高，且容易偏离现在已经可用的 WordPress 工作流。

## 桌面端

桌面端可操作，但不作为第一阶段目标。

优先顺序：

1. 先使用浏览器安装的 PWA 覆盖 macOS、Windows、Linux 的日常阅读和编辑。
2. 如果需要本地文件系统、Obsidian vault、托盘常驻、开机启动或后台同步，再做 Tauri 桌面壳。
3. Electron 也可行，但体积和资源占用更高；当前知识库场景优先考虑 Tauri。

## 发布约定

- GitHub 仍作为主仓库。
- Gitee 仍作为国内镜像。
- App 化相关文档、主题代码、图标和后续壳工程都进入同一仓库，避免 GitHub/Gitee 历史分叉。
