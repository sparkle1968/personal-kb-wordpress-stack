#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

export PATH="/data/data/com.termux/files/usr/bin:/system/bin:${PATH:-}"

KB_HOST="${KB_HOST:-}"
KB_PORT="${KB_PORT:-22}"
KB_USER="${KB_USER:-}"
KB_KEY_NAME="${KB_KEY_NAME:-kb-android-publish-ed25519}"

download_dir="/sdcard/Download"
home_dir="${HOME:-/data/data/com.termux/files/home}"
bin_dir="$home_dir/bin"
ssh_dir="$home_dir/.ssh"
url_opener_src="$download_dir/termux-url-opener"
key_src="$download_dir/$KB_KEY_NAME"
pub_src="$download_dir/$KB_KEY_NAME.pub"
url_opener_dst="$bin_dir/termux-url-opener"
key_dst="$ssh_dir/$KB_KEY_NAME"

say() {
  printf '%s\n' "$*"
}

need_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    say "缺少文件：$path"
    say "请确认 Mac 已经通过 adb push 放入 Download 目录。"
    exit 1
  fi
}

need_setting() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    say "缺少配置：$name"
    say "示例：KB_HOST=your-server.example.com KB_USER=debian bash /sdcard/Download/kb-android-install.sh"
    exit 2
  fi
}

say "准备安装知识库安卓分享入口..."

need_setting "KB_HOST" "$KB_HOST"
need_setting "KB_USER" "$KB_USER"

if ! command -v ssh >/dev/null 2>&1; then
  say "Termux 里还没有 ssh，开始安装 openssh。"
  pkg update -y
  pkg install -y openssh coreutils
fi

need_file "$url_opener_src"
if [[ ! -f "$key_src" && ! -f "$key_dst" ]]; then
  need_file "$key_src"
fi

mkdir -p "$bin_dir" "$ssh_dir"
chmod 700 "$ssh_dir"

cp "$url_opener_src" "$url_opener_dst"
chmod 700 "$url_opener_dst"

if [[ -f "$key_src" ]]; then
  cp "$key_src" "$key_dst"
  chmod 600 "$key_dst"
else
  say "保留现有 SSH key：$key_dst"
fi

if [[ -f "$pub_src" ]]; then
  cp "$pub_src" "$key_dst.pub"
  chmod 644 "$key_dst.pub"
fi

ssh-keyscan -p "$KB_PORT" "$KB_HOST" >> "$ssh_dir/known_hosts" 2>/dev/null || true
chmod 600 "$ssh_dir/known_hosts" 2>/dev/null || true

rm -f "$key_src" "$pub_src"

say "安装完成。"
say "分享入口：$url_opener_dst"
say "SSH key：$key_dst"
say "测试分类读取："
ssh -i "$key_dst" -p "$KB_PORT" \
  -o BatchMode=yes \
  -o ConnectTimeout=15 \
  -o StrictHostKeyChecking=accept-new \
  "$KB_USER@$KB_HOST" \
  "python3 /opt/home-wordpress/scripts/kb-mobile-publish.py --list-categories"
