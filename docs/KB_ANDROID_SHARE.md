# Android 分享发布到个人知识库

这个流程让安卓手机从 Chrome、X、微信内置浏览器等应用的分享菜单，把当前网页发布到 `kb.example.com`。服务器端继续复用现有 SSH 入口：

```bash
/opt/home-wordpress/scripts/kb-mobile-publish.py
```

设计原则不变：

- 手机必须能通过 WireGuard/VPN 访问 `<VM_IP>`。
- 只通过 SSH 触发 Debian VM 上的脚本。
- WordPress Application Password 仍只保存在服务器 `/opt/home-wordpress/.env`。
- 不新增公开 HTTP webhook，不放宽匿名 REST，不开启 XML-RPC。

## 1. 推荐方案：Termux 分享入口

Termux 支持从安卓分享菜单接收 URL；当 `~/bin/termux-url-opener` 存在时，分享到 Termux 会调用这个脚本，并把分享链接作为参数传入。

### 1.1 安装应用

在安卓手机安装：

- Termux
- 可选：Termux:API，用于完成后显示 toast 提示

Termux 官方说明：Termux 是安卓上的 Linux 环境，内置包管理，并可使用 OpenSSH 访问远程服务器。

### 1.2 Mac + ADB 快速安装

如果安卓手机已经通过 USB 连到 Mac，并且开启了 USB 调试，可以直接用项目里的脚本安装。这个方式会：

- 生成 Android 专用 SSH key。
- 把公钥追加到服务器 `<ssh-user>` 用户的 `~/.ssh/authorized_keys`。
- 把私钥临时推到手机 `Download`，再由 Termux 移入私有目录 `~/.ssh/`。
- 安装完成后删除 `Download` 里的临时私钥。
- 安装 `~/bin/termux-url-opener` 并测试分类读取。

Mac 端：

```bash
adb devices -l
adb install -r /private/tmp/com.termux_1002.apk
adb push android/termux/termux-url-opener /sdcard/Download/termux-url-opener
adb push android/termux/install-kb-share.sh /sdcard/Download/kb-android-install.sh
```

Termux 端首次运行：

```bash
termux-setup-storage
bash /sdcard/Download/kb-android-install.sh
```

安装完成后，屏幕应输出当前 WordPress 分类，例如：

```text
健康
技术
未分类
生活
资料
```

本项目当前使用的手机端入口是：

```text
android/termux/termux-url-opener
android/termux/install-kb-share.sh
```

### 1.3 手动准备 SSH key

在 Termux 里执行：

```bash
pkg update
pkg install openssh coreutils
mkdir -p ~/.ssh ~/bin
ssh-keygen -t ed25519 -f ~/.ssh/kb-android-publish-ed25519 -C "kb-android-publish"
chmod 700 ~/.ssh
chmod 600 ~/.ssh/kb-android-publish-ed25519
cat ~/.ssh/kb-android-publish-ed25519.pub
```

把输出的公钥追加到服务器：

```bash
ssh debian@your-server.example.com 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'
cat kb-android-publish-ed25519.pub | ssh debian@your-server.example.com 'cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

如果你是在手机上复制公钥，也可以直接登录服务器后手动编辑：

```bash
nano ~/.ssh/authorized_keys
```

### 1.4 手动安装分享脚本

把项目里的模板复制到 Termux：

```bash
mkdir -p ~/bin
nano ~/bin/termux-url-opener
chmod 700 ~/bin/termux-url-opener
```

脚本模板在项目中：

```text
android/termux/termux-url-opener
```

如果服务器地址、用户或 key 路径不同，修改脚本顶部：

```bash
KB_HOST="<VM_IP>"
KB_PORT="22"
KB_USER="<ssh-user>"
KB_KEY="$HOME/.ssh/kb-android-publish-ed25519"
```

可选：如果你希望所有安卓分享默认进某个分类，不每次选择分类：

```bash
KB_DEFAULT_CATEGORY="资料"
```

留空则每次分享时动态读取 WordPress 当前分类，并让你在 Termux 里选择。

### 1.5 测试

先在 Termux 里直接测试 SSH：

```bash
ssh -i ~/.ssh/kb-android-publish-ed25519 debian@your-server.example.com \
  'python3 /opt/home-wordpress/scripts/kb-mobile-publish.py --list-categories'
```

再测试分享脚本：

```bash
~/bin/termux-url-opener "https://example.com/article"
```

最后在 Chrome 里打开网页：

1. 点分享。
2. 选择 Termux。
3. Termux 打开后选择分类。
4. 等待返回 `[成功] 知识库发布完成` 或 `[失败] ...`。
5. 默认 4 秒后自动返回桌面并关闭本次 Termux 会话。

如果临时调试时不希望自动关闭，可以在脚本顶部把下面这一项改成 `0`：

```bash
KB_AUTO_CLOSE="0"
```

## 2. 固定分类快捷入口

如果你想要类似 `发布到知识库-技术` 这种最快入口，可以复制一份脚本，并设置：

```bash
KB_DEFAULT_CATEGORY="技术"
```

不过安卓分享菜单通常只显示 Termux 这个入口，不能像 iOS 快捷指令那样天然显示多个命名入口。要做多个漂亮入口，需要 Tasker / MacroDroid 这类自动化工具接管分享 intent。

## 3. Tasker 进阶方案

如果以后想做更像 iOS 快捷指令的体验，可以用 Tasker + Termux:Tasker：

- Tasker 接收安卓分享内容。
- Termux:Tasker 执行 Termux 脚本。
- Tasker 弹出分类选择和发布结果。

注意：

- Termux:Tasker 需要给 Tasker 授权 `Run commands in Termux environment`。
- 如果让 Tasker 执行 `~/.termux/tasker/` 以外的脚本，还需要配置 Termux 的 `allow-external-apps`；这个权限较大，不建议一开始启用。

当前项目推荐先用 `termux-url-opener`，链路短，权限少，也更容易排障。

## 4. 排障

### 分享菜单里没有 Termux

- 确认脚本路径是 `~/bin/termux-url-opener`。
- 确认脚本可执行：

  ```bash
  chmod 700 ~/bin/termux-url-opener
  ```

- 重新打开 Termux，再回到浏览器分享。

### 分类列表读取失败

检查手机是否已经连上 WireGuard/VPN：

```bash
ssh -i ~/.ssh/kb-android-publish-ed25519 debian@your-server.example.com 'hostname'
```

### 发布失败

在服务器查看手机发布日志：

```bash
tail -80 /opt/home-wordpress/incoming/kb-mobile-publish.log
```

然后跑一次巡检：

```bash
cd /opt/home-wordpress
KB_COMPOSE_FILE=compose.kb-cloudflare.yml ./scripts/kb-healthcheck.sh
```

## 5. 参考

- Termux 官方站点说明 Termux 是安卓上的终端和 Linux 环境，并支持 OpenSSH。
- Termux release notes 里说明分享 URL 到 Termux 会调用 `~/bin/termux-url-opener`。
- Termux:Tasker README 说明 Tasker 调 Termux 命令需要 `com.termux.permission.RUN_COMMAND` 权限。
