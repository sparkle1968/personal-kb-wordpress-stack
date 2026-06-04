#!/usr/bin/env python3
"""Publish a mobile-shared video as a KB post.

The video bytes are read from stdin over SSH and written to a static directory
already mounted into the WordPress container. Only the small post-creation
request goes through WordPress REST, so large video uploads avoid Cloudflare's
request-size limits.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib.util
import json
import mimetypes
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_PATH = ROOT / "scripts" / "kb-import.py"
VIDEO_DIR = ROOT / "themes" / "kanso-minimal" / "kb-videos"
VIDEO_PUBLIC_PATH = "/wp-content/themes/kanso-minimal/kb-videos"
DEFAULT_STATUS = "publish"
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024
CATEGORY_ALIASES = {
    "待读": "未分类",
    "未读": "未分类",
}
ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


def load_importer():
    spec = importlib.util.spec_from_file_location("kb_import", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load importer from {IMPORTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def split_terms(values: list[str] | None) -> list[str]:
    if not values:
        return []
    terms: list[str] = []
    for value in values:
        for item in re.split(r"[,，;；\n]+", value):
            item = item.strip()
            if item and item not in terms:
                terms.append(item)
    return terms


def normalize_category_aliases(categories: list[str], available_categories: list[str]) -> list[str]:
    normalized: list[str] = []
    for category in categories:
        target = CATEGORY_ALIASES.get(category, category)
        if target not in available_categories:
            target = category
        if target not in normalized:
            normalized.append(target)
    return normalized


def load_wordpress_categories(importer, site: str, env_file: Path) -> list[str]:
    importer.load_env(env_file)
    base_url, user, password = importer.site_config(site)
    if not user or not password:
        raise SystemExit("Missing WordPress API credentials in env file.")

    auth = importer.auth_header(user, password)
    categories: list[str] = []
    page = 1
    while True:
        path = (
            "/wp-json/wp/v2/categories"
            f"?per_page=100&page={page}&hide_empty=false&orderby=name&order=asc"
        )
        batch = importer.api_call(base_url, auth, "GET", path)
        if not isinstance(batch, list):
            break

        for item in batch:
            if not isinstance(item, dict):
                continue
            if item.get("slug") == "uncategorized":
                continue
            name = str(item.get("name") or "").strip()
            if name and name not in categories:
                categories.append(name)

        if len(batch) < 100:
            break
        page += 1

    return categories


def enable_public_share(importer, site: str, env_file: Path, post: dict[str, Any]) -> str:
    post_id = post.get("id")
    if not post_id or post.get("status") != "publish":
        return ""

    try:
        importer.load_env(env_file)
        base_url, user, password = importer.site_config(site)
        if not user or not password:
            return ""
        auth = importer.auth_header(user, password)
        response = importer.api_call(
            base_url,
            auth,
            "POST",
            f"/wp-json/home-kb/v1/public-share/{int(post_id)}",
            {},
        )
        return str(response.get("share_url") or "").strip()
    except Exception:
        return ""


def safe_filename(value: str, fallback: str = "mobile-video.mp4") -> str:
    name = Path(value or fallback).name
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name).strip()
    if not name or name in {".", ".."}:
        name = fallback
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip("-._")
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        ext = ".mp4"
    return f"{stem or 'mobile-video'}{ext}"


def unique_video_name(filename: str, data: bytes) -> str:
    path = Path(safe_filename(filename))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(data[:1024 * 1024]).hexdigest()[:10]
    stem = path.stem[:72].strip("-._") or "mobile-video"
    return f"{stamp}-{digest}-{stem}{path.suffix.lower()}"


def video_url(base_url: str, filename: str) -> str:
    return base_url.rstrip("/") + VIDEO_PUBLIC_PATH + "/" + filename


def paragraphs(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    return "\n".join(
        "<p>" + "<br>".join(html.escape(line.strip()) for line in block.splitlines()) + "</p>"
        for block in blocks
    )


def build_content(title: str, video_public_url: str, body: str, source_url: str) -> str:
    safe_video = html.escape(video_public_url, quote=True)
    safe_title = html.escape(title or "视频资料", quote=True)
    pieces: list[str] = []
    if source_url:
        safe_source = html.escape(source_url, quote=True)
        pieces.append(
            f'<p><strong>来源链接：</strong><a href="{safe_source}" target="_blank" rel="noopener noreferrer">{safe_source}</a></p>'
        )
    pieces.append(
        f'<figure class="kb-mobile-video"><video controls preload="metadata" src="{safe_video}"></video>'
        f'<figcaption>{safe_title}</figcaption></figure>'
    )
    body_html = paragraphs(body)
    if body_html:
        pieces.append(body_html)
    return "\n\n".join(pieces)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a mobile-uploaded video as a personal KB post.")
    parser.add_argument("--list-categories", action="store_true", help="Print current WordPress categories and exit.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--site", choices=["kb"], default="kb")
    parser.add_argument("--title", help="Post title.")
    parser.add_argument("--body", default="", help="Optional post body text.")
    parser.add_argument("--category", action="append", help="Knowledge base category.")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--tags", help="Comma/newline separated tag names.")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--filename", default="mobile-video.mp4", help="Original video filename from Shortcuts.")
    parser.add_argument("--status", choices=["draft", "private", "publish"], default=DEFAULT_STATUS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    importer = load_importer()
    env_file = env_path(args.env_file)
    available_categories = load_wordpress_categories(importer, args.site, env_file)

    if args.list_categories:
        print("\n".join(available_categories))
        return 0

    title = clean_text(args.title or "")
    if not title:
        raise SystemExit("Missing --title.")

    categories = split_terms(args.category or [])
    categories = normalize_category_aliases(categories, available_categories)
    if not categories:
        raise SystemExit("Missing --category. Current categories: " + ", ".join(available_categories))
    unsupported = [item for item in categories if item not in available_categories]
    if unsupported:
        raise SystemExit(
            "Unsupported category: "
            + ", ".join(unsupported)
            + ". Current categories: "
            + ", ".join(available_categories)
        )

    data = sys.stdin.buffer.read(args.max_bytes + 1)
    if not data:
        raise SystemExit("No video bytes received on stdin.")
    if len(data) > args.max_bytes:
        raise SystemExit(f"Video is larger than {args.max_bytes} bytes.")

    importer.load_env(env_file)
    base_url, user, password = importer.site_config(args.site)
    if not user or not password or password.startswith("CHANGE_ME"):
        raise SystemExit("Missing WordPress application password in env file.")

    filename = unique_video_name(args.filename, data)
    public_url = video_url(base_url, filename)
    content = build_content(title, public_url, args.body, args.source_url)

    preview = {
        "target": base_url,
        "status": args.status,
        "title": title,
        "categories": categories,
        "filename": filename,
        "video_url": public_url,
        "bytes": len(data),
    }
    if args.dry_run:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    destination = VIDEO_DIR / filename
    destination.write_bytes(data)
    destination.chmod(0o644)

    auth = importer.auth_header(user, password)
    category_ids = [importer.ensure_term(base_url, auth, "categories", name) for name in categories]
    tags = split_terms(args.tag + ([args.tags] if args.tags else []))
    tag_ids = [importer.ensure_term(base_url, auth, "tags", name) for name in tags]
    payload: dict[str, Any] = {
        "title": title,
        "content": content,
        "status": args.status,
        "categories": category_ids,
        "tags": tag_ids,
        "meta": {
            "source_url": args.source_url,
            "source_site": "手机视频上传",
            "source_author": "",
        },
    }

    try:
        post = importer.api_call(base_url, auth, "POST", "/wp-json/wp/v2/posts", payload)
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise

    permalink = post.get("link")
    share_link = enable_public_share(importer, args.site, env_file, post)

    print(json.dumps({
        "ok": True,
        "id": post["id"],
        "link": share_link or permalink,
        "share_link": share_link,
        "permalink": permalink,
        "edit": base_url.rstrip("/") + f"/wp-admin/post.php?post={post['id']}&action=edit",
        "status": post.get("status"),
        "category": categories,
        "video_url": public_url,
        "bytes": len(data),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
